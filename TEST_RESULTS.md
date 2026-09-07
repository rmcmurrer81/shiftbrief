# ShiftBrief staffing verification · 2026-09-07

These checks establish specific behavior, not owner/judge acceptance. The owner has not yet accepted the new staffing workflow.

- 60 Python tests pass: existing source/revision/handoff behavior plus employee onboarding, dated availability, role qualification, read-only weekly proposals, edited proposals, atomic acceptance/failure rollback, stale employee/proposal protection, lunch coverage, sick-call overtime ranking and partial extensions, employment end dates, cancellation history, CSV/ZIP integrity and team isolation.
- Operating-hours checks cover separate customer/opening-staff/closing-staff bands, weekdays/ranges, 24-hour operation, explicit overnight end dates, calendar-day projection, recurring December 25 in multiple years, one-date closures, and blocking overnight spillover on closed dates. Changed settings preserve existing saved plans and reject stale proposals.
- Real Edge workflow: empty team → new-hire conversation → name → seven-date form → actual availability → reviewed customer hours → proposed week → accept. No fixture is added to the blank team.
- Real Edge actions using stock Python 3.14, with the model function forced to fail if called: edited weekly proposal; saved replacement call-list option; saved lunch; historical revision restored as a new revision; reviewed exact-date closure; quitting/effective date; stale acceptance rejected visibly; downloaded actual weekly ZIP; persisted state after reload. No model, API key or voice pack was needed.
- Screens/forms/dialogs were checked at 3440×1311, 1920×1080, 1366×768, 768×1024, 390×844 and 320×568. Active screen, form and dialog dimensions and visible controls were measured; the final matrix found no page scroll, overflowing measured panels or offscreen controls. Phones use focused screens and one dated availability row at a time.
- Browser fixtures are isolated temporary fictional teams/office sources. They do not modify the owner's Desktop data. No calls, messages, paid APIs or Runway generations occurred.

Evidence is in the development `evidence/staffing-browser/` directory and is excluded from the clean app package. `verify_staffing.cjs`, `verify_staffing_deep.cjs` and `verify_staffing_actions.cjs` reproduce the current checks with Playwright and an explicit Python path. Older browser harnesses target the earlier layout and are superseded by these current harnesses.

The optional approved local CPU voice pack passed actual playback before this dashboard update; text is the primary judge workflow. The optional Strands/Ollama route remains separate, and the new free staffing engine is not represented as a general LLM or as fulfilling that framework requirement by itself.
