"""Builds the prompt sent to the LLM client wrapper to generate a game recap."""

_HALF_LABELS = {'top': 'Top', 'bottom': 'Bottom'}


def _player_name(player_id: int, player_info: dict) -> str:
    return player_info.get(player_id, {}).get('full_name', f'Player {player_id}')


def _notable_batting_lines(batter_stats: list[dict], player_info: dict) -> list[str]:
    lines = []
    for b in batter_stats:
        name = _player_name(b['player_id'], player_info)
        if b['hr'] > 0:
            lines.append(f"{name}: {b['hr']} HR, {b['rbi']} RBI, {b['h']}-for-{b['ab']}")
        elif b['h'] >= 2:
            lines.append(f"{name}: {b['h']}-for-{b['ab']}, {b['rbi']} RBI")
    return lines


def _notable_pitching_lines(pitcher_stats: list[dict], player_info: dict) -> list[str]:
    lines = []
    for p in pitcher_stats:
        name = _player_name(p['player_id'], player_info)
        ip = f"{p['outs_recorded'] // 3}.{p['outs_recorded'] % 3}"
        lines.append(f"{name}: {ip} IP, {p['h']} H, {p['er']} ER, {p['bb']} BB, {p['k']} K")
    return lines


def _team_section(team_name: str, lines: list[str]) -> str:
    body = '\n'.join(lines) if lines else 'None'
    return f'{team_name}:\n{body}'


def _batting_team_name(half: str, home_team_name: str, road_team_name: str) -> str:
    """Road always bats in the top half, home in the bottom — a fixed convention (see
    engine.py's simulate_game loop), not something derived per-matchup."""
    return home_team_name if half == 'bottom' else road_team_name


def build_play_by_play_text(
    events: list[dict],
    runner_outcomes: list[dict],
    home_team_name: str,
    road_team_name: str,
) -> str:
    """Render events in order, grouped under half-inning headers, with each event's
    own description followed by any baserunner-advancement notes tied to it — mirroring
    how the API assembles the Play-by-Play tab (event description + runner_notes)."""
    notes_by_event_id: dict[str, list[str]] = {}
    narrated = sorted(
        (r for r in runner_outcomes if r.get('description')),
        key=lambda r: r['narration_sequence'],
    )
    for r in narrated:
        notes_by_event_id.setdefault(r['sim_event_id'], []).append(r['description'])

    lines = []
    current_half = None
    for e in events:
        if not e.get('description'):
            continue
        half_key = (e['inning'], e['half'])
        if half_key != current_half:
            current_half = half_key
            batting_team = _batting_team_name(e['half'], home_team_name, road_team_name)
            lines.append(f"{_HALF_LABELS[e['half']]} {e['inning']} ({batting_team} batting):")
        notes = notes_by_event_id.get(e['id'], [])
        sentence = '. '.join([e['description'], *notes])
        lines.append(f'  {sentence}.')

    return '\n'.join(lines) if lines else 'Not available'


def build_prompt(
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
    """Build a single-turn prompt summarizing a completed sim's structured results."""
    home_notable = (
        _notable_batting_lines(home_batter_stats, player_info)
        + _notable_pitching_lines(home_pitcher_stats, player_info)
    )
    road_notable = (
        _notable_batting_lines(road_batter_stats, player_info)
        + _notable_pitching_lines(road_pitcher_stats, player_info)
    )
    notable_text = '\n\n'.join([
        _team_section(home_team_name, home_notable),
        _team_section(road_team_name, road_notable),
    ])
    pbp_text = build_play_by_play_text(events, runner_outcomes, home_team_name, road_team_name)

    return (
        'You are a sportswriter producing a short recap of a simulated baseball game '
        'between two fantasy baseball rosters.\n\n'
        f'Home team: {home_team_name}\n'
        f'Road team: {road_team_name}\n\n'
        f'Final score: {road_team_name} (road) {final_score["road"]}, '
        f'{home_team_name} (home) {final_score["home"]}\n\n'
        f'Notable performances:\n{notable_text}\n\n'
        f'Play-by-play:\n{pbp_text}\n\n'
        'Write a 2-4 paragraph narrative recap of this game in sportswriter style. '
        'Focus on the final score, the standout performances, and the flow of the game. '
        'Do not invent any statistics or events not present above.'
    )
