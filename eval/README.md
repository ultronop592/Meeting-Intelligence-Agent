# Meeting Intelligence Agent — Evaluation Harness (`/eval`)

This directory houses the quantitative evaluation framework for the Meeting Intelligence Agent platform, fulfilling **Phase 0** and establishing the baseline infrastructure for **Phase 1** of the [Improvement Plan](../meeting-intelligence-agent-improvement-plan.md).

---

## 1. Directory Structure

```text
eval/
├── README.md                          # Documentation and evaluation methodology
├── schema.py                          # Pydantic models for ground truth, predictions, and metrics
├── run_eval.py                        # Benchmark runner CLI script
├── metrics/
│   ├── __init__.py
│   ├── transcription.py               # WER and CER calculation (jiwer / DP Levenshtein)
│   ├── action_items.py                # Action item Precision, Recall, F1, Owner & Due-date accuracy
│   ├── decisions.py                   # Decision Precision, Recall, and F1
│   └── summary.py                     # Summary lexical coverage and factual faithfulness
├── datasets/
│   └── sample_baseline_meeting.json   # Seed baseline benchmark meeting
└── results/
    ├── baseline_report.json           # Machine-readable evaluation report
    └── baseline_report.md             # Rendered markdown benchmark summary
```

---

## 2. Target Metrics & Benchmarks

| Component | Metric | Target Threshold | Description |
|---|---|---|---|
| **Transcription** | Word Error Rate (WER) | `< 12.0%` | Measures transcription word edit distance against ground truth. |
| **Diarization** | Diarization Error Rate (DER) | `< 18.0%` | Measures speaker confusion, false alarm, and missed speaker time (Pyannote). |
| **Action Items** | Precision / Recall / F1 | `> 78.0%` | Evaluates extraction of concrete actionable commitments. |
| **Action Items** | Owner Attribution Accuracy | `> 85.0%` | Validates whether the correct assignee was linked to the action item. |
| **Action Items** | Due-Date Accuracy | `> 80.0%` | Validates whether the correct deadline was captured. |
| **Decisions** | Precision / Recall / F1 | `> 75.0%` | Evaluates extraction of formal decisions and contextual rationale. |
| **Summary** | Faithfulness & Coverage | `> 85.0%` | Validates that claims in the summary are factually supported by transcript text. |
| **Runtime** | Node Latency & Cost | `< 10s / < $0.05` | Evaluates latency per node and cost per meeting-hour. |

---

## 3. Dataset Formats

Every test case in `eval/datasets/` is a JSON file conforming to `eval/schema.py`:

```json
{
  "ground_truth": {
    "meeting_id": "unique-id",
    "title": "Meeting Title",
    "language": "en",
    "reference_transcript": "Verbatim transcript text...",
    "speaker_turns": [
      { "speaker": "Alice", "start": 0.0, "end": 5.0, "text": "..." }
    ],
    "action_items": [
      {
        "description": "Commitment description",
        "owner": "Alice",
        "due_date": "2026-10-25",
        "priority": "high"
      }
    ],
    "decisions": [
      {
        "decision": "Agreed decision",
        "rationale": "Contextual reason"
      }
    ],
    "reference_summary": "Ground truth executive summary..."
  },
  "prediction": {
    "meeting_id": "unique-id",
    "hypothesis_transcript": "Transcribed text...",
    "action_items": [ ... ],
    "decisions": [ ... ],
    "generated_summary": "...",
    "node_latencies_ms": {
      "transcribe_audio": 3120,
      "extract_information": 1450,
      "generate_summary": 1210
    },
    "cost_usd": 0.0038
  }
}
```

---

## 4. Running Benchmarks

### Using Python directly:
```bash
python -m eval.run_eval
```

### With custom thresholds for CI:
```bash
python -m eval.run_eval --dataset-dir eval/datasets --min-f1 0.75 --min-faithfulness 0.70
```

### Using Make:
```bash
make eval
```

---

## 5. Phase 1 Data Roadmap

1. **Public Corpora**:
   - **AMI Meeting Corpus**: 100 hours of multimodal meeting recordings with reference transcripts and dialogue acts.
   - **ICSI Meeting Corpus**: 75 hours of academic meetings with speaker segmentations.
   - **QMSum**: Query-based multi-domain meeting summarization benchmark.
2. **Custom / Hinglish Corpus**:
   - 10–15 recorded real-world meetings including Hindi-English code-switched dialogues to benchmark low-resource speaker attribution.
