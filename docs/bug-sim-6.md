# bug-sim-6: Plate-appearance event sequencing is corrupted by post-PA steal events

**Severity:** Medium
**Component:** Sim engine
**Status:** Open

## Summary

The plate-appearance event is appended to the log *after* any stolen-base/caught-stealing
event from the same iteration, and it reuses the current `seq` counter rather than the
value reserved when the PA began. This can give a steal and its own PA the same or an
inverted `sequence_number`, and lets the PA's `outs_before_play` include a caught-stealing
out that logically happened afterward. Both break the chronological play-by-play.

## Spec references

- `specs/data-model.md` §sim_events — `sequence_number` is "Ordering within the
  half-inning"; `outs_before_play` is "0, 1, or 2".
- `specs/mini-prd-lineup-and-sim.md` §Post-Sim Mode, Play-by-Play — "Chronological text
  feed of every at-bat outcome, grouped by half-inning."

## Location

- `sim/engine.py:453-532` — PA resolution, steal handling, and the deferred PA-event append

## Details

Within one batting iteration the code does, in order:

1. `seq += 1; event_id = str(uuid.uuid4())` — reserves a sequence value and an id for the PA.
2. Resolves the outcome and updates `outs`.
3. Steal block: on a stolen base or caught stealing, `seq += 1` and appends that event
   immediately (caught stealing also does `outs += 1`).
4. Appends the PA event **last**, reading the *current* `seq` (not the value reserved in
   step 1) and computing `outs_before_play = outs - (1 if is_out else 0)`.

Because the PA event is appended after the steal event and reads the mutated `seq`:

- The steal event and the PA event can carry the same `sequence_number`, or the steal can
  sort *before* the PA that produced the baserunner ("X steals 2nd" before "X singles").
- `outs_before_play` on the PA can be inflated by a caught-stealing out that occurred
  after the PA outcome.

The same "append PA last, read current `seq`" pattern also interacts with `substitution`
and `pitching_change` events emitted earlier in the iteration, so the PA event's
`sequence_number` is generally not the value reserved for it.

## Expected vs actual

| | Expected | Actual |
|---|---|---|
| PA sequence_number | monotonic, reserved at PA start | reuses post-mutation `seq` |
| Steal vs its PA order | PA first, then steal | can collide or invert |
| PA outs_before_play | outs before the PA only | may include a later CS out |

## Suggested fix

- Append the PA event using the `seq`/`event_id` reserved for it in step 1, and capture
  `outs_before_play` at the moment the PA is resolved (before the steal block runs).
- Emit any stolen-base / caught-stealing events with `sequence_number` strictly greater
  than the PA that created the baserunner.
- Consider building each event with its own captured sequence value at the point it
  logically occurs, rather than reading a shared mutable `seq` at append time.

## Verification

Add a test that forces a single followed by a caught stealing and assert: the PA event's
`sequence_number` is less than the caught-stealing event's, and the PA's
`outs_before_play` does not include the caught-stealing out.
