"""
Shared vocabulary of plate-appearance outcomes.

This module is the single source of truth for the *identity* of a PA outcome.
It deliberately depends on nothing else in the package, so every layer can
import it without creating a cycle:

    stats  ──emits──▶  Outcome probabilities
    engine ──routes─▶  on the Outcome
    text_gen ─renders▶ the Outcome as prose

Only *identity* (and the classification that follows from it) lives here.
*Behavior* stays with the consumer that owns it — baserunner advancement and
stat bucketing in the engine, play-by-play templates in text_gen — because
those pull in dependencies (TeamState, RNG, template tables) that have no place
in a shared leaf module.

Outcome subclasses ``str`` so members serialize as their canonical keys and stay
compatible with existing string-keyed data (DB rows, JSON, tests): at runtime
``Outcome.HR == 'hr'``. Static type checkers still treat ``Outcome`` as a
distinct type, so a bare ``str`` won't satisfy an ``Outcome`` annotation — the
mixin buys runtime compatibility without giving up compile-time safety.
"""

from enum import Enum


class Outcome(str, Enum):
    BB = 'bb'
    HBP = 'hbp'
    K = 'k'
    SINGLE = 'single'
    DOUBLE = 'double'
    TRIPLE = 'triple'
    HR = 'hr'
    GO = 'go'
    FO = 'fo'

    @property
    def is_out(self) -> bool:
        return self in _OUTS

    @property
    def is_hit(self) -> bool:
        return self in _HITS


# Classification is a fact about the *identity*, not behavior, so it belongs
# here where both the engine and any other consumer can rely on it.
_OUTS = frozenset({Outcome.K, Outcome.GO, Outcome.FO})
_HITS = frozenset({Outcome.SINGLE, Outcome.DOUBLE, Outcome.TRIPLE, Outcome.HR})
