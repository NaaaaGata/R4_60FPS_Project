"""Bounded, experimental RecompOne static-recompilation integration."""

from .config import RecompOneConfig, ValidatedRecompOneConfig, load_recompone_config
from .funcmap import FuncMapConversion, convert_ghidra_export
from .runner import RecompOneRunner, compile_generated_project
from .tool import PINNED_RECOMPONE_COMMIT, RecompOneTool, discover_recompone

__all__ = [
    "FuncMapConversion",
    "PINNED_RECOMPONE_COMMIT",
    "RecompOneConfig",
    "RecompOneRunner",
    "RecompOneTool",
    "ValidatedRecompOneConfig",
    "compile_generated_project",
    "convert_ghidra_export",
    "discover_recompone",
    "load_recompone_config",
]
