from datetime import datetime
from typing import Protocol

from app.schemas.ingest import IngestBatch


class BrokerAdapter(Protocol):
    """Read-only source of broker history. Implementations never send trading requests."""

    name: str

    def fetch_batch(self, range_from: datetime, range_to: datetime) -> IngestBatch: ...
