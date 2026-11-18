"""What a profile never keeps the value of: a parameter named like a credential."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

__all__ = ["MASK", "is_sensitive", "masked"]

MASK: Final = "******"

_SENSITIVE_HEADERS: Final = frozenset(
    {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key"}
)
_SENSITIVE_FIELDS: Final = ("password", "secret", "token", "passwd", "api_key", "apikey")


def is_sensitive(name: str) -> bool:
    """Tell whether a parameter with this name likely holds a credential."""
    lowered = name.lower()
    return lowered in _SENSITIVE_HEADERS or any(word in lowered for word in _SENSITIVE_FIELDS)


def masked(parameters: object) -> object:
    """Return ``parameters`` with the value of every credential-named key replaced by the mask.

    A statement is given one mapping of parameters, or a list of them when it
    runs once per row; positional parameters carry no names, so they are kept
    as they are.
    """
    if isinstance(parameters, Mapping):
        return _masked_mapping(cast("Mapping[object, object]", parameters))
    if isinstance(parameters, list | tuple):
        items = [
            _masked_mapping(cast("Mapping[object, object]", item))
            if isinstance(item, Mapping)
            else item
            for item in cast("list[object] | tuple[object, ...]", parameters)
        ]
        return items if isinstance(parameters, list) else tuple(items)
    return parameters


def _masked_mapping(parameters: Mapping[object, object]) -> dict[object, object]:
    return {
        key: MASK if isinstance(key, str) and is_sensitive(key) else value
        for key, value in parameters.items()
    }
