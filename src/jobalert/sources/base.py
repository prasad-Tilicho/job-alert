"""The contract every job source implements."""
from __future__ import annotations

from typing import List

import httpx

from jobalert.models import Job

try:  # pragma: no cover - Protocol is only used for type checking
    from typing import Protocol
except ImportError:  # pragma: no cover
    Protocol = object  # type: ignore[assignment]

DEFAULT_USER_AGENT = "jobalert/0.1 (+https://github.com/)"


class JobSource(Protocol):
    """A feed of job postings.

    Implementations are constructed with their own configuration and are handed a
    shared ``httpx.Client`` at fetch time so connection pooling and timeouts are
    configured in exactly one place.
    """

    name: str

    def fetch(self, client: httpx.Client) -> List[Job]:
        """Return postings from this source. Raises on transport or HTTP errors."""
        ...
