"""
eval/validate_dataset.py — Schema and Quality Validator for Meeting Evaluation Datasets.

Validates that all benchmark JSON files in eval/datasets/:
1. Strictly conform to MeetingGroundTruth and MeetingPrediction schemas.
2. Contain valid speaker turn temporal order (start <= end).
3. Have non-empty action item descriptions and decisions.
4. Have valid language tags ('en', 'hi', 'hinglish', etc.).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple
from pydantic import ValidationError

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from eval.schema import MeetingGroundTruth, MeetingPrediction


def validate_meeting_file(file_path: Path) -> Tuple[bool, List[str]]:
    """Validate a single meeting evaluation JSON file."""
    errors: List[str] = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, [f"JSON parsing error: {e}"]

    if "ground_truth" not in data:
        return False, ["Missing top-level 'ground_truth' key"]

    # Validate ground truth
    try:
        gt = MeetingGroundTruth(**data["ground_truth"])
    except ValidationError as ve:
        return False, [f"Ground truth schema validation failed: {ve}"]

    if not gt.meeting_id:
        errors.append("ground_truth.meeting_id cannot be empty")
    if not gt.reference_transcript.strip():
        errors.append("ground_truth.reference_transcript cannot be empty")

    # Validate speaker turns
    prev_end = 0.0
    for idx, turn in enumerate(gt.speaker_turns):
        if turn.end < turn.start:
            errors.append(f"Speaker turn {idx} has invalid timestamps: start ({turn.start}) > end ({turn.end})")
        if not turn.speaker.strip():
            errors.append(f"Speaker turn {idx} has empty speaker name")

    # Validate action items
    for idx, item in enumerate(gt.action_items):
        if not item.description.strip():
            errors.append(f"Action item {idx} has empty description")

    # Validate decisions
    for idx, dec in enumerate(gt.decisions):
        if not dec.decision.strip():
            errors.append(f"Decision {idx} has empty decision text")

    # Validate prediction if present
    if "prediction" in data:
        try:
            pred = MeetingPrediction(**data["prediction"])
            if pred.meeting_id != gt.meeting_id:
                errors.append(f"Prediction meeting_id '{pred.meeting_id}' does not match ground truth '{gt.meeting_id}'")
        except ValidationError as ve:
            errors.append(f"Prediction schema validation failed: {ve}")

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_all_datasets(dataset_dir: str = "eval/datasets") -> int:
    """Validate all JSON dataset files in the target directory."""
    path = Path(dataset_dir)
    if not path.exists():
        print(f"[-] Directory {dataset_dir} does not exist.", file=sys.stderr)
        return 1

    files = sorted(list(path.glob("*.json")))
    if not files:
        print(f"[-] No .json dataset files found in {dataset_dir}.", file=sys.stderr)
        return 1

    print("\n=======================================================")
    print(" Meeting Intelligence Agent -- Dataset Corpus Validator")
    print(f" Scanning {len(files)} files in {dataset_dir}")
    print("=======================================================\n")

    all_passed = True
    for f in files:
        valid, errors = validate_meeting_file(f)
        if valid:
            print(f"  [PASS] {f.name} -- Schema valid and complete")
        else:
            all_passed = False
            print(f"  [FAIL] {f.name}:")
            for err in errors:
                print(f"         * {err}")

    print("\n" + ("=" * 55))
    if all_passed:
        print(f" All {len(files)} dataset files passed validation successfully!")
        print("=" * 55 + "\n")
        return 0
    else:
        print(f" Validation failed on one or more dataset files.", file=sys.stderr)
        print("=" * 55 + "\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate evaluation dataset files")
    parser.add_argument("--dataset-dir", default="eval/datasets", help="Directory containing dataset JSONs")
    args = parser.parse_args()

    sys.exit(validate_all_datasets(args.dataset_dir))
