"""Optional swearing behavior — injects permission and intensity into agent prompt."""
from __future__ import annotations

from rpg_player import config
from rpg_player.behaviors.base import Behavior, BehaviorContext

_INSTRUCTIONS = {
    "mild": (
        "Możesz używać łagodnych przekleństw ('cholera', 'kurczę', 'o rany', 'do diabła') "
        "gdy emocje są silne. Raz na jakiś czas — naturalnie, nie w każdym zdaniu."
    ),
    "moderate": (
        "Możesz przeklinać gdy sytuacja tego wymaga ('kurwa', 'cholera', 'do kurwy nędzy', 'do diabła'). "
        "Używaj jak prawdziwy gracz — gdy jest powód, nie na siłę."
    ),
    "heavy": (
        "Możesz przeklinać bez cenzury gdy emocje i sytuacja tego wymagają. "
        "Używaj mocno ale naturalnie — jak gracz który naprawdę gra, nie robot cytujący bluzgi."
    ),
}


class SwearingBehavior(Behavior):
    name = "swearing"

    def should_trigger(self, ctx: BehaviorContext) -> bool:
        return config.SWEARING_INTENSITY not in ("off", "", None)

    def get_instruction(self, ctx: BehaviorContext) -> str:
        return _INSTRUCTIONS.get(config.SWEARING_INTENSITY, "")
