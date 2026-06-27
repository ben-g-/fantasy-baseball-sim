# API Refactoring Recommendations

## Current Hotspots

- Route modules are orchestration-heavy, especially `api/src/routes/matchups.ts`.
- Route handlers mix auth/membership checks, data loading, business rules, and response shaping.
- Some writes are non-atomic (for example, delete-then-insert replacement flows).
- Shared logic (membership/deadline checks) appears repeatedly across handlers.

## Refactoring Priorities

### 1. Introduce service layer per domain area

Create services such as:

- `MatchupService`
- `LineupService`
- `ResultsService`

Route responsibilities should be limited to:

- Request parsing/validation
- Calling service methods
- Mapping domain errors to HTTP responses

### 2. Add repository layer for data access

Define repositories for Supabase access:

- `MatchupRepository`
- `LineupRepository`
- `TeamRepository`
- `ResultsRepository`

Benefits:

- Improved DIP: business logic depends on interfaces, not Supabase calls.
- Easier unit tests with repository fakes.

### 3. Make lineup updates transactional

Current delete-then-insert replacement can leave partial state if insert fails.

Recommended:

- Wrap lineup mutation flows in database transactions or RPC.
- Prefer upsert/replace patterns that are atomic at persistence boundary.

### 4. Centralize authorization and league-membership guards

Extract repeated guard logic into reusable policy helpers or middleware utilities.

Examples:

- `assert_user_manages_team(...)`
- `assert_user_in_league(...)`
- `assert_deadline_open(...)`

### 5. Separate response mappers from route handlers

Move response shaping into dedicated mapper functions/modules.

Benefits:

- Clearer route handlers.
- Stable response-contract tests.
- Reduced coupling between query shapes and HTTP payloads.

## Testing Recommendations

- Add unit tests for services with fake repositories.
- Add integration tests for route-to-service error mapping.
- Add mutation safety tests for lineup update paths.

## Suggested Next Iteration Order

1. Extract `LineupService` with transactional update methods.
2. Add repositories and migrate one route end-to-end.
3. Extract auth/membership/deadline policy helpers.
4. Migrate `matchups.ts` handlers incrementally to service/repository architecture.
