"""Tests for the recap prompt builder."""

import recap


def _player_info():
    return {
        1: {'full_name': 'Shohei Ohtani'},
        2: {'full_name': 'Mookie Betts'},
        10: {'full_name': 'Gerrit Cole'},
        20: {'full_name': 'Jose Ramirez'},
    }


def _event(event_id, inning, half, description, seq=1):
    return {
        'id': event_id,
        'inning': inning,
        'half': half,
        'sequence_number': seq,
        'description': description,
    }


def _build(**overrides):
    defaults = dict(
        home_team_name='Home Squad',
        road_team_name='Road Squad',
        final_score={'home': 5, 'road': 3},
        home_batter_stats=[],
        road_batter_stats=[],
        home_pitcher_stats=[],
        road_pitcher_stats=[],
        events=[],
        runner_outcomes=[],
        player_info={},
    )
    defaults.update(overrides)
    return recap.build_prompt(**defaults)


def test_build_prompt_includes_final_score_with_team_names():
    prompt = _build(final_score={'home': 5, 'road': 3})
    assert 'Road Squad (road) 3, Home Squad (home) 5' in prompt, (
        "the final score line should name both teams, label which is home/road, and match the "
        "road/home score order used everywhere else in the app (road listed first)"
    )


def test_build_prompt_states_home_and_road_team_explicitly():
    prompt = _build()
    assert 'Home team: Home Squad' in prompt and 'Road team: Road Squad' in prompt, (
        "the model should be told outright which roster is home and which is road, rather than "
        "having to infer it solely from the final-score line's ordering"
    )


def test_build_prompt_lists_home_run_as_notable_with_name_and_rbi():
    prompt = _build(
        home_batter_stats=[{'player_id': 1, 'ab': 4, 'h': 1, 'hr': 1, 'rbi': 3}],
        player_info=_player_info(),
    )
    assert 'Shohei Ohtani: 1 HR, 3 RBI' in prompt, (
        "a home run should surface in the notable-performances section, named and with RBI, "
        "since that's the kind of standout line the recap should call out"
    )


def test_build_prompt_lists_multi_hit_game_without_home_run_as_notable():
    prompt = _build(
        road_batter_stats=[{'player_id': 2, 'ab': 4, 'h': 3, 'hr': 0, 'rbi': 1}],
        player_info=_player_info(),
    )
    assert 'Mookie Betts: 3-for-4' in prompt, (
        "a multi-hit game (>=2 hits) should be called out as notable even without a home run, "
        "per the build-plan's 'multi-hit games' example of a notable box score line"
    )


def test_build_prompt_omits_single_hit_batter_from_notable_performances():
    prompt = _build(
        home_batter_stats=[{'player_id': 1, 'ab': 4, 'h': 1, 'hr': 0, 'rbi': 0}],
        player_info=_player_info(),
    )
    assert 'Shohei Ohtani' not in prompt, (
        "an unremarkable single-hit game shouldn't be surfaced as a notable performance — "
        "only home runs and multi-hit games qualify"
    )


def test_build_prompt_includes_pitching_line_with_ip_conversion():
    prompt = _build(
        home_pitcher_stats=[
            {'player_id': 10, 'outs_recorded': 20, 'h': 4, 'r': 1, 'er': 1, 'bb': 2, 'k': 9},
        ],
        player_info=_player_info(),
    )
    assert 'Gerrit Cole: 6.2 IP' in prompt, (
        "outs_recorded should convert to the standard baseball notation (whole innings dot "
        "remaining outs), e.g. 20 outs = 6.2 IP, not a raw out count"
    )


def test_build_prompt_says_no_notable_performances_when_none_qualify():
    prompt = _build()
    assert 'Home Squad:\nNone' in prompt and 'Road Squad:\nNone' in prompt, (
        "with no qualifying batting or pitching lines for a team, its notable-performances "
        "section should explicitly say so rather than leaving a blank the model might fill in"
    )


def test_build_prompt_labels_notable_performances_by_team():
    prompt = _build(
        home_batter_stats=[{'player_id': 1, 'ab': 4, 'h': 1, 'hr': 1, 'rbi': 3}],
        road_batter_stats=[{'player_id': 2, 'ab': 4, 'h': 3, 'hr': 0, 'rbi': 1}],
        player_info=_player_info(),
    )
    home_section = prompt.split('Home Squad:\n', 1)[1]
    assert 'Shohei Ohtani' in home_section.split('\n\n')[0], (
        "Ohtani's home-run line is a home-team stat and should appear under the 'Home Squad:' "
        "header, not lumped into an undifferentiated list"
    )
    road_section = prompt.split('Road Squad:\n', 1)[1]
    assert 'Mookie Betts' in road_section.split('\n\n')[0], (
        "Betts's multi-hit line is a road-team stat and should appear under the 'Road Squad:' "
        "header, so the model knows which roster produced which performance"
    )


def test_build_prompt_labels_play_by_play_with_half_inning_and_batting_team():
    prompt = _build(
        events=[_event('e1', 1, 'top', 'Jose Ramirez singles to left field')],
        player_info=_player_info(),
    )
    assert 'Top 1 (Road Squad batting):' in prompt, (
        "each play-by-play line should be grouped under a half-inning header naming which team "
        "is batting, since the top half is always the road team by convention — without it the "
        "model has to guess which inning (and which side) an event happened in"
    )
    assert 'Jose Ramirez singles to left field' in prompt


def test_build_prompt_labels_bottom_half_as_home_team_batting():
    prompt = _build(
        events=[_event('e1', 3, 'bottom', 'Shohei Ohtani homers to left')],
        player_info=_player_info(),
    )
    assert 'Bottom 3 (Home Squad batting):' in prompt, (
        "the bottom half is always the home team batting — the header should say so explicitly "
        "rather than leaving the reader (or model) to infer it"
    )


def test_build_prompt_includes_baserunning_notes_attached_to_their_event():
    prompt = _build(
        events=[_event('e1', 1, 'top', 'Jose Ramirez singles to left field')],
        runner_outcomes=[
            {
                'sim_event_id': 'e1',
                'description': 'Mookie Betts advances to third base',
                'narration_sequence': 0,
            },
        ],
        player_info=_player_info(),
    )
    assert 'Jose Ramirez singles to left field. Mookie Betts advances to third base.' in prompt, (
        "baserunner-advancement notes live in a separate table (sim_event_runner_outcomes) from "
        "the plate-appearance description, but the recap prompt should merge them onto the same "
        "line — otherwise the play-by-play silently drops every non-batter base advance, forcing "
        "the model to fabricate or ignore what happened to existing runners"
    )


def test_build_prompt_orders_baserunning_notes_by_narration_sequence():
    prompt = _build(
        events=[_event('e1', 1, 'bottom', 'Shohei Ohtani hits a double down the left field line')],
        runner_outcomes=[
            {'sim_event_id': 'e1', 'description': 'Jose Ramirez scores from second base', 'narration_sequence': 1},
            {'sim_event_id': 'e1', 'description': 'Mookie Betts scores from third base', 'narration_sequence': 0},
        ],
        player_info=_player_info(),
    )
    assert 'Mookie Betts scores from third base. Jose Ramirez scores from second base' in prompt, (
        "runner notes must render in narration_sequence order (closest-to-home first, per the "
        "sim engine), not insertion order, to match the sequencing already used elsewhere (e.g. "
        "the API's Play-by-Play tab query orders by narration_sequence)"
    )


def test_build_prompt_says_play_by_play_not_available_when_no_events():
    prompt = _build()
    assert 'Play-by-play:\nNot available' in prompt, (
        "with no events, the prompt should explicitly say play-by-play is unavailable rather "
        "than leaving a blank section"
    )
