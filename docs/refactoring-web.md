# Web Refactoring Recommendations

## Current Hotspots

- `web/src/views/MatchupView.vue` is very large and contains multiple concerns.
- `web/src/composables/useLineupPanel.ts` combines validation, drag/drop, autosave, and persistence calls.
- Repeated formatting/status mapping logic appears across views.

## Refactoring Priorities

### 1. Split `MatchupView` into focused child components

Recommended components:

- `MatchupHeader`
- `LineupPanel`
- `BoxScorePanel`
- `PlayByPlayPanel`

Keep the page-level view focused on orchestration and routing.

### 2. Split lineup composable by concern

Break `useLineupPanel` into smaller composables/modules:

- `useLineupDeadlines`
- `useLineupDragDrop`
- `useLineupValidation`
- `useLineupPersistence`

Benefits:

- Better testability and readability.
- Lower risk when changing a single interaction behavior.

### 3. Extract pure lineup validation rules

Move batting-order constraints into a pure domain module that does not depend on Vue reactivity.

Examples:

- Position uniqueness checks
- DH/P XOR rule
- Eligibility checks

Then test these as plain unit tests.

### 4. Introduce typed API/domain adapters

Keep transport DTOs in API layer and map to UI-facing domain models before rendering.

Benefits:

- UI less sensitive to backend field-shape changes.
- Cleaner component props and computed logic.

### 5. Consolidate formatting/status helpers

Create shared utilities for:

- Status label/severity mapping
- Date/time formatting
- Common matchup display strings

This reduces drift between Home and Matchup views.

## Testing Recommendations

- Add unit tests for extracted pure validation module.
- Add component tests for lineup interactions (drag/drop, position edits, save/revert).
- Add lightweight integration tests for realtime update behavior.

## Suggested Next Iteration Order

1. Extract pure lineup validation module and add tests.
2. Split `useLineupPanel` into validation + persistence first.
3. Split `MatchupView` into box score and lineup child components.
4. Consolidate formatting/status helpers and update both Home and Matchup views.
