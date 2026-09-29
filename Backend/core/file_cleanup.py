"""File cleanup utility for uploaded audio and media artifacts.

Prevents disk storage exhaustion on self-hosted instances and ephemeral containers
by deleting orphaned files and stale uploads older than a configured threshold.
"""

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def cleanup_stale_uploads(upload_dir: str, max_age_hours: int = 24) -> int:
    """Scan *upload_dir* and delete any files older than *max_age_hours*.

    Args:
        upload_dir: Directory containing uploaded audio files.
        max_age_hours: Threshold in hours beyond which unlinked files are considered stale.

    Returns:
        Number of stale files removed.
    """
    if not os.path.exists(upload_dir):
        return 0

    now = time.time()
    cutoff_time = now - (max_age_hours * 3600)
    cleaned_count = 0

    try:
        for entry in os.scandir(upload_dir):
            try:
                if entry.is_file() and entry.stat().st_mtime < cutoff_time:
                    os.remove(entry.path)
                    cleaned_count += 1
                    logger.info("Purged stale upload: %s (age > %dh)", entry.name, max_age_hours)
            except OSError as err:
                logger.warning("Could not purge stale file %s: %s", entry.name, err)
    except Exception as exc:
        logger.warning("Error scanning upload directory %s: %s", upload_dir, exc)

    return cleaned_count


def delete_audio_file(file_path: str | Path | None) -> bool:
    """Safely delete an audio file if it exists on disk.

    Args:
        file_path: Absolute or relative file path to the audio file.

    Returns:
        True if the file was deleted, False if it was not found or failed.
    """
    if not file_path:
        return False

    try:
        path = Path(file_path)
        if path.exists() and path.is_file():
            path.unlink()
            logger.info("Deleted processed audio file: %s", file_path)
            return True
    except OSError as exc:
        logger.warning("Failed to delete audio file %s: %s", file_path, exc)

    return False
