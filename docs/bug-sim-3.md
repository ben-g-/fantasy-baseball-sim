# bug-sim-3: Platoon probability model does not match the specified algorithm

**Severity:** Medium
**Component:** Sim engine (stats)
**Status:** Open

## Summary

The plate-appearance probability model feeds pre-lock platoon **split rates** directly
into the log5 combination. The spec calls for a two-step process: derive a platoon
*adjustment factor* from the pre-lock splits, apply it to the post-lock (true-talent)
rates, and only then combine via log5.

## Spec references

- `specs/build-plan.md` Phase 5, plate-appearance resolution:
  > "first apply platoon adjustment factors to the batter's and pitcher's post-lock
  > rates independently — the batter's rates are adjusted using their pre-lock vs. LHP
  > or vs. RHP splits … The adjustment factor for each outcome is the ratio of the
  > relevant pre-lock split rate to the pre-lock overall rate. The platoon-adjusted
  > rates are then combined via a log5-style formula … Applying platoon adjustments
  > before log5 ensures the combination operates on true-talent estimates that already
  > reflect the handedness matchup."

## Location

- `sim/src/stats.py:82-116` — `_batter_rates` / `_pitcher_rates`
- `sim/src/stats.py:156-182` — `pa_probabilities`

## Details

`_batter_rates(stats, pitcher_throws)` selects the `vs_lhp_*` or `vs_rhp_*` split and
returns those rates directly (with a small-sample blend toward league average).
`pa_probabilities` then log5-combines the batter split rate, the pitcher split rate, and
the league average.

The spec's intended computation is different:

```
adjustment_factor(outcome) = pre_lock_split_rate(outcome) / pre_lock_overall_rate(outcome)
adjusted_rate(outcome)     = post_lock_overall_rate(outcome) * adjustment_factor(outcome)
p(outcome)                 = log5(adjusted_batter_rate, adjusted_pitcher_rate, league_rate)
```

Two differences:

1. No adjustment-factor **ratio** is computed; the split rate is used as the operand.
2. The base being adjusted should be the **post-lock** rate (true talent for this week),
   not the pre-lock split. This is coupled to `bug-sim-2` (post-lock stats not wired).

## Expected vs actual

| Step | Expected | Actual |
|---|---|---|
| Platoon signal | ratio (split ÷ overall), pre-lock | raw split rate, pre-lock |
| Base rate adjusted | post-lock overall | none (split used directly) |
| Combination | log5 of adjusted rates | log5 of raw split rates |

## Suggested fix

Implement the factor-then-log5 pipeline once post-lock stats are available (`bug-sim-2`):

1. Compute pre-lock overall rates and pre-lock split rates; the per-outcome factor is
   their ratio (guard against divide-by-zero / tiny denominators).
2. Multiply the post-lock overall rates by those factors, per side, then renormalize.
3. log5-combine the adjusted batter and pitcher rates against the league average.

Keep the existing small-sample blending for the ratio inputs.

## Verification

Unit-test the adjustment factor in isolation (e.g. a batter with a strong vs-LHP split
should have factor > 1 for hits vs LHP) and confirm `pa_probabilities` still returns a
normalized distribution summing to 1.0.
