"""Public interface; implementation lives in service.py."""

from .service import SCHEMA, Store, dump

__all__ = ["SCHEMA", "dump", "Store"]
