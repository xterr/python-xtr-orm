"""Each unit of work starts reading from the replicas, whatever the unit around it wrote."""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Final, cast, final, override

from advanced_alchemy.routing import stick_to_primary_var
from xtr_service_contracts import UnitParticipantInterface

if TYPE_CHECKING:
    from contextvars import Token

__all__ = ["DETACHED_VARIABLE", "StickinessParticipant"]

DETACHED_VARIABLE: Final = (stick_to_primary_var, False)
"""What a new connection starts without: an earlier request's reads stuck to the primary.

The orm bundle registers it with the container when a connection has replicas.
"""


@final
class StickinessParticipant(UnitParticipantInterface):
    """Starts every unit of work on the replicas, and leaves the unit around it as it was.

    On a connection with replicas, a write sends every later read of the unit
    to the primary, so it reads what it wrote. That is one unit's state: a
    new unit starts on the replicas again, and when it ends the unit around
    it — a request a message was handled inside — is back where it was, on
    the primary if it had written.

    Told of each unit by the container — it is a unit participant — and
    registered by the orm bundle only when a connection has replicas.
    """

    __slots__ = ()

    @override
    def unit_began(self) -> object | None:
        """Read from the replicas until the new unit writes."""
        return stick_to_primary_var.set(False)

    @override
    def unit_ended(self, token: object | None) -> None:
        """Put back what the unit around this one read from."""
        # The container hands back what unit_began returned for this unit.
        began = cast("Token[bool]", token)
        # Refused when the unit ends in another context than it began in:
        # that one never held this unit's value, so there is nothing to restore.
        with suppress(ValueError):
            stick_to_primary_var.reset(began)
