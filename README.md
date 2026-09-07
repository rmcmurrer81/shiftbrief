> Current source release: this repository includes the verified Desktop implementation and a separate no-install browser edition. See [BROWSER-BUILD.md](BROWSER-BUILD.md) to generate the static browser assets from pinned dependencies. Runtime binaries, personal state and the optional voice pack are excluded. Desktop setup requirements below apply to maintainers/users running the local server, not to judges opening the hosted browser build. Historical contest and test notes below retain their original verification scope.

# ShiftBrief · Team desk

Plan a real store, office or team week with recorded employee availability, staffing coverage and dated history. Talk to Sarah, review a proposal, then accept or edit it. Your own team starts empty. **Try fictional team** opens a separate example with five clearly fictional employees.

## Start the desktop app

On Windows with Python 3.11 or newer, open **START SHIFTBRIEF.cmd**. The text, staffing and TXT/Markdown/CSV workflows use Python's standard library; there is no first-run model download, API key or pip install. An existing app-local virtual environment is reused. You can also run `python server.py --open` and open `http://127.0.0.1:8797`.

The clean desktop ZIP does not include Python or a voice model. The no-install hosted-browser edition is a separate delivery route; do not describe this ZIP as working on a computer with no Python installed.

## Your first week

1. Say **I hired a new employee**. Sarah asks their name and opens the adjacent seven-day availability form. Desktop shows all seven actual dates starting Sunday; a phone edits one date at a time. Enter Available, Off or Not provided. Choose hours/minutes/AM–PM separately. Check **Ends next day** for overnight availability. The hire date is editable. Save only real qualifications and availability; future weeks remain unknown.
2. Say **We open 9am to 5pm Monday through Friday**, or use **Settings → Customer hours**. Review all weekdays and accept. Customer hours, opening staff arriving early and closing staff staying later are separate. Specific hours, overnight closing, 24-hour operation, closed weekdays and one-date overrides are supported. The starting 9–5 form values are not confirmed business facts; a week cannot be suggested until hours are reviewed.
3. In Settings, record required roles/headcounts and the weekly projected-overtime threshold. Use `Team: 1` alone for general headcount, or distinct roles such as `Cashier: 1` and `Floor: 1`.
4. Open the Sunday week and choose **Suggest week**. The proposal uses recorded availability, time off, employment dates and role qualifications. Review unfilled coverage, planned hours, projected overtime and employee preferences. Lunch breaks are not automatically assigned. **Edit proposed shifts** changes the draft; **Accept reviewed week** saves all seven dates in one transaction. Previous dated revisions remain in History.
5. Choose a date and review its actual shift table and coverage intervals. **3D view** displays the same counts with perspective; the coverage table supplies the exact values. Phones have a focused week overview and a separate day detail screen. Lists, messages and history are paginated so the active controls stay visible.

## Day-to-day work

- **Find a 30 minute lunch for Maya on 2026-09-13** proposes break choices ranked by added role-coverage gaps. An explicit time/window is respected. Select and accept one; it is not applied by asking.
- **Adam is sick on 2026-09-13** ranks eligible, recorded-available people not already working during that shift, from least projected overtime to most, then by weekly hours. Qualified adjacent 2–3 hour early/late extensions are included when possible. Partial coverage is labeled. Optional contact details create a call list only. Nobody is contacted, and the app does not claim anyone agreed to work. Accept an option after arranging it yourself.
- **Lisa quit** asks for the first date she will no longer be available. The employee and earlier schedules remain in history. Conflicts in already-saved future shifts are flagged.
- Record availability, preferences and time off in Employees/Requests. Cancelling a dated time-off request keeps its history. Stale employee forms and stale proposals cannot overwrite newer details.
- **We are closed on Christmas** proposes an annual December 25 closure. **Next Thursday we are closed for a new system installation** shows the resolved exact date and your reason before acceptance. Full-day closures remove all staffing bands on that date, including overnight spillover and opening/closing buffers. Old accepted schedules stay intact and show conflicts until reviewed; no statutory holiday list is assumed.
- Near the weekend, an in-app reminder points to the upcoming Sunday week if it has not been reviewed or its relevant saved state changed. There is no background email or automatic outreach.
- **History** revisits exact dated revisions. Restoring creates a new revision and must satisfy current availability/hours constraints. **Export week** downloads shifts CSV, exact coverage intervals CSV and the dated JSON plans in one ZIP. No contact directory or unrelated team is included.

Overnight work is projected into separate actual calendar-date rows; 24:00 marks midnight at the end of the shown date. Unknown availability is not inferred. Free-text preferences are shown for owner review, not silently interpreted as hard scheduling rules. The scheduler is a bounded deterministic proposal engine, not an optimal-schedule guarantee, general language model, attendance system, payroll system or labor-law assessment.

## Sources and handoffs remain available

Sources keeps exact original lines and their revisions. Sarah can help create a source note from your exact words, requiring YES before saving it, retrieve evidence, compare changes and prepare a saved cited handoff. Conclusions and unresolved decisions stay distinct. Source quotes and long findings are paginated with complete-wording controls.

PDF import is optional: install `requirements-local.txt` into your chosen runtime to enable it. Scanned PDFs need OCR outside this app. Watching a file is optional and checks only the exact selected local path; it does not scan folders.

## Optional capabilities and contest truth

**Voice is optional.** The installed local app can discover the separately installed, owner-approved `sarah-voice-pack` beside it. Enabling voice plays actual saved Sarah replies using its CPU service. The clean app ZIP excludes the voice model and all generated speech. Text remains fully usable without it.

**Strands/Ollama is optional and explicit.** Installing `requirements.txt` enables the real Strands agent route, which uses `read_updates` and `save_shift_brief` with an installed Ollama model. The free staffing/conversation engine is deterministic local code; it is not an LLM and must not be represented as the contest-required Strands agent by itself. The Agents for Humans rules require actual Strands work; retain the separately tested Strands route and describe the distinction honestly. No hosted-model credentials are needed for the standard team desk.

## Data and verification

All local state is under `data/`, with separate teams, employee record history, immutable dated schedule revisions and reviewed proposal hashes. Back up this directory for your own records. The public package excludes owner data, configuration, credentials, logs, generated speech and private media.

See `TEST_RESULTS.md` for the measured workflow and responsive checks, and `BROWSER_API.md` for the reusable standard-library core and hosted-browser port contract.
