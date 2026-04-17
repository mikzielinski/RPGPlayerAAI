"""Pluggable behavior system for the RPG AI player.

To add a new behavior:
  1. Create a file in this package with a class subclassing Behavior.
  2. Register it: DEFAULT_CHAIN.register(MyBehavior())

To build a custom chain:
  chain = BehaviorChain().register(A()).register(B())
  run_agent(..., behavior_chain=chain)
"""
from __future__ import annotations

from rpg_player.behaviors.base import Behavior, BehaviorContext
from rpg_player.behaviors.dice_reactions import (
    CriticalHitBehavior,
    CriticalFailBehavior,
    GoodRollBehavior,
)
from rpg_player.behaviors.plot_reactions import PlotTwistBehavior, EmotionalSceneBehavior
from rpg_player.behaviors.uncertainty import RulesUncertaintyBehavior
from rpg_player.behaviors.swearing import SwearingBehavior
from rpg_player.behaviors.group_dynamics import GroupDebateBehavior
from rpg_player.behaviors.silence_filler import SilenceFillerBehavior


class BehaviorChain:
    """Ordered list of behaviors evaluated against each turn's context."""

    def __init__(self) -> None:
        self._behaviors: list[Behavior] = []

    def register(self, behavior: Behavior) -> "BehaviorChain":
        """Add a behavior to the chain. Returns self for fluent chaining."""
        self._behaviors.append(behavior)
        return self

    def run(self, ctx: BehaviorContext) -> tuple[str, list[str]]:
        """Evaluate all behaviors and return (instruction_block, triggered_names).

        instruction_block is injected into the agent's system prompt.
        triggered_names is the list of behavior names that fired (for the dashboard).
        """
        triggered_instructions: list[str] = []
        triggered_names: list[str] = []

        for b in self._behaviors:
            try:
                if b.should_trigger(ctx):
                    triggered_instructions.append(b.get_instruction(ctx))
                    triggered_names.append(b.name)
            except Exception:
                pass

        if not triggered_instructions:
            return "", []

        block = "\n\n=== WSKAZÓWKI BEHAWIORALNE ===\n" + "\n".join(
            f"[{name}] {instr}"
            for name, instr in zip(triggered_names, triggered_instructions)
        )
        return block, triggered_names


# ── Default chain — all built-in behaviors pre-registered ─────────────────────
# Add your own at the bottom:  DEFAULT_CHAIN.register(MyBehavior())
DEFAULT_CHAIN = (
    BehaviorChain()
    .register(CriticalHitBehavior())
    .register(CriticalFailBehavior())
    .register(GoodRollBehavior())
    .register(PlotTwistBehavior())
    .register(EmotionalSceneBehavior())
    .register(RulesUncertaintyBehavior())
    .register(SwearingBehavior())
    .register(GroupDebateBehavior())
    .register(SilenceFillerBehavior())
)
