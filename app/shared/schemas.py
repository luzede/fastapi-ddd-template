"""Response schemas shared across modules."""

from pydantic import BaseModel


class StatusResponse(BaseModel):
    """Acknowledgement for commands that have no meaningful payload."""

    status: bool = True
