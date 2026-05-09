# Pre-Consult AI Phase 1 Refactor Blueprint

## Goal
Turn the current single-file Flask demo into a maintainable backend with clear boundaries while preserving existing behavior and test coverage.

## Phase 1 scope
1. Introduce an application package under `backend/app/`
2. Extract domain constants / defaults / schemas from `app.py`
3. Extract session state + SSE helpers
4. Extract routing into blueprints or modular route files
5. Keep current frontend/templates working unchanged
6. Keep all existing tests green during migration

## Target structure (incremental)

```text
backend/
  app/
    __init__.py
    config.py
    domain/
      constants.py
      defaults.py
      schemas.py
      rules.py
    state/
      sessions.py
    services/
      triage.py
      providers.py
      booking.py
      export_pdf.py
    api/
      routes.py
```

## Migration strategy
- Step 1: create package + move pure helpers/constants only
- Step 2: import moved symbols back into root `app.py` so behavior stays unchanged
- Step 3: move session state helpers
- Step 4: move service logic
- Step 5: shrink root `app.py` into compatibility entrypoint
- Step 6: add new tests around extracted modules

## Non-goals for this pass
- No React migration yet
- No DB migration yet
- No FastAPI switch yet
- No major API contract changes yet

## Immediate execution order
1. Create `backend/app/domain/defaults.py`
2. Create `backend/app/domain/constants.py`
3. Create `backend/app/state/sessions.py`
4. Patch `app.py` to import from those modules
5. Run tests
6. Then continue extracting provider + booking + PDF services
