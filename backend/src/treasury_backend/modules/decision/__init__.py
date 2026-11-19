"""Public interface; implementation lives in service.py."""

from .service import HARD, RECOVERABLE, TTL, decide, simulation_issues

__all__ = ["TTL", "HARD", "RECOVERABLE", "simulation_issues", "decide"]
