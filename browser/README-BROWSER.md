# ShiftBrief browser edition · verified September 7, 2026

This is a deployable static browser asset bundle. Host the complete folder on HTTPS; a judge then opens its URL in an ordinary current browser. Do not describe double-clicking index.html or extracting this bundle as the judge launch experience. Local verification used Edge at http://127.0.0.1:8898; the production hosting path still requires its own check by the hosting owner.

The browser downloads its public Python runtime and source modules from the same origin. Employee availability, operating hours, closures, schedules, handoffs and conversations run in the browser worker. No installed Python, model, provider key, paid credits or voice pack is required. No owner data or example staff is loaded at first launch. “Try fictional team” is an explicit, separate example.

## What works

- Saved teams; hire by conversation and dated seven-day availability; employee end dates, preferences and time off.
- Reviewed customer hours, opening/closing staffing buffers, overnight/24-hour settings and owner-entered annual/date closures.
- Read-only weekly proposals, edits, explicit acceptance, coverage gaps and hours; sick-day candidate ranking and lunch options; old dated revisions and restores.
- Source text/PDF imports, exact revision comparison, free source-backed Sarah, saved cited handoffs and reviewable checklist changes.
- Real day CSV, week ZIP and Markdown handoff downloads. Workspace-copy ZIP save and explicit restore from the header ⋯ control.

## Storage and limits

The workspace lives in IndexedDB in this browser profile. This is not cloud sync and does not survive clearing that profile's data. Save a workspace copy to keep a separate backup or move it. Requests serialize through Web Locks; another tab's saved version is loaded before each action. Conflicting employee revisions and stale schedule proposals fail visibly. A storage write failure restores the previously committed workspace before reporting failure. Switching teams in another tab is guarded against silently saving to the wrong team.

Calendar phrases use the browser's local date and time zone; stored history timestamps carry an offset. Selected dates remain exact. Uploaded PDF text is extracted locally with pypdf 6.10.2; scanned documents need OCR before import. Sources are limited to 5 MB and 80 PDF pages; workspace copies to 50 MB ZIP / 100 MB uncompressed state.

The free Sarah engine is deterministic and bounded by supported operations and saved facts. It is not a general-purpose language model. This edition does not execute Strands, local file watchers, optional Ollama or the Desktop voice engine. The separate Desktop project preserves its actual Strands integration; browser tests do not demonstrate that contest requirement. Scheduling suggestions are feasibility aids, not optimality, legal-compliance or payroll claims. No calls, messages or reservations are sent.

## Verification

Actual browser cold boot with no external/API network requests; 43 focused domain tests executed in WebAssembly; exact PDF source-line/page extraction; nine scheduling UI actions; 93 screen/form layout cases at 3440×1311, 1920×1080, 1366×768, 768×1024, 390×844 and 320×568. No measured page/pane overflow or offscreen controls in those cases. Separate workspace-copy controls also passed all six sizes.

Durability checks passed reload and complete browser restart, simultaneous tab additions, stale employee edits, changed-team guard, simulated IndexedDB failure rollback, malformed copy rejection, failed restore rollback, valid copy restore and New York/Kiritimati date-boundary behavior. These are engineering checks, not owner or judge acceptance.

## Hosting handoff

Serve .mjs as JavaScript, .wasm as application/wasm and .zip intact. All asset and worker paths are relative, including runtime and PDF library. Keep browser-files.json hashes aligned with the eight Python/vendor inputs. Public caching may cache code assets; user state is never stored in them. Web Locks and IndexedDB require a secure context (HTTPS or localhost). There is no service worker and offline cold-start availability is not claimed.

No .openai Site checkout, hosting config, private state, voice model, API credential, QA fixture or test profile is included. The hosting owner must check the actual deployed path, headers, six-size layout, persistence and export downloads before sharing its judge URL.

## Upstream notices

See runtime/licenses/NOTICE.txt and the individual Pyodide 314.0.6, Python 3.14.2 and pypdf 6.10.2 notices. sources.json records exact upstream URLs and verified SHA256. These libraries retain their respective licenses; their source locations are included. Bundle-manifest.json records every included file hash.
