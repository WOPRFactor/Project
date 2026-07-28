"""Motor de scheduling: Python puro, sin FastAPI ni SQLModel.

Entra y sale por las dataclasses de `types.py`; se testea sin DB y sin servidor.
"""

from .critical import marcar
from .scheduler import calcular
from .types import (
    CycleError,
    DanglingReferenceError,
    DependencyEdge,
    Schedule,
    ScheduledTask,
    ScheduleError,
    SummaryDependencyError,
    TaskNode,
    TipoDependencia,
    TreeError,
)

__all__ = [
    "calcular",
    "marcar",
    "TaskNode",
    "DependencyEdge",
    "Schedule",
    "ScheduledTask",
    "ScheduleError",
    "CycleError",
    "DanglingReferenceError",
    "SummaryDependencyError",
    "TipoDependencia",
    "TreeError",
]
