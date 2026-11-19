"""Public interface; implementation lives in service.py."""

from .provider import GoalPlanner
from .service import GOAL, REVERSE_GOAL, VERSION, propose, requested_amount, reverse_goal, revise

__all__ = [
    "VERSION",
    "GOAL",
    "REVERSE_GOAL",
    "reverse_goal",
    "requested_amount",
    "propose",
    "GoalPlanner",
    "revise",
]
