"""Compose a real Groq planner or the explicit offline rule provider."""

from dataclasses import dataclass

from filelock import Timeout

from treasury_backend.core.errors import ControlError

from .groq import GroqPlanner
from .rotation import RotatingPlanner
from .service import VERSION, requested_amount, reverse_goal


@dataclass(frozen=True)
class GoalPlan:
    amount: int
    reverse: bool


class GoalPlanner:
    def __init__(self, settings, directory, **kwargs):
        self.settings = settings
        self.provider = None
        if settings.provider == "groq":
            self.provider = GroqPlanner(settings, directory, **kwargs)
        elif settings.provider in {"gemini", "xingchi", "rotate"}:
            self.provider = RotatingPlanner(settings, directory, **kwargs)
        self.version = self.provider.version if self.provider else VERSION

    @property
    def metadata(self):
        return {
            "planner_version": self.version,
            "planner_provider": self.settings.provider,
            "planner_model": (
                self.settings.gemini_model if self.settings.provider == "gemini"
                else self.settings.xingchi_model if self.settings.provider == "xingchi"
                else None if self.settings.provider == "rotate"
                else self.settings.model if self.provider else None
            ),
        }

    def parse(self, goal):
        if self.provider:
            try:
                draft = self.provider.plan(goal)
            except Timeout:
                raise ControlError("PLANNER_BUSY", 429, retryable=True) from None
            reverse = draft.direction == "WAVAX_TO_USDC"
            canonical = (
                f"Sell {draft.amount} WAVAX for USDC"
                if reverse
                else f"Buy WAVAX with {draft.amount} USDC"
            )
            return GoalPlan(requested_amount(canonical), reverse)
        return GoalPlan(requested_amount(goal) or 0, reverse_goal(goal))

    def close(self):
        if self.provider:
            self.provider.close()
