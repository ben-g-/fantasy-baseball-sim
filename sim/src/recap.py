"""Builds the prompt sent to the LLM client wrapper to generate a game recap."""


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


def build_prompt(
    home_team_name: str,
    road_team_name: str,
    final_score: dict,
    home_batter_stats: list[dict],
    road_batter_stats: list[dict],
    home_pitcher_stats: list[dict],
    road_pitcher_stats: list[dict],
    play_by_play: list[str],
    player_info: dict,
) -> str:
    """Build a single-turn prompt summarizing a completed sim's structured results."""
    notable = (
        _notable_batting_lines(home_batter_stats, player_info)
        + _notable_batting_lines(road_batter_stats, player_info)
        + _notable_pitching_lines(home_pitcher_stats, player_info)
        + _notable_pitching_lines(road_pitcher_stats, player_info)
    )
    notable_text = '\n'.join(notable) if notable else 'None'
    pbp_text = '\n'.join(play_by_play) if play_by_play else 'Not available'

    return (
        'You are a sportswriter producing a short recap of a simulated baseball game '
        'between two fantasy baseball rosters.\n\n'
        f'Final score: {road_team_name} {final_score["road"]}, {home_team_name} {final_score["home"]}\n\n'
        f'Notable performances:\n{notable_text}\n\n'
        f'Play-by-play:\n{pbp_text}\n\n'
        'Write a 2-4 paragraph narrative recap of this game in sportswriter style. '
        'Focus on the final score, the standout performances, and the flow of the game. '
        'Do not invent any statistics or events not present above.'
    )
