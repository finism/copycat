"""Pont thread-safe entre le thread asyncio (bot Discord) et le thread Tk (UI).

Tkinter n'est pas thread-safe : seul le thread du mainloop peut toucher aux
widgets. Le bot tourne dans son propre thread ; il dépose donc ses
événements (logs, progression, état de connexion) dans une ``queue.Queue``
que l'UI vide périodiquement via ``after()``.

Le bridge transporte des données brutes : la mise en forme (horodatage,
couleurs, tags) est faite par l'UI.
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Literal, Optional

LogLevel = Literal["info", "success", "warning", "error"]


class EventKind(Enum):
    LOG = auto()  # message + level
    PROGRESS = auto()  # progress (0.0 -> 1.0)
    CONNECTED = auto()  # message = nom du bot, payload = liste des serveurs
    DISCONNECTED = auto()  # message = cause de l'erreur, vide si arrêt normal
    TASK_DONE = auto()  # message = nom de la tâche, payload = exception ou None


@dataclass(frozen=True)
class BridgeEvent:
    kind: EventKind
    message: str = ""
    level: LogLevel = "info"
    progress: Optional[float] = None
    payload: Any = None
    timestamp: float = field(default_factory=time.time)


class LoggerBridge:
    """File d'événements thread-safe consommée par l'interface graphique."""

    def __init__(self) -> None:
        self._queue: "queue.Queue[BridgeEvent]" = queue.Queue()

    # --- Producteurs (appelables depuis n'importe quel thread) -----------
    def log(self, message: str, level: LogLevel = "info") -> None:
        self._queue.put(BridgeEvent(EventKind.LOG, message, level=level))

    def progress(self, value: float) -> None:
        clamped = max(0.0, min(1.0, value))
        self._queue.put(BridgeEvent(EventKind.PROGRESS, progress=clamped))

    def connected(self, bot_name: str, guilds: list) -> None:
        self._queue.put(BridgeEvent(EventKind.CONNECTED, bot_name, payload=guilds))

    def disconnected(self, error: str = "") -> None:
        self._queue.put(BridgeEvent(EventKind.DISCONNECTED, error))

    def task_done(self, task_name: str, error: Optional[BaseException] = None) -> None:
        self._queue.put(BridgeEvent(EventKind.TASK_DONE, task_name, payload=error))

    # --- Consommateur (thread UI uniquement) -----------------------------
    def poll(self) -> list[BridgeEvent]:
        """Retourne tous les événements en attente, sans bloquer."""
        events: list[BridgeEvent] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                return events
