# ShiftBrief · Business workspace

Plan a store, office or team week with recorded employee availability, staffing coverage and dated history. Talk to Sarah, review a proposal, then accept or edit it. A new installation opens a blank business with no demo records. **Load demo** explicitly adds Maple Street, a separate fictional workplace with eight invented employees and several months of planned shifts and recorded work. An existing installation reopens its saved selected business without replacing it.

## Download and start on Windows

[**Download ShiftBrief 0.1.0 for Windows**](https://github.com/rmcmurrer81/shiftbrief/releases/download/v0.1.0/ShiftBrief-Setup-0.1.0.exe) · [Release notes, portable ZIP and checksums](https://github.com/rmcmurrer81/shiftbrief/releases/tag/v0.1.0)

The free installer supports Windows 10 or newer on x64-compatible systems. Run it, follow the setup prompts, then open **ShiftBrief** from the Start menu. A desktop shortcut is optional and unchecked by default. Python and the app dependencies are included, so no separate Python setup or pip install is needed. ShiftBrief opens a local browser interface; start with **Records · offline**, which needs no account, API key or AI model.

Closing the browser leaves the local server running. Use **Start → ShiftBrief → Close ShiftBrief** before upgrading or uninstalling. Uninstall through Windows Settings or the Start-menu entry; your saved business data remains. [Installer details and verification](installer/README.md) describe the tested release and its limits.

### Run from source instead

With Python 3.11 or newer, open **START SHIFTBRIEF.cmd**. The text, staffing and TXT/Markdown/CSV workflows use Python's standard library; an existing app-local virtual environment is reused. You can also run `python server.py --open` and open `http://127.0.0.1:8797`.

The source checkout does not include Python. Neither the installer, portable ZIP nor source checkout includes AI model weights or a personal voice model. Optional AI and voice setup are separate from Records mode.

The `browser/` tree and [BROWSER-BUILD.md](BROWSER-BUILD.md) preserve an earlier, separate static-browser edition. They are not synchronized with this desktop update and do not establish current desktop feature parity. Use the local server above for the current business-copy, complete-backup, recorded-work and AI-mode interfaces.

## Your first week

1. Say **I hired a new employee**. Sarah asks their name and opens the adjacent seven-day availability form. Desktop shows all seven actual dates starting Sunday; a phone edits one date at a time. Enter Available, Off or Not provided. Choose hours/minutes/AM–PM separately. Check **Ends next day** for overnight availability. The hire date is editable. Save only real qualifications and availability; future weeks remain unknown.
2. Say **We open 9am to 5pm Monday through Friday**, or use **Settings → Customer hours**. Review all weekdays and accept. Customer hours, opening staff arriving early and closing staff staying later are separate. Specific hours, overnight closing, 24-hour operation, closed weekdays and one-date overrides are supported. The starting 9–5 form values are not confirmed business facts; a week cannot be suggested until hours are reviewed.
3. In Settings, record required roles/headcounts and the weekly projected-overtime threshold. Use `Team: 1` alone for general headcount, or distinct roles such as `Cashier: 1` and `Floor: 1`.
4. Open the Sunday week and choose **Suggest week**. The proposal uses recorded availability, time off, employment dates and role qualifications. Review unfilled coverage, planned hours, projected overtime and employee preferences. Lunch breaks are not automatically assigned. **Edit proposed shifts** changes the draft; **Accept reviewed week** saves all seven dates in one transaction. Previous dated revisions remain in History.
5. Choose a date and review its actual shift table and coverage intervals. **3D view** displays the same counts with perspective; the coverage table supplies the exact values. Phones have a focused week overview and a separate day detail screen. Lists, messages and history are paginated so the active controls stay visible.

## Day-to-day work

- **Find a 30 minute lunch for Maya on 2026-09-13** proposes break choices ranked by added role-coverage gaps. An explicit time/window is respected. Select and accept one; it is not applied by asking.
- **Adam is sick on 2026-09-13** ranks eligible, recorded-available people not already working during that shift, from least projected overtime to most, then by weekly hours. Qualified adjacent 2–3 hour early/late extensions are included when possible. Partial coverage is labeled. Optional contact details create a call list only. Nobody is contacted, and the app does not claim anyone agreed to work. Accept an option after arranging it yourself.
- **Lisa quit** or **I just fired Morgan Stone** opens an employment-ending review for the named employee. Review the first unavailable date and use **Preview remaining shifts** before saving. After **Record end date**, Sarah reports remaining saved shifts and net planned hours, with eligible off-schedule replacements or partial early/late extensions. Options respect recorded availability, qualifications, absences, existing shifts and saved weekly restrictions; overtime is shown separately. These are independent alternatives requiring employee agreement and your schedule review. Existing shifts, completed work and employee history remain intact; Sarah does not choose whom to fire or reassign anyone automatically.
- Record availability, preferences and time off in Employees/Requests. Cancelling a dated time-off request keeps its history. Stale employee forms and stale proposals cannot overwrite newer details.
- **We are closed on Christmas** proposes an annual December 25 closure. **Next Thursday we are closed for a new system installation** shows the resolved exact date and your reason before acceptance. Full-day closures remove all staffing bands on that date, including overnight spillover and opening/closing buffers. Old accepted schedules stay intact and show conflicts until reviewed; no statutory holiday list is assumed.
- Near the weekend, an in-app reminder points to the upcoming Sunday week if it has not been reviewed or its relevant saved state changed. There is no background email or automatic outreach.
- **History** revisits exact dated revisions. Restoring creates a new revision and must satisfy current availability/hours constraints. **Export week** downloads shifts CSV, exact coverage intervals CSV and the dated JSON plans in one ZIP. No contact directory or unrelated team is included.

Overnight work is projected into separate actual calendar-date rows; 24:00 marks midnight at the end of the shown date. Unknown availability is not inferred. Free-text preferences are shown for owner review, not silently interpreted as hard scheduling rules. The scheduler is a bounded deterministic proposal engine, not an optimal-schedule guarantee, general language model, automatic attendance capture, payroll system or labor-law assessment. Completed work is entered separately from planned shifts; comparisons show the saved dates and available records.

## Sources and handoffs remain available

Sources keeps exact original lines and their revisions. Sarah can help create a source note from your exact words, requiring YES before saving it, retrieve evidence, compare changes and prepare a saved cited handoff. Conclusions and unresolved decisions stay distinct. Source quotes and long findings are paginated with complete-wording controls.

The Windows installer includes the PDF reader dependency. When running from source, install `requirements-local.txt` into your chosen runtime to enable PDF import. Scanned PDFs need OCR outside this app. Watching a file is optional and checks only the exact selected local path; it does not scan folders.

## Optional capabilities and contest truth

**Voice is optional.** The installed local app can discover the separately installed, owner-approved `sarah-voice-pack` beside it. Enabling voice plays actual saved Sarah replies using its CPU service. The installer and clean portable ZIP exclude the voice model and all generated speech. Text remains fully usable without it.

**AI modes are optional and explicitly selected.** `Records · offline` uses deterministic domain code and saved records. `AI · local Ollama` and `AI · cloud Bedrock` use the separate Strands route. The installer includes its client libraries; source users install `requirements.txt`. Both require a separately configured provider and a model already available to that provider. No AI mode is invoked by first startup or by the tests listed below. Cloud selection sends the question, recent conversation and selected saved facts to the configured AWS model.

For local AI, source users install the optional dependencies into their chosen Python environment; installer users already have the client libraries. Set `SHIFTBRIEF_AGENT_PROVIDER=ollama`, `SHIFTBRIEF_OLLAMA_URL` to a loopback Ollama URL and `SHIFTBRIEF_MODEL` to an installed model name. For Bedrock, set `SHIFTBRIEF_AGENT_PROVIDER=bedrock`, `SHIFTBRIEF_BEDROCK_REGION`, `SHIFTBRIEF_BEDROCK_MODEL` and temporary AWS credentials in the launch environment. The app does not save credentials in business files. Provider access and cloud usage are separate from the offline workflow.

AI responses and staffing suggestions are reviewed by the user; the app does not choose whom to fire or send messages to employees. Demonstrate the actual selected engine when describing the project. The offline record engine is not an LLM, and this source update does not establish hackathon eligibility or submit the project.

## Data and verification

The installed app saves business data under `%LOCALAPPDATA%\ShiftBrief\data`, separate from its program files under `%LOCALAPPDATA%\Programs\ShiftBrief`. Source and portable runs save under their workspace’s `data/` directory. Use **Save business copy** to download the selected business as a `.shiftbrief.json` file. On another computer, choose **Load saved business** to add it while preserving businesses already there. This portable file includes employees, contacts, pay and employee history, availability, operating settings, planned schedules and recorded work; it excludes documents and conversations.

Use **Back up all businesses** for a complete `.shiftbrief-workspace.json` backup, including all saved businesses, documents and their extracted revisions, handoffs and conversations. On the destination computer, choose **Restore backup from previous computer**, select that file, review its summary and confirm the restore. This replaces the destination workspace after automatically saving a complete backup of its previous state. Linked external documents remain disabled until their file paths are chosen again. Copy external original files separately; the backup does not include the app, Python, models or credentials.

The source package excludes saved workspace data, configuration, credentials, logs and generated speech. The only included business file is the explicitly fictional Maple Street demo.

See `TEST_RESULTS.md` for the measured workflow and responsive checks, and `BROWSER_API.md` for the reusable standard-library core and hosted-browser port contract.

## Verify this update

From the repository root, run:

```sh
python -B -m unittest -v test_first_run_migration test_onboarding test_staffing test_staffing_integrity test_operating_hours
```

The 41 targeted tests passed on Python 3.12.10. After the repository sync, those tests plus its 14 retained language-correction regressions passed again (55 total). They use isolated temporary stores and loopback HTTP; no real model or external service is called. [TEST_RESULTS.md](TEST_RESULTS.md) records the exact scope and known older full-suite failures. Application source uses the MIT license in [LICENSE](LICENSE); the preserved browser dependencies carry their separate upstream notices.

## Departure coverage update

Remaining hours count the latest saved schedules from the later of today or the first unavailable date. Today includes whole planned shifts; no attendance is inferred. Saved breaks are subtracted. Missing future dates and unknown availability are not invented. Reopen **Employees → More → Remaining shifts to cover** after recording an end date.

The integrated update passed 87 targeted Python tests (67 existing/departure-review tests and 20 coverage/HTTP tests), eight UI checks, and a browser walkthrough of the fictional Morgan Stone departure. The walkthrough showed 60 hours across 10 remaining shifts, full replacement options and an early-start option covering four hours with two still uncovered. This is fictional test evidence, not business data or a general scheduling guarantee.
