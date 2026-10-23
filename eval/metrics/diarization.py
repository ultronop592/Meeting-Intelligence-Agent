"""
eval/metrics/diarization.py — Diarization Error Rate (DER) Evaluation Engine.

Computes:
1. Missed Speech (MS): Speech present in reference but absent in hypothesis.
2. False Alarm Speech (FA): Speech absent in reference but present in hypothesis.
3. Speaker Confusion (SC): Speech attributed to the wrong speaker.
4. Total Diarization Error Rate (DER) = (MS + FA + SC) / Total Reference Speech Time.

Supports:
- pyannote.metrics (if installed)
- Pure Python time-slice interval overlap with optimal bipartite speaker mapping
"""

from typing import Dict, List, Optional, Set, Tuple
from eval.schema import ReferenceSpeakerTurn


def _time_slice_intervals(
    ref_turns: List[ReferenceSpeakerTurn],
    hyp_turns: List[ReferenceSpeakerTurn],
    time_step: float = 0.1,  # 100 ms time-slice resolution
) -> Tuple[float, float, float, float, Dict[str, str]]:
    """
    Computes time-sliced overlap matrix and evaluates DER components.

    Returns:
        (total_ref_time, missed_time, false_alarm_time, confusion_time, speaker_map)
    """
    if not ref_turns:
        total_hyp = sum(max(0.0, h.end - h.start) for h in hyp_turns)
        return 0.0, 0.0, total_hyp, 0.0, {}

    max_time = max(
        max((r.end for r in ref_turns), default=0.0),
        max((h.end for h in hyp_turns), default=0.0),
    )

    if max_time <= 0:
        return 0.0, 0.0, 0.0, 0.0, {}

    # 1. Build optimal speaker mapping based on pairwise speech overlap duration
    overlap_matrix: Dict[str, Dict[str, float]] = {}
    ref_speakers: Set[str] = {r.speaker for r in ref_turns}
    hyp_speakers: Set[str] = {h.speaker for h in hyp_turns}

    for r in ref_turns:
        for h in hyp_turns:
            start_overlap = max(r.start, h.start)
            end_overlap = min(r.end, h.end)
            dur = max(0.0, end_overlap - start_overlap)
            if dur > 0:
                overlap_matrix.setdefault(h.speaker, {}).setdefault(r.speaker, 0.0)
                overlap_matrix[h.speaker][r.speaker] += dur

    # Greedy bipartite mapping: map hypothesis speaker to reference speaker with highest overlap
    speaker_map: Dict[str, str] = {}
    assigned_refs: Set[str] = set()

    sorted_pairs: List[Tuple[float, str, str]] = []
    for h_spk, r_dict in overlap_matrix.items():
        for r_spk, dur in r_dict.items():
            sorted_pairs.append((dur, h_spk, r_spk))
    sorted_pairs.sort(reverse=True, key=lambda x: x[0])

    for dur, h_spk, r_spk in sorted_pairs:
        if h_spk not in speaker_map and r_spk not in assigned_refs:
            speaker_map[h_spk] = r_spk
            assigned_refs.add(r_spk)

    # Any unmapped hyp speaker maps to itself
    for h_spk in hyp_speakers:
        if h_spk not in speaker_map:
            speaker_map[h_spk] = h_spk

    # 2. Time-slice integration
    total_ref_time = 0.0
    missed_time = 0.0
    false_alarm_time = 0.0
    confusion_time = 0.0

    t = 0.0
    while t < max_time:
        t_mid = t + time_step / 2.0

        active_refs = {r.speaker for r in ref_turns if r.start <= t_mid < r.end}
        active_hyps = {speaker_map.get(h.speaker, h.speaker) for h in hyp_turns if h.start <= t_mid < h.end}

        num_ref = len(active_refs)
        num_hyp = len(active_hyps)

        if num_ref > 0:
            total_ref_time += time_step * num_ref

        if num_ref == 0 and num_hyp > 0:
            false_alarm_time += time_step * num_hyp
        elif num_ref > 0 and num_hyp == 0:
            missed_time += time_step * num_ref
        elif num_ref > 0 and num_hyp > 0:
            matched = active_refs.intersection(active_hyps)
            num_matched = len(matched)
            if num_hyp > num_ref:
                false_alarm_time += time_step * (num_hyp - num_ref)
            elif num_ref > num_hyp:
                missed_time += time_step * (num_ref - num_hyp)

            # Confusion occurs when speech was detected for both, but speaker identity did not match
            confusion = min(num_ref, num_hyp) - num_matched
            if confusion > 0:
                confusion_time += time_step * confusion

        t += time_step

    return total_ref_time, missed_time, false_alarm_time, confusion_time, speaker_map


def calculate_der(
    reference_turns: List[ReferenceSpeakerTurn],
    hypothesis_turns: List[ReferenceSpeakerTurn],
) -> Dict[str, float]:
    """
    Computes Diarization Error Rate (DER) and individual error components.

    Returns dict with:
      - der: float (0.0 to 1.0+)
      - missed_speech_rate: float
      - false_alarm_rate: float
      - speaker_confusion_rate: float
      - total_reference_seconds: float
    """
    try:
        from pyannote.core import Annotation, Segment
        from pyannote.metrics.diarization import DiarizationErrorRate

        ref_annotation = Annotation()
        for turn in reference_turns:
            if turn.end > turn.start:
                ref_annotation[Segment(turn.start, turn.end)] = turn.speaker

        hyp_annotation = Annotation()
        for turn in hypothesis_turns:
            if turn.end > turn.start:
                hyp_annotation[Segment(turn.start, turn.end)] = turn.speaker

        metric = DiarizationErrorRate()
        der_val = float(metric(ref_annotation, hyp_annotation))
        components = metric.details(ref_annotation, hyp_annotation)

        total_time = sum(turn.end - turn.start for turn in reference_turns)
        return {
            "der": round(der_val, 4),
            "missed_speech_rate": round(float(components.get("missed detection", 0.0) / max(total_time, 0.001)), 4),
            "false_alarm_rate": round(float(components.get("false alarm", 0.0) / max(total_time, 0.001)), 4),
            "speaker_confusion_rate": round(float(components.get("confusion", 0.0) / max(total_time, 0.001)), 4),
            "total_reference_seconds": round(total_time, 2),
        }
    except (ImportError, Exception):
        pass

    total_ref, missed, fa, conf, _ = _time_slice_intervals(reference_turns, hypothesis_turns)

    if total_ref <= 0.0:
        return {
            "der": 0.0,
            "missed_speech_rate": 0.0,
            "false_alarm_rate": 0.0,
            "speaker_confusion_rate": 0.0,
            "total_reference_seconds": 0.0,
        }

    total_error = missed + fa + conf
    der = round(total_error / total_ref, 4)

    return {
        "der": der,
        "missed_speech_rate": round(missed / total_ref, 4),
        "false_alarm_rate": round(fa / total_ref, 4),
        "speaker_confusion_rate": round(conf / total_ref, 4),
        "total_reference_seconds": round(total_ref, 2),
    }
