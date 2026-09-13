# ShiftBrief verification · September 12, 2026

This update brings the current desktop business workspace into the repository. It does not update or re-certify the separate legacy `browser/` bundle.

## Current targeted result

**41 tests passed on Python 3.12.10** using the existing app environment:

```sh
python -B -m unittest -v test_first_run_migration test_onboarding test_staffing test_staffing_integrity test_operating_hours
```

The eight new startup/migration cases cover a fresh blank business with no demo load; reopening an existing fictional business without changing its saved bytes; explicitly loading the demo while preserving existing businesses; recognizing saved historical dates/conversations; additive business export/import with employees, pay history, schedules and recorded work; full-workspace export/preview/restore with exact document revisions and conversations; the automatic before-restore backup and safe repeated restore request; corruption rejection; and the normal loopback HTTP business/backup routes. The bundled demo is explicitly fictional: eight invented employees, 122 saved schedule dates and 385 completed-work records.

The remaining 33 targeted tests cover onboarding, staffing integrity and operating hours. No model calls, external network requests, live-business changes or voice generation occur in this suite. The changed JavaScript files passed Node syntax checks and Python sources compiled in memory. Browser acceptance for this source revision is reported separately; the historical device matrix below is not a fresh claim for the new layout.

The synced repository also passed those 41 tests plus the 14 retained `test_language_corrections` regressions: **55 tests passed** on Python 3.12.10. Negated employment changes, closure corrections and Christmas Eve/Day distinctions remain covered. Add `test_language_corrections` to the command above to reproduce that combined suite.

## Browser review of this update

Actual browser checks on isolated blank and fictional-demo installations verified the blank business startup, Create business dialog and visible **FICTIONAL DEMO** label. A business file was downloaded from the demo, selected through the file chooser in the blank installation and loaded successfully with eight employees and 122 saved schedule dates. The complete-backup download modal also worked. Full-workspace restoration is covered by the CPU and normal HTTP roundtrip above; it was not claimed as an additional browser restore test.

The desktop update preserved the existing saved-state bytes and the previous source backup. These checks establish the stated technical workflows, not owner or hackathon acceptance.

## Known full-suite limits

The first broad check of the desktop candidate ran 68 tests under base Python 3.12 and reported **3 failed assertions and 2 import errors**. The unchanged desktop source ran its 60 tests with the same failures/errors, establishing they predate this first-run change:

- The old Sarah coordinator/follow-up test expects a document lookup, while the installed employee route asks for a saved employee record. Its two assertions fail. This update preserves Sarah's current behavior.
- The old runtime-settings test expects a dictionary without the current `provider` key.
- Base Python lacked optional `pypdf` and `strands`; the PDF and fake-model Strands boundary tests could not import those packages. The existing production app environment has both. The core first-run/migration workflow does not require them.

The initial new-test run also exposed two invalid test request identifiers; the harness was corrected to use the existing restore API's UUID-hex format, and all eight new tests passed. No backend backup-format change was needed. This report does not claim the entire old test suite is green.

## Historical verification retained from the repository

The following September 7 notes apply to their original source/layout and are retained as historical evidence. They are not rerun results for this update. Existing tests and the legacy browser source remain in the repository.

# ShiftBrief staffing verification · 2026-09-07

These checks establish specific behavior, not owner/judge acceptance. The owner has not yet accepted the new staffing workflow.

- 74 Python tests pass (60 existing and 14 language-correction regressions): existing source/revision/handoff behavior plus employee onboarding, dated availability, role qualification, read-only weekly proposals, edited proposals, atomic acceptance/failure rollback, stale employee/proposal protection, lunch coverage, sick-call overtime ranking and partial extensions, employment end dates, cancellation history, CSV/ZIP integrity and team isolation.
- Language corrections preserve employment records on negated quitting/termination, including pending date replies. Christmas Eve resolves to December 24; unsupported holiday qualifiers ask for exact dates. Cancelled closure proposals cannot be accepted after reload. Removing an accepted annual closure requires review, preserves other closures and leaves all accepted dated schedules intact. `test_language_corrections.py` reproduces these 14 checks.
- Operating-hours checks cover separate customer/opening-staff/closing-staff bands, weekdays/ranges, 24-hour operation, explicit overnight end dates, calendar-day projection, recurring December 25 in multiple years, one-date closures, and blocking overnight spillover on closed dates. Changed settings preserve existing saved plans and reject stale proposals.
- Real Edge workflow: empty team → new-hire conversation → name → seven-date form → actual availability → reviewed customer hours → proposed week → accept. No fixture is added to the blank team.
- Real Edge actions using stock Python 3.14, with the model function forced to fail if called: edited weekly proposal; saved replacement call-list option; saved lunch; historical revision restored as a new revision; reviewed exact-date closure; quitting/effective date; stale acceptance rejected visibly; downloaded actual weekly ZIP; persisted state after reload. No model, API key or voice pack was needed.
- Screens/forms/dialogs were checked at 3440×1311, 1920×1080, 1366×768, 768×1024, 390×844 and 320×568. Active screen, form and dialog dimensions and visible controls were measured; the final matrix found no page scroll, overflowing measured panels or offscreen controls. Phones use focused screens and one dated availability row at a time.
- Browser fixtures are isolated temporary fictional teams/office sources. They do not modify the owner's Desktop data. No calls, messages, paid APIs or Runway generations occurred.

Evidence is in the development `evidence/staffing-browser/` directory and is excluded from the clean app package. `verify_staffing.cjs`, `verify_staffing_deep.cjs` and `verify_staffing_actions.cjs` reproduce the current checks with Playwright and an explicit Python path. Older browser harnesses target the earlier layout and are superseded by these current harnesses.

The optional approved local CPU voice pack passed actual playback before this dashboard update; text is the primary judge workflow. The optional Strands/Ollama route remains separate, and the new free staffing engine is not represented as a general LLM or as fulfilling that framework requirement by itself.

The 2026-09-07 language update also passed nine actual Edge conversation turns with repeated reload and nine focused views across the six sizes, on both the browser edition and the installed Desktop files using isolated fictional state. Three installed probes with the provider connection disabled made zero connection attempts. These checks establish the listed behavior only; open-ended language still receives clarification.
