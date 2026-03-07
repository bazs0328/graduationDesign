from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return a naive UTC datetime to preserve the existing storage contract."""
    return datetime.now(UTC).replace(tzinfo=None)
