# ShiftBrief — production changes to a usable handoff

**Target:** Professional Agents track, [Agents for Humans](https://agentsforhumans.devpost.com/). Deadline **September 14, 2026, 8 p.m. Eastern / 5 p.m. Pacific**. The event lists **$40,000 in cash prizes**: $10,000 grand prize and $5,000 / $3,000 / $2,000 in each track. This entry is local software, not a deployed AWS service.

Double-click the Desktop **ShiftBrief** shortcut, or **START SHIFTBRIEF.cmd** in this folder. The launcher opens the browser only after the local service responds at `http://127.0.0.1:8797`. Opening the shortcut again restores the same saved workspace.

## Try it

1. Click **Try fictional shoot documents**. This imports source examples, not a prepared AI answer.
2. Compare the call-sheet revisions: 07:00 becomes 08:30, the pier becomes Warehouse B, and the transport note still gives the old location.
3. Click **Prepare handoff**. The real Strands agent reads the revision tools, identifies changes and conflicts, checks exact source quotations, and saves a briefing and suggested decisions.
4. Open a source quotation, mark a decision done, and export the handoff as Markdown. Reload to see the saved checklist.
5. Add your own PDF, text, Markdown or CSV, or paste text. Select **New revision: …** to preserve an update beside its earlier version. A later revision does not automatically mean an approved decision.
6. Optionally enter one full local file path under **Watch one local file**. Only that exact file is checked every 15 seconds while the app runs. Pause or resume it in the source panel.

No crew messages are sent. Checklist actions are suggestions for a person to handle; checking a box records their own progress. Original files are never overwritten.

## What is working

- Immutable revisions, exact line-position comparisons, deduplication, PDF page citations and explicit one-file watching.
- A real `strands.Agent` using the native `OllamaModel` provider and `@tool` functions: `read_updates` then `save_shift_brief`.
- Literal quote and source-snapshot validation before saving. If documents change mid-run, the result is rejected. Old handoffs remain visible and are marked outdated.
- Four-model-call and six-tool-call limits. The agent stops after its validated save. An unavailable model produces an error while comparison and saved exports remain usable.
- Persistent decision checklist, linked source excerpts, Markdown export, mobile layout, loopback-only service and local request-token/origin checks.

AI conclusions remain interpretations. Matching quotations do not prove every inference is right. The real test identified the schedule and destination conflict; one phrase generalized “not received” to “not sent.” The sources stay visible, and the prompt now explicitly preserves those distinct states. There is no claim of automatic factual approval.

## Runtime and tests

The installed Desktop copy has its own Python 3.12 environment. It requires the already-installed **Ollama** service and **qwen3.5:9b** for AI. No model is downloaded or cloud account used at runtime. [Strands documents native Python Ollama tool support](https://strandsagents.com/docs/user-guide/concepts/model-providers/ollama/).

For a fresh copy: install Python 3.12, then run `py -3.12 launch.py`. The launcher creates `.venv` and installs the pinned direct dependencies. `requirements-lock.txt` records the tested environment. To run manually: `.venv\Scripts\python.exe server.py --open`. Optional `--port` and `--state-dir` support isolated testing.

Run `.venv\Scripts\python.exe -m unittest -q test_shiftbrief`. Fourteen tests cover PDF extraction, revision order, duplicate imports, exact citations, source changes during inference, checklist/export persistence, watch pause/scope, actual HTTP protections and the decorated Strands tool boundary with a fake model. They do not spend model time.

The actual browser-triggered Strands/Qwen run completed in **18.453 seconds**, with **4 findings and 3 suggested decisions**, executing both tools and saving real results. Browser checks verified export, checklist reload, 390-pixel layout and no JavaScript errors. That first QA dataset contained two repeated pairs of fictional documents; the sample button has since been made idempotent. See `evidence/` for the unchanged test receipt and generated handoff.

Current limits: 5 MB per imported file; 80 PDF pages; extractable text only (no OCR); at most eight documents and 36,000 serialized characters across their latest two revisions for one AI briefing. Larger imports can be compared, but require a focused excerpt workspace for synthesis. Watching is local and stops when the server stops. This is a single-owner local workspace, not multi-user hosting or a production notification service.

## Contest and provenance

[Official rules](https://agentsforhumans.devpost.com/rules) require a new in-window project using Strands, disclosure of incorporated pre-existing work, a public MIT/Apache repository, README, architecture diagram, public demo of at most five minutes, and AWS Builder ID. They also list AWS account signup. AgentCore deployment is optional. Registration, account requirements, public repository, demo and submission remain for the owner; none were completed automatically. Personal eligibility is subject to the listed age, location and affiliation conditions.

ShiftBrief was created September 7, 2026. It is a new focused successor to the source-revision/evidence workflow explored in ClearTrail, built September 6 in the same event window. **ClearTrail's concept informed the design; its application code or personal state was not copied.** New Strands orchestration, production-specific handoff workflow, explicit file watching and decision checklist distinguish this entry. Older Sarah/ContextGate and current personal KiraWorld/Video Studio code or data are not included. Codex assisted implementation. Include this disclosure in the final entry.

The [official prior AWS hackathon winners announcement](https://aws-agent-hackathon.devpost.com/updates/38140-congratulations-to-the-winners-of-the-aws-ai-agent-global-hackathon) names AgentShell Best Strands SDK Implementation. Its [creator description](https://devpost.com/software/agent-shell) describes a tool-driven sensing/action loop. Our design inference is to demonstrate an observable completed tool action and usable saved result, rather than a list of future capabilities. No AgentShell code is reused.

## Submission work remaining

- Review the actual app and generated handoff; decide whether this is the entry to submit.
- Confirm registration, personal eligibility, AWS account and Builder ID requirements.
- Publish only the clean source package with MIT license; exclude `.venv/`, `data/`, personal documents and tokens.
- Record a five-minute-or-shorter public demo showing a real source edit, the exact difference, Strands tool calls, saved handoff, checked decision and export.
- Add the project description, [architecture diagram](ARCHITECTURE.svg), technical/runtime instructions and reuse/AI-assistance disclosure to the submission.

No purchase, paid cloud resource, public publishing, contest submission or external message was performed.
