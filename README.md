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
├── docker-compose.yml        # postgres+pgvector, ollama (1080 Ti), vllm (3090), assistant, voice
├── .env.example
├── assistant/                 # the FastAPI service — backend + serves the web UI
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
│   ├── Dockerfile             # build context is the repo root — also copies web/ into the image
│   └── requirements.txt
├── voice/                     # NEW — local speech-to-text microservice (faster-whisper, CPU)
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
├── web/                       # NEW — chat + memory browser, plain HTML/CSS/JS, no build step
│   ├── index.html              # chat page: text input, mic button, file-attach button
│   ├── memory.html             # memory browser/editor, linked from the chat page
│   └── static/
│       ├── style.css
│       ├── chat.js
│       └── memory.js
└── scripts/
    ├── init_db.py
    ├── pull_local_models.sh
    └── seed_demo_memory.py
```

## Web UI

Served directly by the `assistant` container (no separate frontend container)
at `http://localhost:8081/` — the chat page — with the memory browser linked
from its header at `/memory.html`. The API lives under `/api/*` on the same
origin, so the chat/memory pages never cross an origin; only the mic button's
audio upload goes to a different container (`voice`, a different port),
which is why that service has CORS enabled and the assistant doesn't strictly
need it for its own UI (it's still enabled there too, in case something else
calls the API cross-origin later).

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

## Running it

1. `cp .env.example .env`, fill in `ANTHROPIC_API_KEY`. Check `nvidia-smi -L`
   and set `VLLM_GPU_DEVICE_ID`/`OLLAMA_GPU_DEVICE_ID` correctly — don't trust
   the example defaults blindly, especially if the narrative engine stack is
   also configured on this same machine (see note below).
2. `docker compose up -d postgres ollama vllm voice`, wait for vllm's
   first-run model download (`docker compose logs -f vllm`) and voice's
   first-run Whisper model download (`docker compose logs -f voice`).
3. `./scripts/pull_local_models.sh`
4. `docker compose up -d assistant`
5. From `assistant/`: `PYTHONPATH=. python ../scripts/seed_demo_memory.py`
6. Open `http://localhost:8081/` in a browser. Try "How is Sarah doing
   lately?" — should touch `commit_checkin_sarah` and `fact_checkin_sarah`
   (both `sensitive: true`), escalating the reply to Opus, visible in the
   reply's tier label.
7. Open `http://localhost:8081/memory.html` to browse or hand-add records.
8. Trigger consolidation manually whenever you want it to run (it is **not**
   wired to any schedule): `curl -X POST 'http://localhost:8081/api/consolidate'`
   — folds `event_sarah_rough_week` into updated person/standing-fact state.

Note the API moved under `/api/*` in this revision (it was unprefixed before
the web UI was added, to make room for serving the UI at `/`) — update any
existing scripts/bookmarks accordingly.

**Voice input requires either HTTPS or `localhost`.** Browsers only grant
microphone access (`getUserMedia`) on secure origins. `http://localhost:8081`
works fine for local use; if you access this from another machine on your
LAN (e.g. the Air, per the hardware topology doc) over plain `http://`, the
mic button will fail — that setup needs a reverse proxy with a real or
self-signed cert in front of it, which this prototype doesn't include.

**Running alongside the narrative engine stack**: all host ports in this
`docker-compose.yml` are offset from `Claude_Storytelling/prototype`'s
(5433/11435/8001/8081/8092 vs. 5432/11434/8000/8080) so both can run at the
same time without port collisions — but both stacks will try to claim the
same GPU device_ids by default, since it's the same physical desktop. Only
run one stack's `vllm`/`ollama` services at a time unless you've deliberately
partitioned differently.

## What's verified vs. not

Built and verified in the same sandboxed environment as the narrative
engine's prototype, with the same constraints (no GPUs, no Docker, no live
Postgres/Kuzu/Ollama/vLLM/Anthropic/Whisper access, no browser to test
MediaRecorder/getUserMedia against, no network route to install real
dependencies). What was actually checked this round:

- Every `.py` file under `assistant/app/`, `scripts/`, and `voice/` passes a
  syntax compile check.
- The existing pure-logic test suite (`pipeline/mention_matching.py`,
  `routing/escalation.py`, 11/11) was re-run after the `memory_writer.py`
  refactor to confirm it didn't regress anything — still 11/11 passing.
- The three JS files (`chat.js`, `memory.js`) pass `node --check` (syntax
  only — no DOM, no fetch, no MediaRecorder available to actually exercise in
  this sandbox).

**Not verified, needs your actual hardware/browser to confirm** — everything
from before, plus: the entire web UI end-to-end (rendering, fetch calls, the
memory browser's forms), MediaRecorder → voice service → transcript-into-
textbox flow, file attachment extraction (especially PDF via `pypdf`), CORS
behavior in an actual browser, and the FastAPI multipart-form `/api/message`
endpoint (mixing `Form(...)` fields, an optional `UploadFile`, and a query
param in one route — a shape that should work per FastAPI's documented
parameter-resolution rules, but wasn't exercised against a live server this
session).

Read `DESIGN.md` §7 (Privacy and data handling) before pointing this at real
conversations, and note it now applies to voice input too: keeping
transcription local (rather than a browser-native cloud STT API) was a
deliberate extension of that same stance, not an afterthought.
