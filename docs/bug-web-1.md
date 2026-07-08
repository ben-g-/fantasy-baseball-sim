# bug-web-1: Matchup Screen realtime refresh blanks the page and can revert in-progress edits

**Severity:** Medium
**Component:** Web client (Matchup Screen)
**Status:** Open

## Summary

`MatchupView` subscribes to Supabase Realtime on the `matchups`, `lineups`, and
`lineup_batting_order` tables so opponent lineup changes and sim completion show up live.
Any event on any of those tables — regardless of which lineup or matchup field it touched —
calls the same `load()` function, which sets `loading` back to `true` and re-fetches the
entire matchup as a new object graph. This has two visible effects:

1. The whole screen is replaced by a bare "Loading…" state and rebuilt from scratch for
   every realtime event, although a given event might only be relevant to a section of
   the screen (e.g. the opponent
   dragging a bench player into the batting order is relevant only to the opponent's
   batting order and bench).
2. Because the batting-order editor derives its local draft from `lineup.batting_order` by
   object identity, the full re-fetch unconditionally overwrites the draft — including a
   batting-order edit the user has in progress but hasn't saved yet — even when the event
   that triggered the refresh had nothing to do with that lineup.

## Spec references

- `specs/build-plan.md` line 201 — "Supabase Realtime for opponent lineup changes:
  subscribe to `lineups` / `lineup_batting_order` table changes so the opponent's SP and
  batting order edits appear live **without a page refresh**."
- `specs/build-plan.md` line 140 — "Unsaved changes indicator; auto-save on valid state;
  silent revert on navigation away" (implies unsaved edits should survive everything short
  of navigating away or an intentional revert).
- `specs/architecture.md` line 46 — "Manage local lineup state (unsaved edits tracked
  client-side)."

## Location

- `web/src/views/MatchupView.vue:24-37` — `load()` sets `loading.value = true`
  unconditionally on every call, including background refreshes triggered by realtime
  events.
- `web/src/views/MatchupView.vue:41-76` — the three `postgres_changes` handlers all funnel
  into `load()` with no distinction between "this event affects a lineup being edited
  locally" and "this event is unrelated."
- `web/src/composables/useLineupPanel.ts:157-168` — the `watch` on
  `lineupRef.value?.batting_order` rebuilds `boItems`/`savedBoItems` from whatever the
  server returned, keyed only on object identity, with no check for an unsaved local draft
  or for whether the server data actually changed.

## Details

```typescript
// MatchupView.vue
async function load() {
  loading.value = true          // hides the entire template behind "Loading…"
  ...
  matchup.value = await getMatchup(matchupId)   // brand-new object graph every time
  ...
}
```

```typescript
// useLineupPanel.ts
watch(
  () => lineupRef.value?.batting_order,
  () => {
    if (!lineupRef.value) return
    const entries = toDisplayEntries(lineupRef.value)
    boItems.value = entries          // clobbers any unsaved local edit
    savedBoItems.value = entries.map((e) => ({ ...e }))
    hasBoChanges.value = false
    boError.value = ''
  },
  { immediate: true },
)
```

Note that simply gating the overwrite on `hasBoChanges.value` (skip the reset whenever
there's a local draft) is not the right fix on its own: if the user's *own* lineup was
saved from another tab/device while this tab has a stale unsaved draft open, the draft is
now moot, and preserving it would let this tab's later auto-save silently overwrite the
newer save from the other tab. The two cases need to be told apart:

- The refresh was triggered by something unrelated to this lineup's batting order
  (opponent's lineup, sim status, this lineup's starting pitcher, etc.) → the local draft
  should survive untouched.
- The refresh reflects a genuine change to *this lineup's* persisted batting order since
  this tab last synced it (e.g. a save from another tab) → the local draft is stale and
  should be discarded in favor of the new server state.

## Suggested fix

- In `MatchupView.vue`, only show the full-page loading state on the initial fetch (guard
  on `matchup.value === null`); background refreshes triggered by realtime events should
  update data without hiding the already-rendered UI.
- In `useLineupPanel.ts`'s batting-order watcher, compare the incoming server
  `batting_order` against `savedBoItems` (the last state this tab knows was persisted for
  this specific lineup) instead of reacting to object identity:
  - If it matches `savedBoItems`, the refresh didn't actually change this lineup's order —
    leave `boItems`/`hasBoChanges` alone.
  - If it differs from `savedBoItems`, this lineup's persisted order changed elsewhere —
    discard the local draft and adopt the new server state (recompute `boItems`,
    `savedBoItems`, and reset `hasBoChanges`).

## Verification

- Edit the batting order in one tab so that it is in an invalid state that doesn't
  auto-save; then in
  a second tab change the *opponent's* SP or batting order, or the user's own SP. Confirm
  that the change appears in the first tab, the first tab's
  in-progress edit and drag state survive, and the page doesn't flash to a loading state.
- Edit the batting order in one tab so that it is in an invalid state that doesn't
  auto-save; then save a different batting order for the
  same lineup from a second tab (or via direct API call). Confirm the first tab's draft is
  discarded and replaced with the newly saved order once the realtime event arrives,
  and that the page doesn't flash to a loading state.
