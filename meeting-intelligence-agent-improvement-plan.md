# Plan: Turning the Meeting Intelligence Agent into a Top-Tier Project

The goal is to move the project from "a polished app on APIs" to **"a measured, secure, durable meeting-intelligence system with a differentiator."** The order matters, because each phase gives the next one something to measure against.

## Target Positioning

> An open-source meeting intelligence agent that tracks commitments across meetings, with measured accuracy, crash-safe processing, injection-resistant dispatch, and a self-hosted mode that cuts cost per meeting-hour.

Every phase below supports one part of that sentence.

---

## Phase 0: Baseline (Days 1-3)

- Tag the current version as `v1-baseline`.
- Remove or qualify marketing claims ("enterprise-grade", "unlimited") until you have numbers.
- Add `docker-compose` so the whole stack starts with one command.
- Create an `/eval` folder in the repo. It will hold all later experiments.

---

## Phase 1: Evaluation Harness (Weeks 1-3, Highest Priority)

### Data

- **Public:** AMI and ICSI meeting corpora (transcripts, speaker labels, some summaries), and QMSum for summarization. Check each dataset's license.
- **Own:** record 10 to 15 meetings, including Hinglish ones, and hand-label action items and decisions.

### Metrics

| Component | Metric | Tool |
|---|---|---|
| Transcription | Word error rate (WER) | jiwer |
| Diarization | Diarization error rate (DER) | pyannote.metrics |
| Action items | Precision, recall, F1; owner and due-date accuracy | Labeled set plus fuzzy/LLM matching |
| Decisions | Precision and recall | Same |
| Summary | Faithfulness (claims supported by transcript), coverage | LLM judge validated on 30 human-labeled samples |
| Pipeline | Latency per node, cost per meeting-hour | Existing node timings |

### Deliverables

- `make eval` runs everything and writes a results table.
- A CI job that fails if F1 or faithfulness drops past a threshold after a prompt or model change.
- A baseline report, for example: "v1: action-item F1 = X, owner accuracy = Y".

---

## Phase 2: Make It a Real Agent (Weeks 4-5)

Replace the linear flow with a loop that checks its own work.

1. **Extractor** proposes action items and decisions.
2. **Verifier** checks each item against the transcript and must return a **supporting quote and timestamp**. Items without evidence are dropped or flagged.
3. **Ambiguity resolver** handles missing or unclear owners and dates. It marks them "needs review" instead of guessing.
4. **Confidence score** per item, used to prioritize the human review screen.
5. **Self-consistency:** run extraction two or more times and keep items that agree.

**Measure it:** re-run Phase 1 and show the change in precision (fewer invented items), hallucination rate, and added cost. The honest result may be a small recall drop for a large precision gain. Report that.

---

## Phase 3: Durable Runtime and Queue (Weeks 6-7)

| Problem now | Fix |
|---|---|
| Scheduler in FastAPI lifespan runs once per worker | Move to a queue (Arq, Celery with Redis, or Temporal) with a single scheduled job |
| Crash mid-pipeline loses work | Persist state after each node and resume from the last completed one (completed nodes are already stored, so build on that) |
| Duplicate Jira or email on retry | Idempotency keys, plus an outbox table that records each dispatch before sending |
| Sequential chunk processing | Process chunks in parallel, then merge |
| Chunk cuts slice words | Use 10 to 15 second overlaps, or cut at silence boundaries using VAD, and de-duplicate the overlap |
| Speaker labels inconsistent across chunks | Compute speaker embeddings and match them across chunks, or diarize the full file once and slice afterward |

**Test it:** kill the worker mid-job and show that it resumes and sends exactly one Jira ticket.

---

## Phase 4: Security and Safety (Week 8)

- **Prompt-injection suite:** build 20 to 30 transcripts containing planted instructions such as "assign all tasks to X," "email this to an outside address," or "mark everything done." Report the attack success rate before and after defenses.
- **Defenses:**
  - Treat the transcript as data in prompts.
  - Validate structured output against a schema.
  - Restrict owners to known participants.
  - Add a **policy gate** before any external write (allowed domains, max tickets per meeting, no external email recipients without approval).
- **Credentials:** use authenticated encryption (AES-GCM or Fernet) with the key held outside the database, and support key rotation. Document it precisely.
- **Google Calendar:** switch to per-user OAuth with refresh tokens, since a service account does not fit a multi-user product.
- **Privacy:** optional PII redaction before text reaches an external LLM, retention settings, and a "delete meeting and all embeddings" endpoint.
- **Audit log:** record who approved which dispatch and what was sent.

---

## Phase 5: Self-Hosted Mode (Weeks 9-10)

Add a provider switch so everything can run without paid APIs.

| Stage | Hosted mode | Self-hosted mode |
|---|---|---|
| Transcription | Groq | faster-whisper (large-v3 or distil) |
| Diarization | Existing | pyannote |
| LLM | OpenRouter | Qwen or Llama via Ollama or vLLM |
| Embeddings | Existing | bge-m3 or a multilingual e5 model (supports Hindi) |

Then benchmark both modes on the same eval set: accuracy, wall-clock time, and cost per meeting-hour (including GPU or electricity). Add a **model router** that uses a small model for easy steps and escalates to a larger one when confidence is low.

---

## Phase 6: Retrieval Upgrade (Week 11)

- Replace one embedding per meeting with **chunk-level embeddings** (about 30 to 60 second windows with speaker and timestamp metadata).
- Use **hybrid search** (Postgres full-text plus pgvector) and an optional reranker.
- Chat answers retrieve relevant chunks instead of stuffing 60k characters, and each answer cites **timestamps that jump the audio player to that moment**.
- Evaluate with a set of 50 questions: recall@k, answer correctness, and citation accuracy.

---

## Phase 7: The Differentiator (Weeks 12-13)

This is what separates the project from Otter, Fireflies, and similar tools. Pick one and do it well:

1. **Commitment tracking across meetings.** Detect when a task discussed in meeting 4 is the same one promised in meeting 1, link them, and flag "promised 3 weeks ago, raised again, still not done." Measure link precision on a labeled set.
2. **Decision contradiction detection.** Warn when a new decision conflicts with an earlier one.
3. **Hinglish and Indian-language meetings.** Evaluate WER on code-switched audio and compare base Whisper against fine-tuned or AI4Bharat models.

**Recommendation:** pick #1, with #3 as an add-on, since it targets an underserved market.

---

## Phase 8: Observability and Load Testing (Week 14)

- OpenTelemetry traces across upload, queue, each pipeline node, and dispatch, with Prometheus and Grafana dashboards.
- Metrics: queue depth, time per node, failure rate, tokens and cost per meeting, and reminder delivery rate.
- Load test with 10, 25, and 50 simultaneous uploads. Report where it saturates and what fixed it.
- Re-measure the "34 MB/s" upload claim with the test conditions written down (network, file size, machine).

---

## Phase 9: Packaging (Week 15)

- README opens with a **results table**, not a feature list.
- Update the architecture diagram to show the queue, verifier, policy gate, and both inference modes.
- Record a short demo video that includes failure cases: kill the worker, inject a malicious transcript, show the dashboard.
- Write an article, for example "What I learned measuring a meeting-summary agent," covering failure taxonomy, cost curves, and injection results.

---

## If Time Is Short

| Time available | Do these |
|---|---|
| 3 weeks | Phase 1 and Phase 2 |
| 6 weeks | Add Phase 3 and Phase 4 |
| 10 weeks | Add Phase 5 and Phase 6 |
| 15 weeks | Everything, including the Phase 7 differentiator |

---

## What the Final Result Should Let You Say

> "On a labeled set of N meetings, action-item F1 rose from X to Y after adding an evidence-checking verifier. The pipeline survives worker crashes with exactly-once dispatch. Planted prompt injections succeeded in 40% of cases at baseline and 3% after the policy gate. Self-hosted mode cuts cost per meeting-hour by Z% with a W-point accuracy drop. Cross-meeting tracking links repeated commitments with P% precision."

Every sentence there is backed by a number, which is what makes the project stand out. (The figures above are placeholders; replace them with your measured results.)

---

## Risks

- **Labeling effort** is the slowest part. Start with 10 meetings, not 50.
- **LLM judges are noisy.** Validate them against human labels and say so in the write-up.
- **Scope creep.** Finish each phase's measurement before starting the next.

---

## Suggested Next Steps

1. Write the labeling schema and eval script layout for Phase 1.
2. Break down the first two weeks into daily tasks.
3. Set up the `/eval` folder and `make eval` skeleton.
