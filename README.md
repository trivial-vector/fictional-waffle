# Assistant Long-Term Memory

A personal-assistant memory system using the same NWM-style "compress into
typed, evidence-backed lookup cues" architecture as `../Claude_Storytelling`'s
narrative engine, remodeled for real people and an ongoing assistant
relationship instead of a fictional cast and plot. See `DESIGN.md` for the
full reasoning, including exactly what carried over unchanged, what changed
and why, and a privacy/data-handling section worth reading before pointing
this at real conversations.

A web UI (chat + a memory browser/editor) sits on top of the same backend —
see §"Web UI" below.

## Layout

```
├── DESIGN.md                 # architecture, what changed from the narrative engine, privacy notes
├── docker-compose.yml        # postgres+pgvector, ollama (1080 Ti), vllm (3090), assistant, voice, web
├── docker-compose.test.yml   # STANDALONE — offline UI/voice test harness, see "Offline test harness" below
├── .env.example
├── assistant/                 # the FastAPI backend — no longer serves the web UI (see web/ below)
│   ├── app/
│   │   ├── config.py
│   │   ├── db/
│   │   │   ├── schema.sql      # user_profile, person_record, relationship_record,
│   │   │   │                   # standing_fact, episodic_event, commitment
│   │   │   ├── postgres.py     # hybrid (lexical+vector) search + generic list_table for the memory browser
│   │   │   └── graph.py        # Kuzu: Person/Commitment nodes, RelatesTo/Concerns edges
│   │   ├── models/records.py
│   │   ├── llm/
│   │   │   ├── anthropic_client.py   # response generation (Sonnet default / Opus escalated)
│   │   │   ├── vllm_client.py         # consolidation/reflection pass (3090) — repurposed NPC seat
│   │   │   └── ollama_client.py       # per-turn extraction + embeddings (1080 Ti)
│   │   ├── routing/escalation.py     # sensitive-topic escalation
│   │   ├── pipeline/
│   │   │   ├── mention_matching.py    # pure logic: known-person + open-commitment touch detection
│   │   │   ├── retrieval.py           # two-stage hybrid search + one-hop graph expansion
│   │   │   ├── response.py            # reply composition + tier routing
│   │   │   ├── memory_writer.py        # NEW — shared record-write path (extraction pass AND manual entry)
│   │   │   ├── extraction.py          # per-turn typed-record writes, now via memory_writer
│   │   │   ├── file_ingest.py          # NEW — text extraction for chat file attachments (txt/md/pdf)
│   │   │   ├── consolidation.py       # periodic episodic->standing-fact synthesis (DESIGN.md §4)
│   │   │   └── turn.py                # ties the live conversation turn together
│   │   └── api/routes.py     # /api/message (multipart, optional file), /api/consolidate,
│   │                          # /api/memory/{kind} (list/create), /api/memory/search/{kind}
│   ├── tests/                # pytest — pure-logic tests, no live infra required
│   ├── Dockerfile             # build context is ./assistant — backend only
│   └── requirements.txt
├── voice/                     # local speech-to-text microservice (faster-whisper, CPU)
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
├── web/                       # STANDALONE — chat + memory browser, own nginx container,
│   │                           # deployable on a different host than everything else
│   ├── index.html              # chat page: text input, mic button, file-attach button
│   ├── memory.html             # memory browser/editor, linked from the chat page
│   ├── config.js.template      # templated into config.js at container start (envsubst)
│   ├── docker-entrypoint.sh    # renders config.js from ASSISTANT_API_BASE_URL/VOICE_SERVICE_URL, then execs nginx
│   ├── nginx.conf
│   ├── Dockerfile
│   └── static/
│       ├── style.css
│       ├── chat.js
│       └── memory.js
├── mock-backend/               # STANDALONE — offline stand-in for assistant/, used only by
│   │                            # docker-compose.test.yml, see "Offline test harness" below
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
└── scripts/
    ├── init_db.py
    ├── pull_local_models.sh
    └── seed_demo_memory.py
```

## Web UI

Runs as its own container (`web/`, nginx serving plain static files — no
build step), completely decoupled from `assistant`. That's deliberate: this
container can run anywhere — the same desktop, or a genuinely separate
machine (a laptop, the MacBook Air per the hardware topology doc, whatever)
— as long as it can reach the `assistant` and `voice` services over the
network. Nothing about it assumes it's on the same host as the backend.

What makes that possible: `index.html`/`memory.html` load a `/config.js`
before their own JS, and that file isn't static — `docker-entrypoint.sh`
renders it from `config.js.template` at container *start*, substituting in
the `ASSISTANT_API_BASE_URL` and `VOICE_SERVICE_URL` environment variables
(via `envsubst`). So the same built image can point at different backends in
different deployments without a rebuild — just set those two environment
variables in `docker-compose.yml` (or however you run the container).

Because every call from the web UI to the backend is now cross-origin by
construction rather than an edge case, `assistant`'s CORS policy (wide open —
see `main.py`) is load-bearing, not incidental. Same for `voice`.

**Chat page** (`index.html` / `chat.js`): a text box, a mic button, an attach
button, and a send button. The mic button records via the browser's
`MediaRecorder`, uploads the clip to the local `voice` service, and drops the
returned transcript into the text box — nothing is sent to a third-party
transcription API (see `voice/app.py`'s docstring for why that was a
deliberate choice, not a default). The attach button lets you pick a
`.txt`/`.md`/`.pdf` file; its extracted text gets appended to your message
before it's sent (`pipeline/file_ingest.py` — no OCR, and there's no separate
attachment record type, see that file's docstring for the scoping reasoning).
Each reply shows which tier answered it (`default`/`escalated`) and which
open commitments it touched.

**Memory page** (`memory.html` / `memory.js`): tabs for each of the six
typed-record tables. Lists existing records, supports hybrid search within a
type, and has an add/update form per type that writes through the exact same
`pipeline/memory_writer.py` path the automatic extraction pass uses — so a
manually-added person or fact behaves identically to one the assistant
inferred from conversation.

**Known rough edge**: the backend has no session/turn-counter persistence
(flagged since the first version of this design). The web UI works around
this by tracking a session id and an incrementing turn counter in
`localStorage`, client-side — functional for a single browser/single user,
but it's a workaround sitting on top of an unresolved gap, not a fix to it.

## Offline test harness

`docker-compose.test.yml` brings up `web` and `voice` completely disconnected
from the real `assistant` service — no Postgres, no Kuzu, no Ollama/vLLM, no
`ANTHROPIC_API_KEY`, and no network reachability to the desktop that owns the
GPUs at all. It exists to answer "does the interface work" and "does local
voice transcription work" as questions you can test anywhere (a laptop with
no GPU, on a plane, before the desktop is even set up), separately from "does
the memory pipeline actually work."

It runs three services:

- **`mock-backend`** (new, `mock-backend/`) — a small in-memory FastAPI app
  that reproduces `assistant/app/api/routes.py`'s HTTP surface closely enough
  for the web UI to talk to it: canned chat replies (cycling through a few
  fixed strings so you can see the round trip), and a real in-memory
  read/write store for the memory browser's six tabs, seeded with one throwaway
  record per type. Nothing persists across a restart, and there is no
  retrieval/extraction/consolidation/escalation logic — it's a UI test
  double, not a backend. See its docstring for the "don't mistake this for a
  working real backend" caveat, worth reading before relying on it for
  anything beyond interface testing.
- **`voice`** — the *real* voice service, `./voice` unmodified. It was never
  coupled to the GPU desktop (CPU-only faster-whisper), so this is a genuine
  test of the actual local transcription pipeline, not a mock of it.
- **`web`** — the *real* web UI, `./web` unmodified, just pointed at
  `mock-backend` instead of `assistant` via the same `ASSISTANT_API_BASE_URL`
  mechanism used for remote deployment above.

Run it:

```
docker compose -p assistant-test -f docker-compose.test.yml up --build
```

Then open `http://localhost:8084`. Ports are offset from the real stack
(8083/8084/8093 here vs. 8081/8082/8092) so both `docker-compose.yml` and
`docker-compose.test.yml` can run at the same time without colliding, if you
ever want to compare them side by side — but this file reuses the `voice`
and `web` service names from `docker-compose.yml`, so the explicit `-p
assistant-test` project name above matters: without it, Compose's
default project name (the directory name) would be shared by both, and
their containers/networks would collide on name even though the ports
don't.

What this is good for: checking the chat page renders and posts correctly,
the mic button records and gets a real transcript back from `voice`, the
attach-file button and chip UI work, and the memory browser's tabs/search/
add-forms round-trip against *something* — all without touching the desktop.
What it's *not* good for: judging reply quality, memory accuracy, escalation
routing, or anything pipeline-related — that all requires the real
`assistant` service and the full `docker-compose.yml` stack.

## Running it

**Everything on one machine (simplest):**

1. `cp .env.example .env`, fill in `ANTHROPIC_API_KEY`. Check `nvidia-smi -L`
   and set `VLLM_GPU_DEVICE_ID`/`OLLAMA_GPU_DEVICE_ID` correctly — don't trust
   the example defaults blindly, especially if the narrative engine stack is
   also configured on this same machine (see note below). Leave
   `ASSISTANT_API_BASE_URL`/`VOICE_SERVICE_URL` unset — their `localhost`
   defaults are correct for this case.
2. `docker compose up -d postgres ollama vllm voice`, wait for vllm's
   first-run model download (`docker compose logs -f vllm`) and voice's
   first-run Whisper model download (`docker compose logs -f voice`).
3. `./scripts/pull_local_models.sh`
4. `docker compose up -d assistant web`
5. From `assistant/`: `PYTHONPATH=. python ../scripts/seed_demo_memory.py`
6. Open `http://localhost:8082/` in a browser. Try "How is Sarah doing
   lately?" — should touch `commit_checkin_sarah` and `fact_checkin_sarah`
   (both `sensitive: true`), escalating the reply to Opus, visible in the
   reply's tier label.
7. Open `http://localhost:8082/memory.html` to browse or hand-add records.
8. Trigger consolidation manually whenever you want it to run (it is **not**
   wired to any schedule): `curl -X POST 'http://localhost:8081/api/consolidate'`
   — folds `event_sarah_rough_week` into updated person/standing-fact state.

Note the web UI's own port is **8082** — separate from `assistant`'s 8081,
since they're different containers now. The API itself lives under `/api/*`
on 8081.

**Web UI on a different machine than the backend:** build/run everything
above except `web` on the machine with the GPUs, then on the second machine:

```
docker build -t assistant-web ./web
docker run -d -p 8082:80 \
  -e ASSISTANT_API_BASE_URL=http://<desktop-lan-ip>:8081/api \
  -e VOICE_SERVICE_URL=http://<desktop-lan-ip>:8092/transcribe \
  assistant-web
```

(or set those same two variables on the `web` service in `docker-compose.yml`
and run it via compose on the second machine instead, pointed at the same
repo checkout — either way works, since the image doesn't embed the backend
URL at build time, only at container start.) Confirm the desktop's firewall
allows inbound connections on 8081 and 8092 from the second machine.

**Voice input requires either HTTPS or `localhost`.** Browsers only grant
microphone access (`getUserMedia`) on secure origins. `http://localhost:8082`
works fine for local use; accessing the web container from another machine
(the remote-deployment case just above) over plain `http://` will make the
mic button fail even though the rest of the UI works — that needs a reverse
proxy with a real or self-signed cert in front of the `web` container, which
this prototype doesn't include.

**Running alongside the narrative engine stack**: all host ports in this
`docker-compose.yml` are offset from `Claude_Storytelling/prototype`'s
(5433/11435/8001/8081/8092/8082 vs. 5432/11434/8000/8080) so both can run at
the same time without port collisions — but both stacks will try to claim the
same GPU device_ids by default, since it's the same physical desktop. Only
run one stack's `vllm`/`ollama` services at a time unless you've deliberately
partitioned differently.

## What's verified vs. not

Built and verified in the same sandboxed environment as the narrative
engine's prototype, with the same constraints (no GPUs, no Docker, no live
Postgres/Kuzu/Ollama/vLLM/Anthropic/Whisper access, no browser to test
MediaRecorder/getUserMedia against, no network route to install real
dependencies). What was actually checked this round:

- Every `.py` file under `assistant/app/`, `scripts/`, `voice/`, and
  `mock-backend/` passes a syntax compile check.
- The existing pure-logic test suite (`pipeline/mention_matching.py`,
  `routing/escalation.py`, 11/11) was re-run after the `memory_writer.py`
  refactor to confirm it didn't regress anything — still 11/11 passing.
- The three JS files (`chat.js`, `memory.js`) pass `node --check` (syntax
  only — no DOM, no fetch, no MediaRecorder available to actually exercise in
  this sandbox).
- Both `docker-compose.yml` and `docker-compose.test.yml` parse as valid YAML
  and their port mappings don't collide with each other or with the
  narrative engine's stack.

**Not verified, needs your actual hardware/browser to confirm** — everything
from before, plus: the entire web UI end-to-end (rendering, fetch calls, the
memory browser's forms), MediaRecorder → voice service → transcript-into-
textbox flow, file attachment extraction (especially PDF via `pypdf`), CORS
behavior in an actual browser, the FastAPI multipart-form `/api/message`
endpoint (mixing `Form(...)` fields, an optional `UploadFile`, and a query
param in one route — a shape that should work per FastAPI's documented
parameter-resolution rules, but wasn't exercised against a live server this
session), the `envsubst`-based `config.js` templating in `web/docker-
entrypoint.sh` (standard, well-worn pattern, but not run against a live
`nginx:alpine` container this session), and `mock-backend/` end-to-end (it's
a much simpler surface than the real backend — no DB, no multipart edge
cases beyond a single optional file — but still unexercised against a live
`web` container and browser this session).

Read `DESIGN.md` §7 (Privacy and data handling) before pointing this at real
conversations, and note it now applies to voice input too: keeping
transcription local (rather than a browser-native cloud STT API) was a
deliberate extension of that same stance, not an afterthought.
