"""Public interface; implementation lives in service.py."""

from .service import INJECTION, check, wallet_constraints

__all__ = ["INJECTION", "check", "wallet_constraints"]
