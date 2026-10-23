# Meeting Intelligence Agent — Evaluation Report
**Run ID:** `run-20261023-080649` | **Dataset:** `datasets` | **Meetings Evaluated:** 4
**Timestamp:** 2026-10-23T08:06:49.858208+00:00

### Component Summary Metrics

| Metric | Baseline Value | Target Threshold | Status |
|---|---|---|---|
| **Transcription WER** | `0.00%` | `< 12.0%` | [PASS] |
| **Action Item Precision** | `100.00%` | `> 80.0%` | [PASS] |
| **Action Item Recall** | `100.00%` | `> 75.0%` | [PASS] |
| **Action Item F1** | `100.00%` | `> 78.0%` | [PASS] |
| **Owner Attribution Accuracy** | `100.00%` | `> 85.0%` | [PASS] |
| **Due-Date Accuracy** | `100.00%` | `> 80.0%` | [PASS] |
| **Decision F1** | `87.50%` | `> 75.0%` | [PASS] |
| **Summary Faithfulness** | `88.75%` | `> 85.0%` | [PASS] |
| **Average Pipeline Latency** | `6218 ms` | `< 10,000 ms` | [PASS] |
| **Cost per Meeting-Hour** | `$0.0235` | `< $0.05` | [PASS] |

### Per-Meeting Detail

| Meeting ID | Title | WER | Action F1 | Owner Acc | Date Acc | Decision F1 | Faithfulness | Latency |
|---|---|---|---|---|---|---|---|---|
| `arch-review-002` | Core Architecture Review: Durable Queue & Agentic Verifier | 0.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 6565 ms |
| `hinglish-sync-003` | Product & Integrations Sync (Hinglish Code-Switched) | 0.00% | 100.00% | 100.00% | 100.00% | 100.00% | 75.00% | 6165 ms |
| `qmsum-budget-004` | Faculty Research & Lab Equipment Allocation Committee | 0.00% | 100.00% | 100.00% | 100.00% | 50.00% | 100.00% | 6180 ms |
| `sample-standup-001` | Weekly Engineering Standup & Sprint Planning | 0.00% | 100.00% | 100.00% | 100.00% | 100.00% | 80.00% | 5960 ms |