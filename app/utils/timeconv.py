from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models.enums import ServerOffsetMode

NEW_YORK = ZoneInfo("America/New_York")


class ServerOffsetUnknown(ValueError):
    pass


def server_to_utc(
    value: datetime,
    mode: ServerOffsetMode,
    fixed_minutes: int | None = None,
    batch_minutes: int | None = None,
) -> datetime:
    """Convert a broker server timestamp to UTC. Aware values are converted directly."""
    if value.tzinfo is not None:
        return value.astimezone(UTC)
    if mode == ServerOffsetMode.NY_CLOSE:
        return (value - timedelta(hours=7)).replace(tzinfo=NEW_YORK).astimezone(UTC)
    minutes = fixed_minutes if mode == ServerOffsetMode.FIXED else batch_minutes
    if minutes is None and mode == ServerOffsetMode.AUTO:
        minutes = fixed_minutes
    if minutes is None:
        raise ServerOffsetUnknown(
            "Broker server UTC offset is unknown: configure it on the account "
            "(FIXED or NY_CLOSE) or send server_utc_offset_minutes in the batch."
        )
    return (value - timedelta(minutes=minutes)).replace(tzinfo=UTC)
