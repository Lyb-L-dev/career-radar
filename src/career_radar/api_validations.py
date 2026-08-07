"""Local API input validation shared by focused route modules."""

from __future__ import annotations

from .network_policy import PublicTargetPolicy

_PUBLIC_TARGET_POLICY = PublicTargetPolicy()


def safe_public_url(value: str) -> str:
    """Reject invalid/literal-private targets before they enter configuration.

    DNS answers are revalidated immediately before every outbound crawler request,
    where the result cannot become stale while a task waits in the queue.
    """

    return _PUBLIC_TARGET_POLICY.validate(value, resolve=False).url
