"""Tests for the recap prompt builder."""

import recap


def _player_info():
    return {
        1: {'full_name': 'Shohei Ohtani'},
        2: {'full_name': 'Mookie Betts'},
        10: {'full_name': 'Gerrit Cole'},
    }


def test_build_prompt_includes_final_score_with_team_names():
    prompt = recap.build_prompt(
        home_team_name='Home Squad',
        road_team_name='Road Squad',
        final_score={'home': 5, 'road': 3},
        home_batter_stats=[],
        road_batter_stats=[],
        home_pitcher_stats=[],
        road_pitcher_stats=[],
        play_by_play=[],
        player_info={},
    )
    assert 'Road Squad 3, Home Squad 5' in prompt, (
        "the final score line should name both teams and match the road/home score order "
        "used everywhere else in the app (road listed first)"
    )


def test_build_prompt_lists_home_run_as_notable_with_name_and_rbi():
    prompt = recap.build_prompt(
        home_team_name='Home Squad',
        road_team_name='Road Squad',
        final_score={'home': 4, 'road': 0},
        home_batter_stats=[
            {'player_id': 1, 'ab': 4, 'h': 1, 'hr': 1, 'rbi': 3},
        ],
        road_batter_stats=[],
        home_pitcher_stats=[],
        road_pitcher_stats=[],
        play_by_play=[],
        player_info=_player_info(),
    )
    assert 'Shohei Ohtani: 1 HR, 3 RBI' in prompt, (
        "a home run should surface in the notable-performances section, named and with RBI, "
        "since that's the kind of standout line the recap should call out"
    )


def test_build_prompt_lists_multi_hit_game_without_home_run_as_notable():
    prompt = recap.build_prompt(
        home_team_name='Home Squad',
        road_team_name='Road Squad',
        final_score={'home': 2, 'road': 1},
        home_batter_stats=[],
        road_batter_stats=[
            {'player_id': 2, 'ab': 4, 'h': 3, 'hr': 0, 'rbi': 1},
        ],
        home_pitcher_stats=[],
        road_pitcher_stats=[],
        play_by_play=[],
        player_info=_player_info(),
    )
    assert 'Mookie Betts: 3-for-4' in prompt, (
        "a multi-hit game (>=2 hits) should be called out as notable even without a home run, "
        "per the build-plan's 'multi-hit games' example of a notable box score line"
    )


def test_build_prompt_omits_single_hit_batter_from_notable_performances():
    prompt = recap.build_prompt(
        home_team_name='Home Squad',
        road_team_name='Road Squad',
        final_score={'home': 2, 'road': 1},
        home_batter_stats=[
            {'player_id': 1, 'ab': 4, 'h': 1, 'hr': 0, 'rbi': 0},
        ],
        road_batter_stats=[],
        home_pitcher_stats=[],
        road_pitcher_stats=[],
        play_by_play=[],
        player_info=_player_info(),
    )
    assert 'Shohei Ohtani' not in prompt, (
        "an unremarkable single-hit game shouldn't be surfaced as a notable performance — "
        "only home runs and multi-hit games qualify"
    )


def test_build_prompt_includes_pitching_line_with_ip_conversion():
    prompt = recap.build_prompt(
        home_team_name='Home Squad',
        road_team_name='Road Squad',
        final_score={'home': 2, 'road': 1},
        home_batter_stats=[],
        road_batter_stats=[],
        home_pitcher_stats=[
            {'player_id': 10, 'outs_recorded': 20, 'h': 4, 'r': 1, 'er': 1, 'bb': 2, 'k': 9},
        ],
        road_pitcher_stats=[],
        play_by_play=[],
        player_info=_player_info(),
    )
    assert 'Gerrit Cole: 6.2 IP' in prompt, (
        "outs_recorded should convert to the standard baseball notation (whole innings dot "
        "remaining outs), e.g. 20 outs = 6.2 IP, not a raw out count"
    )


def test_build_prompt_includes_play_by_play_descriptions_verbatim():
    prompt = recap.build_prompt(
        home_team_name='Home Squad',
        road_team_name='Road Squad',
        final_score={'home': 1, 'road': 0},
        home_batter_stats=[],
        road_batter_stats=[],
        home_pitcher_stats=[],
        road_pitcher_stats=[],
        play_by_play=['Shohei Ohtani homers to left'],
        player_info=_player_info(),
    )
    assert 'Shohei Ohtani homers to left' in prompt, (
        "the play-by-play text already produced by the text-generation step should be passed "
        "through to the prompt unmodified, per the build-plan's task description"
    )


def test_build_prompt_says_no_notable_performances_when_none_qualify():
    prompt = recap.build_prompt(
        home_team_name='Home Squad',
        road_team_name='Road Squad',
        final_score={'home': 1, 'road': 0},
        home_batter_stats=[],
        road_batter_stats=[],
        home_pitcher_stats=[],
        road_pitcher_stats=[],
        play_by_play=[],
        player_info={},
    )
    assert 'Notable performances:\nNone' in prompt, (
        "with no qualifying batting or pitching lines, the prompt should explicitly say so "
        "rather than leaving a blank section the model might try to fill in on its own"
    )
