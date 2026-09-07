# Browser port contract · ShiftBrief staffing core

The current Desktop source has passed its real no-model workflow. A hosted/browser-only port is a separate integration and must be tested before being called ready. No Python server, model, API key or voice pack should be required from a judge for that edition.

## Reusable core

Load these standard-library modules into the browser Python runtime: `briefing.py`, `sarah_local.py`, `shift_schedule.py`, `staffing.py`, `staffing_chat.py`, `operating_hours.py`. They do not generate text with a model or contact providers. `agent.py`, `server.py`, file watching, optional PDF import and optional voice are separate adapters.

`Store(path)` reads/writes `path/state.json`; `save()` atomically replaces the JSON file. Use the shared browser-runtime durable filesystem/IndexedDB/SQLite adapter and await persistence before reporting success. Do not invent fixture data on an empty browser profile. `Store.view()` supplies current-team sources, handoffs, conversation and staffing state. Existing internal `production` IDs are retained; the UI calls them teams.

All calendar dates are `YYYY-MM-DD`; `week_start` must be Sunday. Native Python uses the local calendar date. The browser adapter must verify its Python calendar agrees with the browser's local date/time zone before using “today”, “tomorrow” or “next Thursday”. Explicit selected dates must remain exact. Do not infer employee availability for a future week.

## State response and frontend

The existing frontend requests `GET /api/state` and receives:

```
{app:'ShiftBrief', state:store.view(), token:sessionNonce,
 runtime:{mode:'sarah_local',label:'Sarah local evidence',model:'none',url:'local browser data',optional_strands_available:false},
 jobs:[...currentTeamJobs]}
```

`state.staffing` contains employees, settings, `operating_hours`, reviewed/unreviewed operating proposals, `selected_week`, `selected_date`, seven dated day objects, weekly hours, schedule proposals, reminder and event history. Each day has its exact saved plan, coverage report, current staff/hours conflicts and history summaries. `state.assistant` contains exact conversation messages and pending source-note/checklist changes, plus optional `staffing_form` and operating/staffing proposal IDs.

Serve `index.html`, `style.css`, `app.js`, `staffing_ui.js`, `operating_ui.js`, `source_handoff_ui.js` and `sarah_voice.js`. Preserve no-store/real durable state semantics. Browser delivery should hide unavailable local-file watching and optional Ollama/voice controls, while keeping normal text Sarah, uploads, scheduling and exports usable. Do not show a judge key wizard. The current native-only voice client is optional and must not block text.

## Mutations

Native POSTs are JSON with `X-ShiftBrief-Token`; a browser adapter can keep a page nonce with the same API shape. The handlers return their operation result; frontend then refreshes state.

| POST route | Core call / payload |
|---|---|
| `production/create`, `production/select` | `Store.create_production(title)`, `Store.select_production(id)` |
| `assistant/message` | `sarah_local.ask(store,message,briefing_id?)` |
| `assistant/confirm` | `sarah_local.confirm(store,proposal_id,proposal_sha,confirmation)`; exact YES required |
| `staff/employee` | `staffing.save_employee(store,payload)`; existing employee needs `id` and `expected_revision` |
| `staff/end` | `end_employment(store,employee_id,date,reason)`; date is first unavailable day |
| `staff/timeoff` | `time_off(store,employee_id,start,end,reason)`; inclusive actual dates |
| `staff/timeoff-cancel` | `cancel_time_off(store,employee_id,date,expected_revision)` |
| `staff/settings` | `settings(store,{roles:{role:headcount},overtime_hours})` |
| `staff/week`, `staff/day` | `select_week(store,week_start)`, `select_day(store,date)` |
| `staff/suggest` | `suggest_week(store,week_start)`; reviewed operating hours required |
| `staff/revise` | `revise_week(store,id,sha256,days)`; exact seven dates, proposed shifts with employee_id/role/start/end/end_next_day |
| `staff/lunch` | `suggest_lunch(store,shift_id,date,duration=30)` |
| `staff/sick` | `suggest_sick(store,employee_id,date)` |
| `staff/accept` | `accept(store,id,sha256,choice?)` |
| `staff/shift` | `edit_shift(store,payload)`; date, expected_sha, optional shift_id, employee_id, role, start/end/end_next_day or remove:true |
| `staff/restore` | `restore_schedule(store,{date,number,expected_sha})` |
| `staff/hours-propose` | `operating_hours.propose(store,config,source_message)` |
| `staff/hours-accept` | `operating_hours.accept(store,id,sha256)` |
| `staff/example` | `load_staff_example(store)`; explicitly separate fictional team |

Employee availability payload is exactly seven rows for `week_start`: `{date,status:'unknown'|'off'|'available',start:'09:00',end:'17:00',end_next_day:false,preference:''}`. Identity fields are name, start_date, roles[], optional phone/email/preferences. Endings at midnight are explicit; overnight availability is projected onto real calendar dates. An explicit Off/time-off/closed calendar date blocks spillover.

Operating hours: `{weekdays:{'0':SundayWindow,...'6':SaturdayWindow},date_overrides:{date:window},closures:[]}`. Window fields: `mode:'hours'|'24h'|'closed'`, open/close strings, `end_next_day`, before_minutes/after_minutes. Closure fields: `{kind:'annual',month,day,reason}` or `{kind:'date',date,reason}`. IDs are assigned by validation. Only user-entered closures exist. Do not replace the reviewed-proposal route with a silent settings write.

## Reads, exports and handoffs

- `GET schedule/history?date=...&number=...`: `shift_schedule.view`; use `staffing.role_coverage(result.plan)` for role detail.
- `GET schedule/export?date=...`: `shift_schedule.export_csv(shift_schedule.latest(store,date))`.
- `GET staff/export-week?week=...`: `staffing.export_week` returns ZIP bytes. Browser adapter must return a downloadable `application/zip` Blob, not a UTF-8 conversion of binary bytes.
- `POST import`: decode selected base64 bytes or UTF-8 text and call `Store.import_document`. Preserve original source lines/revisions. PDF support requires a separately tested browser package; TXT/Markdown/CSV works without it.
- `POST brief` in local mode: call `sarah_local.run_local`; report a completed job with actual saved `briefing_id` and trace. Keep completed jobs queryable so the existing poll completes. No background promise should be reported as a saved handoff.
- `POST decision`: `Store.set_decision`; export uses `Store.export`.

The optional actual Strands/Ollama route must remain accurately labeled. A deterministic browser core does not itself prove the Agents for Humans Strands requirement. Never simulate a successful framework/model run.

## Port acceptance minimum

Repeat the current Python integrity tests and the three current Edge harnesses against the browser adapter, replacing localhost bootstrap only. Verify new browser profile, persistence after reload/browser restart, team isolation, zip bytes, stored original documents, stale proposals, all six viewports, and explicit no-model/no-key behavior. Do not copy owner Desktop data or private voice/media into a public website.
