"""Inspectores registrados. Importar este paquete los registra todos."""

from .base import Inspector, inspector_for, register, registered_inspectors  # noqa: F401
from . import arrays, generic, symbolic, tabular  # noqa: F401  (efecto: @register)

__all__ = ["Inspector", "inspector_for", "register", "registered_inspectors"]
