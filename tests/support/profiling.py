"""What a data collector is handed, without serving anything."""

from __future__ import annotations

from xtr_http_kernel.data_collector import ProfiledRequest
from xtr_http_message import ServerRequest

__all__ = ["profiled"]


def profiled() -> ProfiledRequest:
    """Return a profiled request over a plain message; the orm's collector reads none of it."""
    return ProfiledRequest(ServerRequest("GET", "http://app.test/"), 200, {}, {})
