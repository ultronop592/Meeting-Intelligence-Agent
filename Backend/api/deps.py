"""Shared API dependencies and route security helpers."""

from fastapi import HTTPException, status
from db.models import Meeting, User


def verify_meeting_ownership(meeting: Meeting, current_user: User) -> None:
    """Ensure that the requesting user owns the meeting.
    Allows access if meeting.user_id matches current_user.id or is None (legacy pre-auth records).
    """
    if meeting.user_id and meeting.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access or modify this meeting.",
        )
