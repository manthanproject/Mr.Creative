# Mr.Creative — Project Handoff

## What This Is

A Flask app that combines LLM planning (Groq / Cerebras) with browser-automation backends to produce marketing creative at scale across three Google products:

- **Pomelli** (`labs.google.com/pomelli/`) — Campaign idea-cards + creative animation; Photoshoot mode (product shots from templates).
- **Flow** (`labs.google/fx/tools/flow/`) — A+ infographic / banner generation in batches.
- **Gemini** (`gemini.google.com/`) — Image generation with reference image (clipboard-paste flow).

Two execution backends share most of the Flask plumbing:

1. **Selenium backend** — attaches to a running Chrome via `--remote-debugging-port`, drives one account at a time. `modules/selenium_bot.py`, `modules/flow_bot.py`.
2. **Chrome extension backend** — one extension instance per Chrome profile, polls the Flask server every 3s and dispatches RUN_JOB messages to content scripts. Multiple Google accounts run in parallel. `extension/`, `routes/extension.py`.

The user toggles between them per page via the `🤖 Selenium / 🧩 Extension` button (defaults to Extension).

---

## Layout

```
mr_creative/
├── app.py                      # Flask factory. Registers blueprints, CORS (flask-cors), MAX_CONTENT_LENGTH=50MB, sets active account from active_accounts.json.
├── config.py / config.example.py
├── models.py                   # SQLAlchemy: User, Project, Generation, Collection, Prompt, NightReport, NightTrend, NightCompetitor, ContentPlan, etc.
├── launch_profiles.py          # Scans %LOCALAPPDATA%\Google\Chrome\User Data\ for profiles with "Mr.Creative Bot" extension; launches each at /pomelli/campaigns.
├── launch_profiles.bat         # `cd /d %~dp0 && python launch_profiles.py`
│
├── routes/
│   ├── auth.py / collections.py / projects.py / prompts.py
│   ├── generate.py             # Pomelli Selenium endpoints (run_full_workflow), bot status, pause/resume/clear-jobs
│   ├── banners.py              # Flow Selenium endpoints, banner job lifecycle
│   ├── agent.py + agent_pipeline.py  # LLM plan → multi-step pipeline; emits flow jobs into _state['job_data']
│   ├── extension.py            # /api/ext/* — the extension bridge
│   ├── night_ops.py            # Overnight intelligence dashboard (trends, competitors, plans, reports)
│   ├── scheduler.py            # Cron-style job scheduler
│   └── social.py / compare.py
│
├── modules/
│   ├── selenium_bot.py         # PomelliBot (campaign + photoshoot)
│   ├── flow_bot.py             # FlowBot (banner generation)
│   ├── flow_runner.py          # Drives reuse_project=true/false batches
│   ├── prompt_library.py       # expert_prompts by content_type
│   ├── prompt_previews.py      # md5 hash → image path (static/data/prompt_previews.json)
│   ├── agent_pipeline.py       # LLM → plan → dispatch (Selenium and/or Extension)
│   └── night_orchestrator/     # Trend/competitor/report agents
│
├── extension/
│   ├── manifest.json           # MV3. permissions: activeTab/tabs/storage/downloads/scripting/alarms/debugger/clipboardWrite/clipboardRead.
│   │                           # host_permissions: pomelli (with /u/N/ prefix), flow, gemini, localhost:5000.
│   ├── background.js           # Service worker. Polls /api/ext/command (3s setInterval + chrome.alarms keepalive @ 24s).
│   ├── content/
│   │   ├── pomelli.js          # CampaignBot + PhotoshootBot
│   │   ├── flow.js             # Flow A+ batch generation
│   │   ├── gemini.js           # Gemini content script
│   │   └── gemini_picker_proxy.js  # MAIN world, document_start — intercepts showOpenFilePicker
│   ├── lib/utils.js            # MC.* helpers: waitFor/click(dispatchEvent)/uploadFile/sendStatus/getCardImages
│   └── popup/popup.{html,js}
│
├── templates/
│   ├── base.html               # Sidebar, showToast (app.js:153), showConfirm modal
│   ├── generate.html           # Pomelli UI (Campaign + Photoshoot tabs), engine toggle, progress polling
│   ├── banners.html            # Flow UI, engine toggle, progress polling
│   ├── agent.html              # Agent Studio (brand kit, jobs, content-type pills)
│   ├── collection_detail.html  # Lightbox + Set-as-prompt-preview
│   ├── prompt_library.html     # Custom prompts + URL-persistent category filter
│   ├── night_ops.html          # Cycle status banner, niche analyzer, reset button
│   └── scheduler.html / social.html / compare.html
│
├── static/
│   ├── js/app.js               # showToast, sidebar bindings
│   ├── data/
│   │   ├── prompt_previews.json
│   │   └── extension_profiles.json   # (legacy — launcher now auto-discovers from Chrome dirs)
│   ├── uploads/                # Dashboard-uploaded images (served at /static/uploads/, CORS open)
│   ├── downloads/              # Server-side downloads from /api/ext/download (job_id_index.ext naming)
│   └── outputs/collection_<id>/ # Final saved files; mirrored in Generation.output_path
│
├── pyrefly.toml + pyrightconfig.json   # selenium_bot.py and template_system.py excluded; reportCallIssue=none.
└── active_accounts.json / saved_accounts.json
```

---

## The Extension Backend (the part that needs the most context)

### Connection lifecycle

1. Extension loads → `getProfileId()` reads/creates a persistent ID in `chrome.storage.local`.
2. `detectAccount()` reads visible Google account from a Pomelli/Flow tab; `detectCapabilities()` returns `['campaign','photoshoot','gemini'] + storage.extraCapabilities` (e.g. `flow_active` if a Flow tab is open).
3. POST `/api/ext/register` → server adds to `_state['profiles'][profile_id]`.
4. `startPolling()` sets a 3s `setInterval` AND a `chrome.alarms` keepalive at `periodInMinutes: 0.4` (≈24s). The alarm restarts the interval if the service worker was put to sleep. Freshness threshold on the server is **60s**.

### Job state (in `routes/extension.py`)

```python
_state = {
    'pending_commands': {},   # profile_id → job (targeted; per-profile)
    'pending_any': None,      # job for any capable profile (fallback)
    'current_jobs': {},       # profile_id → job info (state, message, ideas, images, etc.)
    'selections': {},         # job_id → user selection (POPPED on read — exactly once)
    'job_queue': [],
    'profiles': {},           # profile_id → {account, capabilities, last_seen, cooldown_until, profile_dir}
    'job_data': {},           # job_id → FULL payload (for /finalize, /flow-complete lookups)
}
```

Cooldowns are auto-applied for 2 hours when status messages contain "unusual activity" or "rate limit". Profiles unseen for >60s are treated as `stale` and excluded from routing.

### Routing in `submit_job`

1. If `target_account` is set: route to the matching profile.
2. Else: pick the first non-cooldown, non-stale, non-busy profile whose `capabilities` includes the `job_type` (or has empty caps → wildcard).
3. Else: park in `_state['pending_any']`.

If `get_command` finds nothing in `pending_commands[profile_id]`, it falls back to consuming `pending_any` if the profile has capability + isn't in cooldown. **Auto-registers unknown profile_ids** on first poll so a server restart doesn't drop them.

Background.js layer: for flow/aplus jobs it **rejects** the command and re-submits back to the server unless `extraCapabilities` includes `flow_active` — i.e. only a tab actually on Flow accepts Flow work.

### Endpoints (all under `/api/ext/`)

| Endpoint | Method | Purpose |
|---|---|---|
| `/register` | POST | Profile self-registers (writes to `_state['profiles']`). |
| `/command?profile_id=X` | GET | Extension polls for work. Returns `204` if nothing. Auto-registers unknown profile. |
| `/ack` | POST | Extension confirms a job was dispatched to a tab. |
| `/status` | GET | Dashboard "Connected Accounts" panel reads this. Per-profile `active`/`stale`/`cooldown`. |
| `/status` | POST | Content script reports progress (state, message, ideas, images). |
| `/job-status/<id>` | GET | Dashboard polls for live job state. Checks `current_jobs` → `pending_commands` → `pending_any` → `job_queue`. |
| `/submit` | POST | Dashboard submits a job (includes `collection_id`, `user_id`). |
| `/upload-image` | POST | Dashboard uploads ref image → static/uploads/, returns URL. |
| `/selection/<id>` | GET | Content script polls; **`.pop()`** so each selection is consumed once (idea then animate). |
| `/selection/<id>` | POST | Dashboard sends user's idea/animate-cards selection. |
| `/download` | POST | Content script POSTs `{ url, index, job_id, is_base64 }`. Server saves to `static/downloads/{job_id}_{i}.{ext}`. |
| `/finalize` | POST | Server copies `static/downloads/{job_id}_*` → `static/outputs/collection_<id>/`, creates Generation rows, commits. Auto-creates collection if `collection_id` is empty/'auto'. |
| `/flow-complete` | POST | Flow variant: moves recently-modified files from `~/Downloads/` into `static/collections/<collection_id>/` (filter by `start_time` from `job_data`). |
| `/next` | POST | Advance queue after a job completes. |
| `/stop` | POST | Clear all queues, current jobs, selections, job_data. |

CORS: `flask-cors` handles `/api/ext/*` with `origins: "*"`. `app.py` has a `@app.after_request` adding `Access-Control-Allow-Origin: *` to `/static/uploads/` so the extension can fetch uploaded images cross-origin.

### Why downloads use base64

Pomelli/Flow image URLs are auth-cookie gated. The server can't fetch them with `requests`. So the content script:
1. `fetch(img.src, { credentials: 'include' })` — uses the page's cookies.
2. Converts blob → base64 data URI via `FileReader.readAsDataURL`.
3. POSTs `{ url: dataUri, is_base64: true, job_id }`.
4. Server splits at `,`, sniffs ext from header, `base64.b64decode`s, writes to disk.

`_extractCreativeImages` does the same fetch + `createImageBitmap` → canvas thumbnail to render selection grids on the dashboard. `MAX_CONTENT_LENGTH = 50MB` in `app.py`.

### CampaignBot main flow (extension/content/pomelli.js)

```
1. waitFor(textarea, 30s) [bg.js already navigated to landing]
2. Type prompt → input event
3. (optional) Upload image — open imagesBtn dialog, find file input inside the .cdk-overlay-pane that contains app-upload-image-button, send_keys, click Update/Confirm. Wrapped in try/catch — failure skips, doesn't abort.
4. Set aspect ratio (Story/Square/Feed)
5. Click button.prompt-send-button
6. Wait for >=3 .campaign-idea-card (visible)
7. Build ideas[] from .idea-title + .idea-description (3 cards = 3 ideas, no dedup needed)
8. Send 'waiting_selection' with ideas → wait for user selection
9. Click selected card → waitForCreatives (shimmer/spinner/progress all 0 AND >=15s)
10. SMART ANIMATE: only if aspect_ratio includes '9:16' or === 'story':
    - scroll-to-bottom + back to trigger lazy-load
    - extract base64 thumbs from .creative-card-container img
    - 'waiting_animate' → wait for user selection
    - Snapshot videosBefore = document.querySelectorAll('video').length
    - Loop _clickAnimateButton(idx) for each selected (hover bubbles:false → click button.animate-button.mdc-button → 3s)
    - _waitForAnimationsToComplete(jobId, videosBefore) — page-level shimmer/spinner/progress=0 AND videoCount > before. 10-min timeout, 8s polls, gives up after 120s with no progress, aborts on "high demand"/"unusual activity" banner.
11. Download all .creative-card-container img srcs via base64 POST
12. POST /api/ext/finalize → saves to collection, creates Generation rows
13. location.href back to /campaigns landing (preserving /u/N/ prefix)
```

### Service worker quirks to watch

- MV3 service workers go to sleep. The `chrome.alarms.onAlarm` listener restores `setInterval` if it was nuked.
- `chrome.tabs.sendMessage` retries 3× with 5s gaps in `sendJobToTab`. If all fail, the job is re-submitted to the server (`POST /api/ext/submit`) so the content script can pick it up itself on next poll.
- Always navigate to the landing URL before sending `RUN_JOB` — the content script's JS context is destroyed on navigation, so navigating *from inside* the content script (the old approach) lost the job. `dispatchJob` does the navigation, waits for load + 5s Angular bootstrap, then sends.
- Multi-account URLs use a `/u/N/` prefix that must be preserved when building target URLs (`buildLandingUrl`).

---

## Selenium Backend Highlights

- `PomelliBot._try_reconnect_chrome` switches `window_handles` to dodge the Omnibox Popup tab.
- `_ps_click_mode_card` is a 30-tick poll with sidebar-click fallback at tick 10 and direct-URL fallback at tick 20 — Pomelli sometimes drops you on a sub-page after auth.
- `_ps_upload_and_select` scopes its DOM queries to the topmost `.cdk-overlay-pane` containing `app-upload-image-button` to avoid hitting a stale dialog from a previous run.
- `_ps_match_templates` hovers each `div.shot-thumbnail`, reads its label, dedupes, swaps via ActionChains.
- `flow_bot.upload_reference_image` clicks the prompt area before clicking + for Chrome focus.
- `generate_banners` uploads the reference image on every batch (not just the first) — gated by `if image_path:` outside the `else:` branch.
- LocalProxy unwrap pattern in background threads:
  ```python
  app = current_app._get_current_object()  # type: ignore[attr-defined]
  ```
  Used in `routes/generate.py`, `routes/banners.py`, `routes/scheduler.py`, `routes/night_ops.py`.

---

## Dashboard ↔ Extension Plumbing

Both `templates/generate.html` (Pomelli) and `templates/banners.html` (Flow) have the engine toggle. When `useExtension = true`:

1. Build job payload from form, including `collection_id: collectionSelect.value`.
2. If image input has a file: POST to `/api/ext/upload-image`, get back a `http://localhost:5000/static/uploads/...` URL; put that in `jobPayload.image_url`.
3. POST `/api/ext/submit` → server returns `{ job_id, routed_to }`.
4. Set `currentPollingJobId = data.job_id`, show progress panel.
5. `pollExtensionStatus(jobId)` runs every 2s:
   - `stateMap` translates `data.state` → `{ icon, title, step }`.
   - `progressMap`: navigating 5%, entering_prompt 15%, generating 35%, waiting_selection 45%, waiting_animate 60%, animating 70%, downloading 85%, **saving 95%**, complete 100%, error 0%.
   - On `waiting_selection`: render idea cards into `#ideasPanel`. On click: POST `/api/ext/selection/<id>` with `idea_index`.
   - On `waiting_animate`: render image grid into `#animatePanel`. Confirm → POST `animate_indices`.
   - On complete/error: stop polling, advance queue.

Connected Accounts panel in the right sidebar polls `/api/ext/status` every 10s. 🟢 = active, 🔴 = cooldown. Stale profiles are hidden from the "N profile(s) connected" count.

---

## State Files

| File | Purpose | Survives restart? |
|---|---|---|
| `active_accounts.json` | Currently-active account email for each tool (pomelli/flow). Loaded at startup. | Yes |
| `saved_accounts.json` | Account profile list (name, email, optional password). | Yes |
| `static/data/prompt_previews.json` | md5(prompt) → preview image path. Set via "Set as Prompt Preview" button. | Yes |
| `data/extension_profiles.json` | Legacy. Launcher now auto-discovers from Chrome dirs. | Yes |
| `static/uploads/` | Dashboard image uploads. | Yes |
| `static/downloads/` | Server-side downloads keyed by job_id. Cleaned up by finalize-move. | Eventually emptied |
| `static/outputs/collection_<id>/` | Final saved files. Mirrored in DB `Generation.output_path`. | Yes |
| `_state` (in-memory, routes/extension.py) | Job routing + profile registry. | **NO** — wiped on Flask restart. Profiles auto-register on next poll. |

---

## Gotchas / Lessons Hard-Won

- **Pyrefly + heterogeneous `_state` dict.** Many endpoints need `isinstance(x, dict)` / `isinstance(x, list)` guards because `_state.get(...)` is typed as the union of all value types. Pattern reused throughout `routes/extension.py`.
- **`_state['selections']` must `.pop()`** not `.get()` — the content script calls `_waitForSelection` twice (idea, then animate). If selections aren't consumed, the second call returns the stale idea selection immediately and skips animate selection.
- **JS `.click()` doesn't fire Angular's handlers.** `MC.click` uses `dispatchEvent(new MouseEvent('click', {bubbles, cancelable}))`. Same for animate buttons (opacity:0 until hovered) — use `mouseenter`+`pointerenter` with `bubbles:false` to avoid double-activation.
- **CDK overlays stack.** When uploading via the campaign image dialog, scope `querySelector` to the topmost `.cdk-overlay-pane` containing `app-upload-image-button`. Multiple stale overlays will otherwise return the wrong file input.
- **Pomelli campaign URLs.** `/pomelli/campaigns` is the landing page; `/pomelli/campaigns/b-xxxx` is a specific campaign. The regex `\/pomelli\/campaigns\/?$/.test(pathname)` distinguishes. Background.js navigates to the landing before sending RUN_JOB.
- **Content script navigation kills the job.** Never `location.href = '...'` and expect to continue. Always have background.js navigate.
- **MAX_CONTENT_LENGTH.** 50MB. Bumped because 4-image base64 payloads from `_extractCreativeImages` were getting rejected at ~16MB.
- **Animate aspect ratio.** Only Story (9:16) on Pomelli supports animate. Code gates on `aspect_ratio.includes('9:16') || aspect_ratio === 'story'`.
- **Idea card selector.** `.campaign-idea-card` (NOT `mat-card` or `[class*="idea"]`). Previous selectors matched parent containers and tripled the count.
- **Service worker keepalive.** Don't rely on `setInterval` alone; pair with `chrome.alarms` and a freshness window of 60s on the server.
- **Two backends, one UI.** Selenium and Extension paths share `collection_id`, `prompt_text`, `aspect_ratio` but route through entirely different endpoints. Don't accidentally migrate state from one backend's status dict into the other's.

---

## External Dependencies (manual setup required)

- **Pinterest API**: trial access pending (used in `night_orchestrator/pinterest_poster.py`).
- **Groq API key**: may need regeneration.
- **Chrome profile for `stocksmanthan@gmail.com`**: manual login required before bots can use it.

---

## Quick Start (next maintainer)

```bash
# 1. Run the server
python app.py
# Flask on http://localhost:5000

# 2. Launch Chrome profiles (each one auto-runs the extension)
python launch_profiles.py
# Scans ~\AppData\Local\Google\Chrome\User Data\ for profiles with "Mr.Creative Bot" extension.

# 3. Visit a job page (Pomelli/Flow/Agent Studio), make sure 🧩 Extension is selected.
# 4. /api/ext/status should show profile count > 0 within 10s.
# 5. Launch a job. Watch the Chrome tabs.
```

---

## Recent Architectural Decisions (worth remembering)

1. **Extension > Selenium as default** — multi-account parallel runs were impossible with Selenium's debuggerAddress (one Chrome attach at a time).
2. **flask-cors over manual `@after_request`** — manual headers leaked into non-API routes; flask-cors with `resources={r"/api/ext/*": {"origins":"*"}}` is scoped properly.
3. **base64 over server-side fetch** — auth-gated Google CDN URLs can't be fetched by the server. Content scripts fetch with `credentials:'include'` and ship as data URIs.
4. **Profile freshness check** — was 30s, widened to 60s after `chrome.alarms` periodInMinutes was set to 0.4 (≈24s).
5. **`pop()` selections** — selections that aren't consumed cause silent skipping of subsequent waits.
6. **Auto-register on `/command`** — server restarts dropped all profiles until they `/register` again on next manifest load. Auto-registration on first `/command` poll closes this gap.
