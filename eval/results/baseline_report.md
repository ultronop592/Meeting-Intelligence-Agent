# Meeting Intelligence Agent — Evaluation Report
**Run ID:** `run-20261023-075010` | **Dataset:** `datasets` | **Meetings Evaluated:** 1
**Timestamp:** 2026-10-23T07:50:10.202971+00:00

### Component Summary Metrics

| Metric | Baseline Value | Target Threshold | Status |
|---|---|---|---|
| **Transcription WER** | `0.00%` | `< 12.0%` | [PASS] |
| **Action Item Precision** | `100.00%` | `> 80.0%` | [PASS] |
| **Action Item Recall** | `100.00%` | `> 75.0%` | [PASS] |
| **Action Item F1** | `100.00%` | `> 78.0%` | [PASS] |
| **Owner Attribution Accuracy** | `100.00%` | `> 85.0%` | [PASS] |
| **Due-Date Accuracy** | `100.00%` | `> 80.0%` | [PASS] |
| **Decision F1** | `100.00%` | `> 75.0%` | [PASS] |
| **Summary Faithfulness** | `80.00%` | `> 85.0%` | [WARN] |
| **Average Pipeline Latency** | `5960 ms` | `< 10,000 ms` | [PASS] |
| **Cost per Meeting-Hour** | `$0.0228` | `< $0.05` | [PASS] |

### Per-Meeting Detail

| Meeting ID | Title | WER | Action F1 | Owner Acc | Date Acc | Decision F1 | Faithfulness | Latency |
|---|---|---|---|---|---|---|---|---|
| `sample-standup-001` | Weekly Engineering Standup & Sprint Planning | 0.00% | 100.00% | 100.00% | 100.00% | 100.00% | 80.00% | 5960 ms |