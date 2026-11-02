"""agent_arena — 把多个大模型拉进同一场辩论，投票淘汰到只剩一个。"""

from .moderator import Arena, ArenaConfig, ArenaResult, run_arena

__all__ = ["Arena", "ArenaConfig", "ArenaResult", "run_arena"]
__version__ = "2.0.0"
