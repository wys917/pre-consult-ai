# Pre-Consult AI Execution Roadmap

> Living plan for the portfolio-focused rewrite. Continue autonomously checkpoint by checkpoint.

## Current status
- Active branch: `feature/doctor-workbench-queue`
- Phase 1 compatibility + backend extraction: complete
- Phase 2 workflow UX: substantially complete (review metadata + lifecycle state shipped on main)
- Phase 3.1 groundwork: case queue service + `/api/cases` + `/api/cases/<id>` + `/doctor/queue` workbench page delivered
- Latest completed checkpoint: doctor workbench queue with risk-first sorting, status filters, and manual-review highlighting

## Phase definitions

### Phase 1 — Architecture extraction
Goal: move the single-file Flask demo into a maintainable backend package without breaking existing behavior.

Done / near-done:
1. Extract domain defaults/constants/rules
2. Extract session state + SSE helpers
3. Extract triage/provider/booking/pdf services
4. Extract routes into backend blueprint
5. Keep compatibility entrypoint and preserve current API/UI behavior
6. Add module-boundary tests

Exit criteria:
- Existing patient/doctor demo routes still work
- Tests cover extracted service boundaries
- Root `app.py` is compatibility-oriented rather than business-logic heavy

### Phase 2 — Workflow and handoff productization
Goal: make the demo tell a stronger job-ready story around intake → triage → handoff → booking.

Completed checkpoints:
1. Visit preparation / self-care / follow-up guidance in summary payload
2. Workflow stage labels, handoff banner, and progression timeline

Remaining checkpoints:
1. Doctor-side actionable handoff card (copy-ready referral / intake note)
2. Patient-side next-step CTA blocks tied to workflow stage
3. Booking completion state written back into session summary for both views
4. More explicit emergency / urgent routing copy and state transitions

Exit criteria:
- Both patient and doctor views clearly communicate next action
- Summary payload includes actionable handoff guidance, not just descriptive analysis
- Booking state is reflected in the workflow narrative

### Phase 3 — Productization and doctor workbench
Goal: evolve from single-session demo into a workflow-style clinical intake platform.

#### Phase 3.1 Case queue / doctor workbench
Build doctor-side workflow management instead of a single summary page.

Target capabilities:
- case list / queue
- sort by risk level
- statuses: `new`, `in_review`, `escalated`, `booked`, `closed`
- open a case to inspect full summary
- view summary diffs across turns
- mark `needs_manual_review`
- allow manual edits to selected summary fields later

Recommended incremental order:
1. Persist per-session lifecycle/status metadata in backend state
2. Add queue endpoint returning active sessions with status/risk summary
3. Render simple doctor queue panel before rewriting the UI stack
4. Add per-case open/focus behavior and detail panel
5. Add summary diff / replay view

#### Phase 3.2 Session timeline / replay
Expose why the system produced a result.

Replay should show:
- raw patient input per turn
- model reply per turn
- structured summary snapshots/diffs
- which red flags came from rules
- which fields were model-filled
- review-trigger reasons

This is high-value for:
- explainability
- medical credibility
- interviews/demo narrative

#### Phase 3.3 Lifecycle state machine
Adopt explicit lifecycle states:
- `intake_started`
- `summary_ready`
- `awaiting_more_info`
- `high_risk_escalated`
- `ready_for_booking`
- `booked`
- `closed`

Rule: workflow stage for UI and lifecycle state for platform operations are related but distinct. Keep both if needed.

#### Phase 3.4 Frontend modernization
Preferred direction:
- React + TypeScript + Vite or Next.js

Priority if time-constrained:
1. Doctor workbench first
2. Admin/eval/debug page second
3. Patient UI last

Until the migration starts, keep backend contracts clean and component-friendly.

#### Phase 3.5 Multi-case demo mode
Add seeded demo cases for portfolio walkthroughs:
- respiratory infection
- acute abdomen risk
- high-risk chest pain
- rash/allergy
- neurologic symptoms

Use these for queue, replay, eval, and demo video generation.

### Phase 4 — Evaluation, observability, and job-market polish
Goal: move from “built a prototype” to “built a measured, trustworthy AI workflow system.”

#### Phase 4.1 Offline evals
Add:
```text
evals/
  cases/
    triage_eval_v1.jsonl
  scripts/
    run_eval.py
    score_eval.py
  reports/
    eval_report_v1.md
```

Each case should contain:
- input conversation
- expected department
- expected urgency
- expected red flags
- expected missing fields
- expected review trigger if applicable

Metrics:
- department accuracy
- urgency accuracy
- red-flag recall
- structured parse success rate
- review-trigger precision

#### Phase 4.2 Observability
At minimum log / expose:
- `request_id`
- `session_id`
- `provider`
- `model`
- `latency`
- `parse_success`
- `fallback_triggered`
- `review_triggered`

#### Phase 4.3 CI/CD
Minimum:
- ruff
- black
- pytest
- GitHub Actions for lint/test/build

#### Phase 4.4 Deployment hardening
Next steps after current Docker/Render baseline:
- staging/prod env separation
- health endpoint
- structured logging
- persistent DB deployment

## High-priority safety/product upgrades from user roadmap

### Safety review / calibrated confidence (highest near-term priority)
Add summary metadata fields:
- `confidence_score`
- `review_reason`
- `risk_source` (`rule` / `llm` / `hybrid`)
- `needs_manual_review`

Trigger `needs_manual_review = True` when, for example:
- too many critical fields are missing
- department recommendation confidence is low
- red-flag conflict exists
- symptoms are contradictory

This is especially valuable for interviews because it demonstrates that the system knows when not to be overconfident.

### Prompt versioning
Do not keep prompts embedded invisibly in functions.

Recommended structure:
```text
backend/app/prompts/
  summary_v1.txt
  followup_v1.txt
  department_routing_v1.txt
  safety_review_v1.txt
```

Track prompt metadata such as:
- `version`
- `model`
- `provider`
- `created_at`

Why:
- enables prompt comparison
- supports eval iteration
- helps tell a prompt-engineering story in interviews

## 2 / 4 / 6 week roadmap compression

### First 2 weeks — remove demo feel
- finish app decomposition
- unify config/schema/provider boundaries
- add SQLite + SQLAlchemy
- persist sessions/messages/summaries
- seed mock/demo data
- refresh README
- migrate/expand tests

### First 4 weeks — strong AI engineering version
- hybrid red-flag engine
- structured output validation
- confidence/manual review
- prompt versioning
- 30–50 eval cases
- eval runner + baseline report
- basic replay / summary diff

### First 6 weeks — flagship version
- React/TS doctor workbench
- case queue
- replay / timeline
- multi-case demo
- observability
- CI/CD
- polished docs and architecture visuals

## Decision rule for autonomous continuation
- If a remaining Phase 2 checkpoint directly improves the visible intake-to-handoff experience, do it before broader Phase 3 work.
- The next best product step after current Phase 2 work is safety-review metadata plus lifecycle state, because it strengthens both product credibility and future queue/eval systems.
- Prefer smallest vertical slice with user-visible impact, tests, commit, push.

## Immediate next recommended implementation checkpoint
1. Persist per-session lifecycle/status history so the queue can show transitions, not just the latest snapshot
2. Add a per-case detail drawer on `/doctor/queue` that reuses the single-session summary components
3. Surface queue counts + manual-review pill on the main `/doctor` view (entry point affordance)
4. Seed mock demo cases (respiratory, abdomen, chest pain, rash, neuro) so the queue has content without manual interaction
5. Begin summary-diff / replay groundwork for Phase 3.2

## Verification standard per checkpoint
- Run focused pytest first, then broader app tests if touched
- Commit after each stable slice
- Push immediately after green tests
