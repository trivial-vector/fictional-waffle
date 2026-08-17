# Assistant Long-Term Memory — Design Document

Status: living draft, remodeled from `Claude_Storytelling`'s narrative engine. That
project's `narrative-engine-design.md` is the architectural ancestor of this one —
read there for the original reasoning on why typed-record compression beats pure
vector or pure GraphRAG memory. This doc covers what's shared, what changed, and why.

## 1. What carries over unchanged

The core memory philosophy is domain-independent and carries over exactly:

- **Compress into typed, evidence-backed records, not raw transcript or a generic
  entity/edge graph.** Each record is short, structured, embeddable as a lookup
  cue, and a node in a lightweight relationship graph — the same "compress context
  into cues, not verbatim replay" idea from the original brief, grounded in the
  same research (Narrative World Model's typed memory records, evidence-backed
  and chapter-scoped, merging into cumulative current-state registries rather than
  growing logs).
- **Two-stage hybrid retrieval**: cheap lexical+vector search over the compact
  records, then one-hop graph expansion from matched entities, with the option to
  follow an evidence pointer back to the source conversation when exact wording
  matters.
- **The stack**: Postgres + pgvector for typed records and hybrid search, Kùzu
  (embedded, no server process) for the relationship graph, Ollama on the 1080 Ti
  for structured extraction + embeddings, a frontier API model for the
  highest-judgment generation, and a sensitive-topic escalation router.
- **Evidence-backing and validity intervals**: every record keeps a pointer to the
  conversation/turn that produced it, and time-scoped facts carry `valid_from`
  (and `valid_to` where a fact can become stale) rather than being asserted as
  permanently true.

## 2. What changed, and why

The narrative engine's schema and pipeline are shaped around *fiction-specific*
concerns that don't apply to an assistant: an adaptive plot skeleton, NPCs with
obligations to a story, precondition/re-planning logic for player-driven
divergence. None of that has an analog here — an assistant isn't running a plot.
What it needs instead is closer to NWM's actual original context (a writer's
memory of what's been established) crossed with human episodic/semantic memory:
things that happened, durable facts, people, and open loops.

| Narrative engine concept | Assistant equivalent | Notes |
|---|---|---|
| `character_state` | `person_record` | People the user talks about — not the user themself (see `user_profile`) |
| `relationship_state` | `relationship_record` | Same shape: pair, type, polarity, valid-from |
| `world_fact` | `standing_fact` | Durable facts/preferences, now about the user's real life, not a fictional world |
| *(implicit in narration)* | `episodic_event` | **New.** Discrete, timestamped things that happened/were discussed. Fiction didn't need this as a separate table because the narration turns themselves were the episodic layer; an assistant's conversations need it modeled explicitly. |
| `plot_beat` + `npc_obligation` | `commitment` | The single most direct conceptual carryover: a fiction "promise/payoff" (planted setup that must eventually pay off) is structurally identical to "the assistant said it would follow up on X" — both are open loops that need tracking until resolved. |
| Adaptive skeleton + re-plan step | **Dropped.** | No plot to diverge from. The closest surviving idea is: if a new message touches an *open commitment*, surface and possibly resolve it — no re-planning involved, just relevance detection (see `pipeline/extraction.py` and the simplified alignment logic in `pipeline/retrieval.py`). |
| Multi-agent NPCs (vLLM on 3090) | **Repurposed**, not dropped. | An assistant has one voice, not several simulated characters, so per-NPC generation doesn't apply. The 3090/vLLM seat is reassigned to the **consolidation/reflection pass** (§4) — a heavier local model that does periodic synthesis work, where vLLM's throughput advantage on modern hardware is still the right fit, just for a different job. |
| `divergence_log` | **Dropped**, not replaced. | Was specifically about plan deviation. No equivalent need here. |

## 3. Schema summary

Full DDL in `assistant/app/db/schema.sql`. Six tables:

- **`user_profile`** — the user themself: name, timezone, standing communication
  preferences. Effectively a singleton (multi-profile support is not built, but
  the schema doesn't prevent it).
- **`person_record`** — people other than the user: name, how they relate to the
  user, notes, last-mentioned turn.
- **`relationship_record`** — pairs of people (including user-to-person), relation
  type, polarity, valid-from.
- **`standing_fact`** — durable facts/preferences, tagged `sensitive` where
  relevant (drives escalation routing, §6).
- **`episodic_event`** — discrete happenings: summary, participants, approximate
  date, category, sentiment, `sensitive` flag.
- **`commitment`** — open loops: description, status (open/completed/dropped/
  deferred), who it concerns, `sensitive` flag.

## 4. Consolidation — the actual "human-like" part

This is the piece that's genuinely new relative to the narrative engine, not just
a renamed table. Per-turn extraction (small local model, same mechanism as
before) captures what just happened cheaply and immediately — this is the fast,
automatic encoding layer. But human memory doesn't work by keeping every raw
episodic trace forever and re-scanning all of it; it consolidates: recent
episodic detail gets compressed into stable schema/gist memory over time, which
is the entire "compress context into lookup cues" idea from the original brief,
applied literally to the assistant's own memory of itself rather than just to
retrieval.

So this system adds a periodic **consolidation pass** (`pipeline/consolidation.py`,
run on a schedule or triggered manually — not on every turn) that:

1. Pulls `episodic_event` records accumulated since the last consolidation.
2. Asks a model to merge them into updated `person_record` / `standing_fact`
   current-state (the same "cumulative registry, not growing log" principle as
   the narrative engine's core design).
3. Optionally synthesizes higher-level observations that don't correspond to any
   single event (e.g., a pattern noticed across several episodic mentions) —
   the generative-agents-style "reflection" step.

This runs on the model now sitting on the 3090 via vLLM — larger and
higher-quality than the per-turn extraction model, justified because
consolidation isn't latency-critical (it's explicitly meant to run when the user
*isn't* actively waiting on a reply, mirroring offline memory consolidation
rather than live encoding).

## 5. Turn (conversation) pipeline

Replaces the narrative engine's 8-step turn pipeline:

1. User sends a message.
2. Cheap entity-mention pass over the raw message (same mechanism as the
   narrative engine's alignment check, retargeted): which known people are
   mentioned, and does this message touch any *open* commitment.
3. Retrieval: hybrid search over all typed record tables + one-hop graph
   expansion from mentioned people + any touched open commitments pulled in
   explicitly regardless of retrieval ranking.
4. Response generation, grounded in retrieved context, tier resolved by the
   escalation router (§6).
5. Extraction pass (small local model) writes new/updated typed records from the
   exchange — same mechanism as the narrative engine, different schema.
6. *(Not per-turn)* Consolidation runs separately, on schedule.

As of the web UI (§8), step 1 can arrive as typed text, a voice recording
transcribed locally before it ever reaches this pipeline, or a message with a
file attached whose extracted text is folded into the message body before
step 2 runs — the turn pipeline itself doesn't know or care which.

## 6. Escalation routing

Same mechanism as the narrative engine's `emotional_stakes` flag, retargeted:
`standing_fact.sensitive`, `episodic_event.sensitive`, and `commitment.sensitive`
drive escalation to the higher-tier model when retrieved/touched context includes
a flagged record, plus the same category of crude keyword-based placeholder for
emergent sensitive topics not yet captured in any record — flagged as a
placeholder in code exactly as it was in the narrative engine, for the same
reason (a real implementation needs a proper classifier).

## 7. Privacy and data handling

Worth stating plainly, since this is a real change from the storytelling
project: that system's memory was about fictional characters. This one's memory
is about real people — the user, and everyone the user mentions, none of whom
consented to being modeled in a database. Practical implications, not fully
resolved by this design, flagged here rather than ignored:

- Every record sent to the frontier API (response generation, and now
  consolidation-tier data if that pass ever escalates) leaves the local network.
  Anthropic's API data-handling terms apply; read them before deciding what's
  comfortable to send if this holds sensitive material.
- The extraction and consolidation passes run entirely locally (Ollama/vLLM on
  the desktop) by design — that's a real, load-bearing property of this
  architecture, not incidental: the model that reads every raw message and does
  the heaviest synthesis over accumulated personal detail never leaves the
  machine you own. Only the retrieved, already-typed record context needed to
  answer a given message goes to the frontier API.
- No encryption-at-rest, access control, or per-person data deletion path is
  implemented in this prototype. For anything beyond personal/single-user use,
  that gap should be closed before real people's data accumulates in it —
  tracked in the open-questions list, not solved here.
- Voice input extends this stance rather than complicating it: transcription
  runs locally (`voice/`, faster-whisper on CPU) specifically so raw audio
  never leaves the machine either, deliberately avoiding the browser's
  built-in cloud speech-recognition API. See §8.

## 8. Web UI

A chat page and a memory browser/editor sit on top of this backend — full
details in `README.md` ("Web UI" section), kept there rather than duplicated
here since it's operational, not architectural. Two things worth noting at
the design level:

- **The memory browser writes through the same path as automatic extraction.**
  `pipeline/memory_writer.py` was factored out of `extraction.py` so that a
  person/fact/commitment you add by hand in the UI and one the assistant
  infers from conversation are indistinguishable to the rest of the system —
  same validation, same embedding, same graph mirroring. This matters for the
  "human-like memory" framing from the original brief: a good long-term
  memory system should let you correct or seed it directly, not only learn
  passively.
- **Voice-to-text is a separate local service, not a browser API call**, for
  the same privacy reasoning as §7 — worth restating here because it was a
  live design choice (browser-native `SpeechRecognition` would have been
  less code), not a default.
- **The web tier is a separate deployable unit from the backend tier**, not
  bundled into the `assistant` container. This is the same "client vs.
  server" split as the narrative engine's hardware topology doc (thin client
  reaching over the network to wherever the heavier services actually run),
  applied to this project: the backend needs the GPUs and stays on the
  desktop, but nothing about a chat/memory UI requires being co-located with
  them. Runtime-configurable backend URLs (`web/config.js.template`,
  rendered at container start) are what make that possible without baking a
  specific host into the built image.
- **The web UI can be tested against a fake backend, not just no backend.**
  `docker-compose.test.yml` + `mock-backend/` reuse the exact same
  configurable-URL mechanism to point the real `web` container at an
  in-memory stand-in instead of the real `assistant` service — see
  `README.md`'s "Offline test harness" section. This falls directly out of
  the point above: once the backend URL is just a runtime variable, "point it
  at a fake" and "point it at a remote real one" are the same mechanism, not
  two separate features.

## 9. Open questions

- [ ] Consolidation schedule/trigger: time-based (nightly), turn-count-based, or
      manually invoked? Not decided — the API exposes a manual trigger endpoint
      either way.
- [ ] Retention/deletion: no policy implemented for removing a person's data on
      request. Needed before this holds real third-party information long-term.
- [ ] The commitment-touch detection (step 2 of the turn pipeline) uses the same
      simplified substring-matching approach flagged as a placeholder in the
      narrative engine — same caveat applies here.
- [ ] Sensitive-topic keyword placeholder (§6) needs replacing with a real
      classifier before relying on it for anything that matters.
- [ ] No sessions/turn-counter persistence layer, same gap as the narrative
      engine's prototype — the web UI works around it client-side (localStorage)
      rather than fixing it server-side.
- [ ] File attachments have no dedicated record type or storage — extracted
      text is folded into the message and nothing else; see
      `pipeline/file_ingest.py`.
- [ ] Voice input requires HTTPS or `localhost` (browser security requirement
      for microphone access) — no reverse-proxy/TLS setup is included for LAN
      access from another device.

See `assistant/README.md` for run instructions and what's been verified vs. not.
