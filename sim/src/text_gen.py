"""Template-based play-by-play description generator."""

import random

from outcomes import Outcome

_SINGLE_TEMPLATES = [
    "{batter} singles to {location}",
    "{batter} lines a single to {location}",
    "{batter} hits a ground ball single to {location}",
]
_DOUBLE_TEMPLATES = [
    "{batter} doubles to {location}",
    "{batter} hits a double down the {location} line",
    "{batter} gaps a double to {location}",
]
_TRIPLE_TEMPLATES = [
    "{batter} triples to {location}",
    "{batter} hits a triple to {location}",
]
_HR_TEMPLATES = [
    "{batter} hits a home run",
    "{batter} homers to {location}",
    "{batter} launches a home run",
]
_BB_TEMPLATES = [
    "{batter} walks",
    "{pitcher} walks {batter}",
]
_HBP_TEMPLATES = [
    "{batter} is hit by a pitch",
]
_K_TEMPLATES = [
    "{batter} strikes out",
    "{pitcher} strikes out {batter}",
    "{batter} strikes out swinging",
    "{batter} called out on strikes",
]
_GO_TEMPLATES = [
    "{batter} grounds out",
    "{batter} grounds into an out",
    "{batter} hits a groundball out",
]
_FO_TEMPLATES = [
    "{batter} flies out",
    "{batter} pops out",
    "{batter} hits a flyball out",
]
_SB_TEMPLATES = [
    "{runner} steals second base",
    "{runner} steals a base",
]
_CS_TEMPLATES = [
    "{runner} is caught stealing",
    "{runner} is thrown out trying to steal",
]

_OUTFIELD_LOCATIONS = ["left field", "center field", "right field", "left-center", "right-center"]
_INFIELD_LOCATIONS = ["left", "right", "center"]
_LINE_LOCATIONS = ["left field", "right field"]


def _rng_choice(rng: random.Random, templates: list[str]) -> str:
    return rng.choice(templates)


def describe_pa(
    outcome: Outcome,
    batter_name: str,
    pitcher_name: str,
    rng: random.Random,
) -> str:
    loc_of = rng.choice(_OUTFIELD_LOCATIONS)
    loc_if = rng.choice(_INFIELD_LOCATIONS)

    if outcome is Outcome.SINGLE:
        tmpl = _rng_choice(rng, _SINGLE_TEMPLATES)
        return tmpl.format(batter=batter_name, location=loc_of)
    if outcome is Outcome.DOUBLE:
        tmpl = _rng_choice(rng, _DOUBLE_TEMPLATES)
        return tmpl.format(batter=batter_name, location=rng.choice(_LINE_LOCATIONS))
    if outcome is Outcome.TRIPLE:
        tmpl = _rng_choice(rng, _TRIPLE_TEMPLATES)
        return tmpl.format(batter=batter_name, location=loc_of)
    if outcome is Outcome.HR:
        tmpl = _rng_choice(rng, _HR_TEMPLATES)
        return tmpl.format(batter=batter_name, location=loc_of)
    if outcome is Outcome.BB:
        tmpl = _rng_choice(rng, _BB_TEMPLATES)
        return tmpl.format(batter=batter_name, pitcher=pitcher_name)
    if outcome is Outcome.HBP:
        return _rng_choice(rng, _HBP_TEMPLATES).format(batter=batter_name)
    if outcome is Outcome.K:
        tmpl = _rng_choice(rng, _K_TEMPLATES)
        return tmpl.format(batter=batter_name, pitcher=pitcher_name)
    if outcome is Outcome.GO:
        return _rng_choice(rng, _GO_TEMPLATES).format(batter=batter_name)
    if outcome is Outcome.FO:
        return _rng_choice(rng, _FO_TEMPLATES).format(batter=batter_name)
    return f"{batter_name} — {outcome}"


def describe_stolen_base(runner_name: str, rng: random.Random) -> str:
    return _rng_choice(rng, _SB_TEMPLATES).format(runner=runner_name)


def describe_caught_stealing(runner_name: str, rng: random.Random) -> str:
    return _rng_choice(rng, _CS_TEMPLATES).format(runner=runner_name)
