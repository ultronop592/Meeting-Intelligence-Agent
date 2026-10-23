# Meeting Intelligence Agent — Evaluation Report
**Run ID:** `live-run-20261023-114436` | **Dataset:** `datasets` | **Meetings Evaluated:** 4
**Timestamp:** 2026-10-23T11:44:36.802460+00:00

### Component Summary Metrics

| Metric | Baseline Value | Target Threshold | Status |
|---|---|---|---|
| **Transcription WER** | `0.00%` | `< 12.0%` | [PASS] |
| **Diarization DER** | `0.00%` | `< 18.0%` | [PASS] |
| **Action Item Precision** | `100.00%` | `> 80.0%` | [PASS] |
| **Action Item Recall** | `100.00%` | `> 75.0%` | [PASS] |
| **Action Item F1** | `100.00%` | `> 78.0%` | [PASS] |
| **Owner Attribution Accuracy** | `100.00%` | `> 85.0%` | [PASS] |
| **Due-Date Accuracy** | `100.00%` | `> 80.0%` | [PASS] |
| **Decision F1** | `100.00%` | `> 75.0%` | [PASS] |
| **Summary Faithfulness** | `100.00%` | `> 85.0%` | [PASS] |
| **Average Pipeline Latency** | `17011 ms` | `< 10,000 ms` | [WARN] |
| **Cost per Meeting-Hour** | `$0.0459` | `< $0.05` | [PASS] |

### Per-Meeting Detail

| Meeting ID | Title | WER | DER | Action F1 | Owner Acc | Date Acc | Decision F1 | Faithfulness | Latency |
|---|---|---|---|---|---|---|---|---|---|
| `arch-review-002` | Core Architecture Review: Durable Queue & Agentic Verifier | 0.00% | 0.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 7485 ms |
| `hinglish-sync-003` | Product & Integrations Sync (Hinglish Code-Switched) | 0.00% | 0.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 7650 ms |
| `qmsum-budget-004` | Faculty Research & Lab Equipment Allocation Committee | 0.00% | 0.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 26023 ms |
| `sample-standup-001` | Weekly Engineering Standup & Sprint Planning | 0.00% | 0.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 26885 ms |