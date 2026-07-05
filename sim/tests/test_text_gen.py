"""Tests for sim/src/text_gen.py's baserunner narration."""

from outcomes import Outcome
from text_gen import describe_runner_outcome


def test_describe_runner_outcome_advances():
    text = describe_runner_outcome(
        outcome=Outcome.SINGLE,
        base_before=1,
        final_base=3,
        ends_half_inning=False,
    )
    assert text == 'advances to third base', (
        'a runner whose base changed (but did not score) should be narrated as advancing to the new base; the '
        "runner's name is rendered separately by the caller, not baked into this clause"
    )


def test_describe_runner_outcome_scores():
    text = describe_runner_outcome(
        outcome=Outcome.DOUBLE,
        base_before=2,
        final_base=4,
        ends_half_inning=False,
    )
    assert text == 'scores from second base', (
        'a runner whose final base is 4 (home) should be narrated as scoring from their prior base'
    )


def test_describe_runner_outcome_holds_on_hit():
    text = describe_runner_outcome(
        outcome=Outcome.SINGLE,
        base_before=2,
        final_base=2,
        ends_half_inning=False,
    )
    assert text == 'holds at second base', (
        'a runner who did not advance on a hit should still be narrated, since an advance would typically be expected'
    )


def test_describe_runner_outcome_holds_on_non_inning_ending_groundout():
    text = describe_runner_outcome(
        outcome=Outcome.GO,
        base_before=2,
        final_base=2,
        ends_half_inning=False,
    )
    assert text == 'holds at second base', (
        'a groundout that does not end the half-inning would typically advance a runner, so a non-advance should be narrated'
    )


def test_describe_runner_outcome_silent_on_inning_ending_groundout():
    text = describe_runner_outcome(
        outcome=Outcome.GO,
        base_before=2,
        final_base=2,
        ends_half_inning=True,
    )
    assert text is None, (
        'a groundout that ends the half-inning (e.g. the third out via a double play) is not expected to advance '
        'any runner, so a non-advance should not be narrated'
    )


def test_describe_runner_outcome_silent_on_strikeout():
    text = describe_runner_outcome(
        outcome=Outcome.K,
        base_before=1,
        final_base=1,
        ends_half_inning=False,
    )
    assert text is None, 'a strikeout never advances a runner, so staying put is expected and should not be narrated'


def test_describe_runner_outcome_silent_on_flyout():
    text = describe_runner_outcome(
        outcome=Outcome.FO,
        base_before=3,
        final_base=3,
        ends_half_inning=False,
    )
    assert text is None, (
        'a fly-out carries no depth information and most fly balls do not advance a runner in reality, so a '
        'non-advance on a fly-out should not be narrated'
    )


def test_describe_runner_outcome_silent_on_unforced_walk_stay():
    text = describe_runner_outcome(
        outcome=Outcome.BB,
        base_before=3,
        final_base=3,
        ends_half_inning=False,
    )
    assert text is None, (
        'a runner left unforced on a walk is not expected to advance, so staying put should not be narrated'
    )
