"""Registered inspectors. Importing this package registers all of them."""

from .base import Inspector, inspector_for, register, registered_inspectors  # noqa: F401
from . import arrays, generic, symbolic, tabular  # noqa: F401  (side effect: @register)

__all__ = ["Inspector", "inspector_for", "register", "registered_inspectors"]
