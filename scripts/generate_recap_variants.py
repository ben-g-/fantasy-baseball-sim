"""
Generates a game recap for a completed matchup already in Supabase, using
either the "filtered" (notable lines only) or "full" (entire box score)
batting/pitching summary in the prompt — for eyeballing recap quality
side by side before committing to one approach.

This is a comparison tool, not part of the production recap pipeline: it
never writes to sim_recaps.

Usage: python scripts/generate_recap_variants.py --matchup-id <id> --variant filtered|full

Requires .env with SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ANTHROPIC_API_KEY.
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'sim' / 'src'))
import llm_client  # noqa: E402
import recap  # noqa: E402

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_SERVICE_ROLE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']


def _player_name(player_id: int, player_info: dict) -> str:
    return player_info.get(player_id, {}).get('full_name', f'Player {player_id}')


def _full_batting_lines(batter_stats: list[dict], player_info: dict) -> list[str]:
    lines = []
    for b in batter_stats:
        name = _player_name(b['player_id'], player_info)
        lines.append(
            f"{name}: {b['ab']} AB, {b['r']} R, {b['h']} H, {b['doubles']} 2B, "
            f"{b['triples']} 3B, {b['hr']} HR, {b['rbi']} RBI, {b['bb']} BB, {b['k']} K, {b['sb']} SB"
        )
    return lines


def _full_pitching_lines(pitcher_stats: list[dict], player_info: dict) -> list[str]:
    lines = []
    for p in pitcher_stats:
        name = _player_name(p['player_id'], player_info)
        ip = f"{p['outs_recorded'] // 3}.{p['outs_recorded'] % 3}"
        lines.append(f"{name}: {ip} IP, {p['h']} H, {p['r']} R, {p['er']} ER, {p['bb']} BB, {p['k']} K")
    return lines


def build_full_box_score_prompt(
    home_team_name: str,
    road_team_name: str,
    final_score: dict,
    home_batter_stats: list[dict],
    road_batter_stats: list[dict],
    home_pitcher_stats: list[dict],
    road_pitcher_stats: list[dict],
    events: list[dict],
    runner_outcomes: list[dict],
    player_info: dict,
) -> str:
    """Same shape as recap.build_prompt, but with every batter/pitcher line
    included instead of a pre-filtered "notable" subset — for comparison."""
    home_lines = _full_batting_lines(home_batter_stats, player_info) + _full_pitching_lines(home_pitcher_stats, player_info)
    road_lines = _full_batting_lines(road_batter_stats, player_info) + _full_pitching_lines(road_pitcher_stats, player_info)
    box_score_text = '\n\n'.join([
        f'{home_team_name}:\n' + ('\n'.join(home_lines) if home_lines else 'None'),
        f'{road_team_name}:\n' + ('\n'.join(road_lines) if road_lines else 'None'),
    ])
    pbp_text = recap.build_play_by_play_text(events, runner_outcomes, home_team_name, road_team_name)

    return (
        'You are a sportswriter producing a short recap of a simulated baseball game '
        'between two fantasy baseball rosters.\n\n'
        f'Home team: {home_team_name}\n'
        f'Road team: {road_team_name}\n\n'
        f'Final score: {road_team_name} (road) {final_score["road"]}, '
        f'{home_team_name} (home) {final_score["home"]}\n\n'
        f'Box score:\n{box_score_text}\n\n'
        f'Play-by-play:\n{pbp_text}\n\n'
        'Write a 2-4 paragraph narrative recap of this game in sportswriter style. '
        'Focus on the final score, the standout performances, and the flow of the game. '
        'Do not invent any statistics or events not present above.'
    )


def fetch_matchup_data(client, matchup_id: str) -> dict:
    matchup = client.table('matchups').select(
        'id, home_team_id, road_team_id, sim_status'
    ).eq('id', matchup_id).single().execute().data

    if matchup['sim_status'] != 'sim_complete':
        raise SystemExit(
            f"Matchup {matchup_id} has sim_status '{matchup['sim_status']}', not 'sim_complete'."
        )

    home_team_id = matchup['home_team_id']
    road_team_id = matchup['road_team_id']

    teams = client.table('teams').select('id, name').in_('id', [home_team_id, road_team_id]).execute().data
    team_names = {t['id']: t['name'] for t in teams}

    line_score = client.table('sim_line_score').select('team_id, runs').eq('matchup_id', matchup_id).execute().data
    final_score = {'home': 0, 'road': 0}
    for row in line_score:
        if row['team_id'] == home_team_id:
            final_score['home'] += row['runs']
        elif row['team_id'] == road_team_id:
            final_score['road'] += row['runs']

    batter_stats = client.table('sim_batter_stats').select(
        'team_id, player_id, ab, r, h, doubles, triples, hr, rbi, bb, k, sb'
    ).eq('matchup_id', matchup_id).execute().data

    pitcher_stats = client.table('sim_pitcher_stats').select(
        'team_id, player_id, pitching_sequence, outs_recorded, h, r, er, bb, k'
    ).eq('matchup_id', matchup_id).order('pitching_sequence').execute().data

    events = client.table('sim_events').select(
        'id, inning, half, sequence_number, description'
    ).eq('matchup_id', matchup_id).order('sequence_number').execute().data

    event_ids = [e['id'] for e in events]
    runner_outcomes = (
        client.table('sim_event_runner_outcomes')
        .select('sim_event_id, description, narration_sequence')
        .in_('sim_event_id', event_ids)
        .execute()
        .data
        if event_ids else []
    )

    player_ids = list({r['player_id'] for r in batter_stats} | {r['player_id'] for r in pitcher_stats})
    players = client.table('players').select('mlb_id, full_name').in_('mlb_id', player_ids).execute().data
    player_info = {p['mlb_id']: {'full_name': p['full_name']} for p in players}

    return {
        'home_team_name': team_names.get(home_team_id, 'Home'),
        'road_team_name': team_names.get(road_team_id, 'Road'),
        'final_score': final_score,
        'home_batter_stats': [b for b in batter_stats if b['team_id'] == home_team_id],
        'road_batter_stats': [b for b in batter_stats if b['team_id'] == road_team_id],
        'home_pitcher_stats': [p for p in pitcher_stats if p['team_id'] == home_team_id],
        'road_pitcher_stats': [p for p in pitcher_stats if p['team_id'] == road_team_id],
        'events': events,
        'runner_outcomes': runner_outcomes,
        'player_info': player_info,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matchup-id', required=True)
    parser.add_argument('--variant', required=True, choices=['filtered', 'full'])
    args = parser.parse_args()

    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    data = fetch_matchup_data(client, args.matchup_id)

    build_fn = recap.build_prompt if args.variant == 'filtered' else build_full_box_score_prompt
    prompt = build_fn(
        home_team_name=data['home_team_name'],
        road_team_name=data['road_team_name'],
        final_score=data['final_score'],
        home_batter_stats=data['home_batter_stats'],
        road_batter_stats=data['road_batter_stats'],
        home_pitcher_stats=data['home_pitcher_stats'],
        road_pitcher_stats=data['road_pitcher_stats'],
        events=data['events'],
        runner_outcomes=data['runner_outcomes'],
        player_info=data['player_info'],
    )

    print(f"=== Matchup {args.matchup_id}: {data['road_team_name']} at {data['home_team_name']} ===")
    print(f"Final score: {data['road_team_name']} {data['final_score']['road']}, "
          f"{data['home_team_name']} {data['final_score']['home']}")
    print(f'Variant: {args.variant}')
    print()
    print(f'--- Prompt ({len(prompt)} chars, ~{len(prompt) // 4} tokens est.) ---')
    print(prompt)
    print()
    print('--- Recap ---')
    print(llm_client.generate_text(prompt))


if __name__ == '__main__':
    main()
