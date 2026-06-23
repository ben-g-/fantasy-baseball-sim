"""
Core game simulation engine.

Simulates a 9-inning (or extra-innings) fantasy baseball game between two lineups.
Returns structured result data ready to be written to the database.
"""

import random
import uuid
from dataclasses import dataclass, field
from typing import Optional

from stats import LeagueAverages, pa_probabilities, sb_attempt_rate, sb_success_rate, batter_pa_cap, pitcher_bf_cap, pitcher_pitch_cap
from text_gen import describe_pa, describe_stolen_base, describe_caught_stealing

# Pitches-per-PA average used for pitch count estimation
_AVG_PITCHES_PER_PA = 3.9

# Runner advancement lookup table.
# Key: (hit_type, runners_on_bases_tuple, outs)
# Value: list of (runner_base_before -> base_after) for each runner, 0=scored/out-of-play
# Bases tuple: (r1, r2, r3) each True/False
# We encode simple fixed advancement rules:
#   single: r3 scores, r2 scores, r1 advances to 2nd (sometimes 3rd with 0/1 out)
#   double: r3 scores, r2 scores, r1 scores
#   triple: all runners score
#   hr: all runners score (including batter)

def _advance_runners(hit_type: str, runners: dict[int, int], outs: int) -> tuple[dict[int, int], int]:
    """
    Advance baserunners based on hit type.

    runners: dict mapping base (1,2,3) -> player_id (0 = empty)
    Returns (new_runners, runs_scored).
    """
    new_runners: dict[int, int] = {1: 0, 2: 0, 3: 0}
    runs = 0

    if hit_type == 'hr':
        runs = sum(1 for v in runners.values() if v) + 1  # all runners + batter
        return new_runners, runs

    if hit_type == 'triple':
        runs = sum(1 for v in runners.values() if v)
        return new_runners, runs

    if hit_type == 'double':
        runs = sum(1 for v in runners.values() if v)
        # No runners remain after double (all score), batter at 2nd
        new_runners[2] = -1  # placeholder for batter
        return new_runners, runs

    if hit_type == 'single':
        # r3 always scores
        if runners[3]:
            runs += 1
        # r2 scores
        if runners[2]:
            runs += 1
        # r1 advances to 2nd (3rd with 0 outs)
        if runners[1]:
            new_runners[2 if outs >= 1 else 3] = runners[1]
        new_runners[1] = -1  # batter placeholder
        return new_runners, runs

    # bb / hbp — force advances only
    if hit_type in ('bb', 'hbp'):
        if runners[1] and runners[2] and runners[3]:
            runs += 1
            new_runners[3] = runners[3]
            new_runners[2] = runners[2]
            new_runners[1] = runners[1]
        elif runners[1] and runners[2]:
            new_runners[3] = runners[2]
            new_runners[2] = runners[1]
            new_runners[1] = -1
        elif runners[1]:
            new_runners[2] = runners[1]
            new_runners[1] = -1
        else:
            if runners[2]:
                new_runners[2] = runners[2]
            if runners[3]:
                new_runners[3] = runners[3]
            new_runners[1] = -1
        return new_runners, runs

    return new_runners, runs


@dataclass
class BatterSlot:
    batting_position: int  # 1-9
    player_id: int
    field_position: str
    bats: str
    stats: dict | None
    dh_eligible: bool = True  # has at least one non-P eligible position
    pa_used: int = 0
    ph_player_id: Optional[int] = None  # set if pinch-hit substitution made


@dataclass
class PitcherSlot:
    player_id: int
    throws: str
    stats: dict | None
    bf_used: int = 0
    pitches_used: int = 0
    sequence: int = 1  # 1 = starter, 2+ = relievers


@dataclass
class TeamState:
    team_id: str
    batting_order: list[BatterSlot]
    bullpen: list[PitcherSlot]  # available relievers (all except SP)
    current_pitcher: PitcherSlot
    current_batting_spot: int = 0  # index into batting_order (0-8)
    bench: list[BatterSlot] = field(default_factory=list)

    # Tracking for output
    events: list[dict] = field(default_factory=list)
    batter_stats: dict[int, dict] = field(default_factory=dict)
    pitcher_stats: dict[int, dict] = field(default_factory=dict)
    batter_positions: dict[int, list[str]] = field(default_factory=dict)
    line_score: dict[int, dict] = field(default_factory=dict)  # inning -> {r,h,e}
    _slot_batter_count: dict[int, int] = field(default_factory=dict, repr=False)

    def next_batter(self) -> BatterSlot:
        slot = self.batting_order[self.current_batting_spot]
        self.current_batting_spot = (self.current_batting_spot + 1) % 9
        return slot

    def peek_batter(self) -> BatterSlot:
        return self.batting_order[self.current_batting_spot]

    def _get_reliever(self) -> PitcherSlot | None:
        return self.bullpen[0] if self.bullpen else None

    def should_change_pitcher(self) -> bool:
        p = self.current_pitcher
        bf_cap = pitcher_bf_cap(p.stats)
        pitch_cap = pitcher_pitch_cap(p.stats)
        return bf_cap > 0 and p.bf_used >= bf_cap and pitch_cap > 0 and p.pitches_used >= pitch_cap

    def sp_batting_slot_index(self) -> int | None:
        """Index of the P-position batting slot, if the pitcher is batting for himself."""
        for i, slot in enumerate(self.batting_order):
            if slot.field_position == 'P':
                return i
        return None

    def change_pitcher(self) -> PitcherSlot | None:
        reliever = self._get_reliever()
        if reliever:
            self.bullpen.pop(0)
            reliever.sequence = self.current_pitcher.sequence + 1
            self.current_pitcher = reliever
        return reliever

    def record_pitcher(self, h: int = 0, r: int = 0, er: int = 0, bb: int = 0, k: int = 0, hr: int = 0, outs: int = 0) -> None:
        pid = self.current_pitcher.player_id
        if pid not in self.pitcher_stats:
            self.pitcher_stats[pid] = {'outs_recorded': 0, 'h': 0, 'r': 0, 'er': 0, 'bb': 0, 'k': 0, 'hr': 0}
        ps = self.pitcher_stats[pid]
        ps['outs_recorded'] += outs
        ps['h'] += h
        ps['r'] += r
        ps['er'] += er
        ps['bb'] += bb
        ps['k'] += k
        ps['hr'] += hr

    def record_batter(self, batter_slot: BatterSlot, ab: int = 0, r: int = 0, h: int = 0,
                      doubles: int = 0, triples: int = 0, hr: int = 0,
                      rbi: int = 0, bb: int = 0, k: int = 0, sb: int = 0) -> None:
        pid = batter_slot.ph_player_id or batter_slot.player_id
        if pid not in self.batter_stats:
            pos = batter_slot.batting_position
            seq = self._slot_batter_count.get(pos, 0) + 1
            self._slot_batter_count[pos] = seq
            self.batter_stats[pid] = {
                'batting_order_position': pos,
                'sequence_within_spot': seq,
                'ab': 0, 'r': 0, 'h': 0, 'doubles': 0, 'triples': 0,
                'hr': 0, 'rbi': 0, 'bb': 0, 'k': 0, 'sb': 0,
            }
        bs = self.batter_stats[pid]
        bs['ab'] += ab
        bs['r'] += r
        bs['h'] += h
        bs['doubles'] += doubles
        bs['triples'] += triples
        bs['hr'] += hr
        bs['rbi'] += rbi
        bs['bb'] += bb
        bs['k'] += k
        bs['sb'] += sb


def _is_dh_eligible(player_id: int, player_info: dict) -> bool:
    """True if the player has at least one non-P eligible position."""
    positions = player_info.get(player_id, {}).get('eligible_positions', [])
    return any(p != 'P' for p in positions)


def _best_bench_player(bench: list[BatterSlot]) -> BatterSlot | None:
    """Pick the bench player with the most pre-lock PA (most active batter)."""
    if not bench:
        return None
    return max(bench, key=lambda s: s.stats.get('pa', 0) if s.stats else 0)


def _build_team_state(
    lineup: dict,
    player_info: dict,
    batter_stats_map: dict,
    pitcher_stats_map: dict,
    bench_player_ids: list[int],
) -> TeamState:
    sp_id = lineup['sp_player_id']
    sp_info = player_info.get(sp_id, {})
    sp_stats = pitcher_stats_map.get(sp_id)
    sp_slot = PitcherSlot(
        player_id=sp_id,
        throws=sp_info.get('throws', 'R'),
        stats=sp_stats,
        sequence=1,
    )

    batting_order = []
    for entry in lineup['batting_order']:
        pid = entry['player_id']
        pinfo = player_info.get(pid, {})
        slot = BatterSlot(
            batting_position=entry['batting_position'],
            player_id=pid,
            field_position=entry['field_position'],
            bats=pinfo.get('bats', 'R'),
            stats=batter_stats_map.get(pid),
            dh_eligible=_is_dh_eligible(pid, player_info),
        )
        batting_order.append(slot)

    # Build bullpen: pitchers in the batting order who are not the SP
    bullpen: list[PitcherSlot] = []
    for slot in batting_order:
        if slot.field_position == 'P' and slot.player_id != sp_id:
            pinfo = player_info.get(slot.player_id, {})
            bullpen.append(PitcherSlot(
                player_id=slot.player_id,
                throws=pinfo.get('throws', 'R'),
                stats=pitcher_stats_map.get(slot.player_id),
            ))

    # Build bench: roster players not in the batting order, excluding pure pitchers
    in_order = {slot.player_id for slot in batting_order} | {sp_id}
    bench: list[BatterSlot] = []
    for pid in bench_player_ids:
        if pid in in_order:
            continue
        pinfo = player_info.get(pid, {})
        eligible = pinfo.get('eligible_positions', [])
        if not any(p != 'P' for p in eligible):
            continue  # pure pitchers don't pinch-hit
        bench.append(BatterSlot(
            batting_position=0,  # assigned at substitution time
            player_id=pid,
            field_position='',
            bats=pinfo.get('bats', 'R'),
            stats=batter_stats_map.get(pid),
            dh_eligible=True,
        ))

    return TeamState(
        team_id=lineup['team_id'],
        batting_order=batting_order,
        bullpen=bullpen,
        current_pitcher=sp_slot,
        bench=bench,
    )


def _simulate_pa(
    batter_slot: BatterSlot,
    pitcher_slot: PitcherSlot,
    league: LeagueAverages,
    rng: random.Random,
) -> str:
    """Resolve a plate appearance. Returns outcome string."""
    # If batter is at their PA cap, they can no longer bat — caller handles substitution
    probs = pa_probabilities(
        batter_slot.stats,
        pitcher_slot.stats,
        batter_slot.bats,
        pitcher_slot.throws,
        league,
    )
    outcomes = list(probs.keys())
    weights = [probs[o] for o in outcomes]
    return rng.choices(outcomes, weights=weights, k=1)[0]


def _try_steal(runner_id: int, batter_stats: dict | None, rng: random.Random) -> bool | None:
    """Returns True (stolen), False (caught), or None (no attempt)."""
    attempt_rate = sb_attempt_rate(batter_stats)
    if rng.random() > attempt_rate:
        return None
    success_rate = sb_success_rate(batter_stats)
    return rng.random() < success_rate


def simulate_game(
    matchup_id: str,
    home_lineup: dict,
    road_lineup: dict,
    player_info: dict,
    batter_stats_map: dict,
    pitcher_stats_map: dict,
    league: LeagueAverages,
    home_bench_ids: list[int] | None = None,
    road_bench_ids: list[int] | None = None,
    seed: int | None = None,
) -> dict:
    """
    Simulate a full game. Returns a dict with all result data.
    """
    rng = random.Random(seed)

    home = _build_team_state(home_lineup, player_info, batter_stats_map, pitcher_stats_map, home_bench_ids or [])
    road = _build_team_state(road_lineup, player_info, batter_stats_map, pitcher_stats_map, road_bench_ids or [])

    all_events: list[dict] = []
    all_runner_outcomes: list[dict] = []
    seq = 0

    home_runs_by_inning: list[int] = []
    road_runs_by_inning: list[int] = []

    home_score = 0
    road_score = 0

    def _record_line(team: TeamState, inning: int, runs: int, hits: int, errors: int = 0) -> None:
        if inning not in team.line_score:
            team.line_score[inning] = {'r': 0, 'h': 0, 'e': 0}
        team.line_score[inning]['r'] += runs
        team.line_score[inning]['h'] += hits
        team.line_score[inning]['e'] += errors

    def _simulate_half_inning(
        batting_team: TeamState,
        fielding_team: TeamState,
        inning: int,
        half: str,
        walk_off_allowed: bool = False,
    ) -> int:
        nonlocal seq
        outs = 0
        runners: dict[int, int] = {1: 0, 2: 0, 3: 0}  # base -> player_id (0=empty)
        inning_runs = 0
        inning_hits = 0

        # Extra innings: zombie runner on 2nd base
        if inning > 9:
            prev_batter_idx = (batting_team.current_batting_spot - 1) % 9
            zombie_id = batting_team.batting_order[prev_batter_idx].player_id
            runners[2] = zombie_id

        while outs < 3:
            # Walk-off check: home team leads in bottom of 9th+
            if walk_off_allowed and inning_runs + _current_score_delta(batting_team, fielding_team, half, home_score, road_score) > 0:
                break

            batter_slot = batting_team.next_batter()

            # Pinch-hit if batter is at PA cap
            cap = batter_pa_cap(batter_slot.stats)
            if batter_slot.pa_used >= cap and cap != 999:
                sub = _best_bench_player(batting_team.bench)
                if sub is not None:
                    slot_idx = (batting_team.current_batting_spot - 1) % 9
                    batting_team.bench.remove(sub)
                    sub.batting_position = batter_slot.batting_position
                    batting_team.batting_order[slot_idx] = sub
                    out_name = player_info.get(batter_slot.player_id, {}).get('full_name', 'Unknown')
                    sub_name = player_info.get(sub.player_id, {}).get('full_name', 'Unknown')
                    seq += 1
                    all_events.append({
                        'id': str(uuid.uuid4()),
                        'matchup_id': matchup_id,
                        'inning': inning,
                        'half': half,
                        'sequence_number': seq,
                        'event_type': 'substitution',
                        'pitcher_player_id': None,
                        'description': f'{sub_name} pinch hits for {out_name}',
                        'runs_scored': 0,
                        'outs_before_play': outs,
                    })
                    batter_slot = sub

            # Pitcher change check
            if fielding_team.should_change_pitcher():
                old_pitcher_id = fielding_team.current_pitcher.player_id
                new_p = fielding_team.change_pitcher()
                if new_p:
                    # Handle the batting-order slot that was occupied by the outgoing pitcher
                    p_slot_idx = fielding_team.sp_batting_slot_index()
                    if p_slot_idx is not None:
                        if _is_dh_eligible(old_pitcher_id, player_info):
                            # Two-way player: stays in lineup as DH
                            fielding_team.batting_order[p_slot_idx].field_position = 'DH'
                        else:
                            # Pure pitcher: incoming reliever takes the P batting slot
                            old_slot = fielding_team.batting_order[p_slot_idx]
                            new_p_info = player_info.get(new_p.player_id, {})
                            fielding_team.batting_order[p_slot_idx] = BatterSlot(
                                batting_position=old_slot.batting_position,
                                player_id=new_p.player_id,
                                field_position='P',
                                bats=new_p_info.get('bats', 'R'),
                                stats=batter_stats_map.get(new_p.player_id),
                                dh_eligible=_is_dh_eligible(new_p.player_id, player_info),
                            )
                    seq += 1
                    all_events.append({
                        'id': str(uuid.uuid4()),
                        'matchup_id': matchup_id,
                        'inning': inning,
                        'half': half,
                        'sequence_number': seq,
                        'event_type': 'pitching_change',
                        'pitcher_player_id': new_p.player_id,
                        'description': None,
                        'runs_scored': 0,
                        'outs_before_play': outs,
                    })

            outcome = _simulate_pa(batter_slot, fielding_team.current_pitcher, league, rng)
            batter_slot.pa_used += 1

            # Estimate pitches
            pitches = max(1, int(rng.gauss(_AVG_PITCHES_PER_PA, 1.2)))
            fielding_team.current_pitcher.bf_used += 1
            fielding_team.current_pitcher.pitches_used += pitches

            seq += 1
            event_id = str(uuid.uuid4())

            runs_on_play = 0
            is_hit = outcome in ('single', 'double', 'triple', 'hr')
            is_out = outcome in ('k', 'go', 'fo')

            if is_out:
                outs += 1
                fielding_team.record_pitcher(outs=1, k=(1 if outcome == 'k' else 0))
                batting_team.record_batter(batter_slot, ab=1, k=(1 if outcome == 'k' else 0))
            elif outcome == 'bb':
                new_runners, runs_on_play = _advance_runners('bb', runners, outs)
                _apply_batter_to_runners(new_runners, batter_slot.player_id)
                runners = new_runners
                fielding_team.record_pitcher(bb=1)
                batting_team.record_batter(batter_slot, bb=1)
            elif outcome == 'hbp':
                new_runners, runs_on_play = _advance_runners('hbp', runners, outs)
                _apply_batter_to_runners(new_runners, batter_slot.player_id)
                runners = new_runners
                fielding_team.record_pitcher()
                batting_team.record_batter(batter_slot, bb=1)  # bb bucket for HBP (on-base)
            elif is_hit:
                new_runners, runs_on_play = _advance_runners(outcome, runners, outs)
                _apply_batter_to_runners(new_runners, batter_slot.player_id)
                runners = new_runners
                inning_hits += 1
                h_flag = 1
                d_flag = 1 if outcome == 'double' else 0
                t_flag = 1 if outcome == 'triple' else 0
                hr_flag = 1 if outcome == 'hr' else 0
                fielding_team.record_pitcher(
                    h=h_flag, hr=hr_flag,
                    r=runs_on_play, er=runs_on_play,
                )
                batting_team.record_batter(
                    batter_slot, ab=1, h=h_flag,
                    doubles=d_flag, triples=t_flag, hr=hr_flag,
                    rbi=runs_on_play,
                )

            # Attempt stolen base (only if runner on 1st, < 2 outs)
            if runners[1] and outs < 2:
                runner_id = runners[1]
                # Find that batter's stats
                runner_stats = _find_batter_stats(runner_id, batting_team, batter_stats_map)
                sb_result = _try_steal(runner_id, runner_stats, rng)
                if sb_result is True:
                    runners[2] = runner_id
                    runners[1] = 0
                    batting_team.record_batter(_find_slot(runner_id, batting_team), sb=1)
                    seq += 1
                    runner_name = player_info.get(runner_id, {}).get('full_name', 'Unknown')
                    all_events.append({
                        'id': str(uuid.uuid4()),
                        'matchup_id': matchup_id,
                        'inning': inning,
                        'half': half,
                        'sequence_number': seq,
                        'event_type': 'stolen_base',
                        'pitcher_player_id': fielding_team.current_pitcher.player_id,
                        'description': describe_stolen_base(runner_name, rng),
                        'runs_scored': 0,
                        'outs_before_play': outs,
                    })
                elif sb_result is False:
                    runners[1] = 0
                    outs += 1
                    seq += 1
                    runner_name = player_info.get(runner_id, {}).get('full_name', 'Unknown')
                    all_events.append({
                        'id': str(uuid.uuid4()),
                        'matchup_id': matchup_id,
                        'inning': inning,
                        'half': half,
                        'sequence_number': seq,
                        'event_type': 'caught_stealing',
                        'pitcher_player_id': fielding_team.current_pitcher.player_id,
                        'description': describe_caught_stealing(runner_name, rng),
                        'runs_scored': 0,
                        'outs_before_play': outs - 1,
                    })

            inning_runs += runs_on_play

            batter_name = player_info.get(batter_slot.player_id, {}).get('full_name', 'Unknown')
            pitcher_name = player_info.get(fielding_team.current_pitcher.player_id, {}).get('full_name', 'Unknown')
            all_events.append({
                'id': event_id,
                'matchup_id': matchup_id,
                'inning': inning,
                'half': half,
                'sequence_number': seq,
                'event_type': 'plate_appearance',
                'pitcher_player_id': fielding_team.current_pitcher.player_id,
                'description': describe_pa(outcome, batter_name, pitcher_name, rng),
                'runs_scored': runs_on_play,
                'outs_before_play': outs - (1 if is_out else 0),
            })

        _record_line(batting_team, inning, inning_runs, inning_hits)
        return inning_runs

    def _current_score_delta(batting_team, fielding_team, half, hs, rs):
        if half == 'bottom':
            return hs - (rs + 0)  # home leads over road
        return 0

    inning = 1
    max_innings = 18  # safety cap

    while inning <= max_innings:
        # Top half — road bats
        road_inning_runs = _simulate_half_inning(road, home, inning, 'top')
        road_score += road_inning_runs
        road_runs_by_inning.append(road_inning_runs)

        # Bottom half — home bats; walk-off possible in 9th+
        walk_off = inning >= 9
        home_inning_runs = _simulate_half_inning(home, road, inning, 'bottom', walk_off_allowed=walk_off)
        home_score += home_inning_runs
        home_runs_by_inning.append(home_inning_runs)

        # Game over conditions
        if inning >= 9 and home_score != road_score:
            break

        inning += 1

    # Build output data structures
    home_batting_rows = _build_batter_stat_rows(matchup_id, home)
    road_batting_rows = _build_batter_stat_rows(matchup_id, road)
    home_pitching_rows = _build_pitcher_stat_rows(matchup_id, home)
    road_pitching_rows = _build_pitcher_stat_rows(matchup_id, road)
    line_score_rows = _build_line_score_rows(matchup_id, home, road, inning)

    return {
        'events': all_events,
        'runner_outcomes': all_runner_outcomes,
        'batter_stats': home_batting_rows + road_batting_rows,
        'batter_positions': _build_batter_position_rows(matchup_id, home) + _build_batter_position_rows(matchup_id, road),
        'pitcher_stats': home_pitching_rows + road_pitching_rows,
        'line_score': line_score_rows,
        'final_score': {'home': home_score, 'road': road_score},
    }


def _apply_batter_to_runners(runners: dict[int, int], batter_id: int) -> None:
    """Replace placeholder (-1) with actual batter id."""
    for base, pid in list(runners.items()):
        if pid == -1:
            runners[base] = batter_id


def _find_batter_stats(player_id: int, team: TeamState, batter_stats_map: dict) -> dict | None:
    return batter_stats_map.get(player_id)


def _find_slot(player_id: int, team: TeamState) -> BatterSlot:
    for slot in team.batting_order:
        if slot.player_id == player_id:
            return slot
    return team.batting_order[0]  # fallback


def _build_batter_stat_rows(matchup_id: str, team: TeamState) -> list[dict]:
    rows = []
    for pid, stats in team.batter_stats.items():
        rows.append({
            'matchup_id': matchup_id,
            'team_id': team.team_id,
            'player_id': pid,
            **stats,
        })
    return rows


def _build_pitcher_stat_rows(matchup_id: str, team: TeamState) -> list[dict]:
    rows = []
    seq = 1
    for pid, stats in team.pitcher_stats.items():
        rows.append({
            'matchup_id': matchup_id,
            'team_id': team.team_id,
            'player_id': pid,
            'pitching_sequence': seq,
            **stats,
        })
        seq += 1
    return rows


def _build_batter_position_rows(matchup_id: str, team: TeamState) -> list[dict]:
    rows = []
    for slot in team.batting_order:
        pid = slot.ph_player_id or slot.player_id
        rows.append({
            'matchup_id': matchup_id,
            'player_id': pid,
            'position_sequence': 1,
            'field_position': slot.field_position,
        })
    return rows


def _build_line_score_rows(matchup_id: str, home: TeamState, road: TeamState, last_inning: int) -> list[dict]:
    rows = []
    for inning in range(1, last_inning + 1):
        for team in (home, road):
            ls = team.line_score.get(inning, {'r': 0, 'h': 0, 'e': 0})
            rows.append({
                'matchup_id': matchup_id,
                'team_id': team.team_id,
                'inning': inning,
                'runs': ls['r'],
                'hits': ls['h'],
                'errors': ls['e'],
            })
    return rows
