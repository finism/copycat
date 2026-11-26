"""Encapsulation du bot Discord dans un thread dédié.

discord.py a besoin d'une boucle asyncio, alors que l'UI tourne dans le
mainloop Tk, bloquant. Le bot vit donc dans un thread séparé avec sa propre
boucle ; l'UI lui soumet des coroutines via ``run_coro`` et reçoit ses
nouvelles par le ``LoggerBridge``.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Coroutine, Optional, TypeVar

import discord

from core.logger_bridge import LoggerBridge

T = TypeVar("T")


class BotClient:
    """Un ``discord.Client`` exécuté dans un thread dédié."""

    def __init__(self, bridge: LoggerBridge) -> None:
        self.bridge = bridge
        self.client: Optional[discord.Client] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_running(self) -> bool:
        """Vrai tant que le thread du bot vit (connexion en cours incluse)."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def guilds(self) -> list[discord.Guild]:
        return list(self.client.guilds) if self.client else []

    # --- Cycle de vie ----------------------------------------------------
    def start(self, token: str) -> None:
        """Lance la connexion du bot dans un nouveau thread."""
        if self.is_running:
            self.bridge.log("Le bot est déjà démarré.", "warning")
            return
        self._thread = threading.Thread(
            target=self._run, args=(token,), daemon=True, name="discord-bot-thread"
        )
        self._thread.start()

    def stop(self) -> None:
        """Demande la déconnexion ; le thread se termine ensuite de lui-même."""
        if self.client and self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self.client.close(), self._loop)

    def run_coro(self, coro: Coroutine[object, object, T]) -> "Future[T]":
        """Planifie une coroutine sur la boucle du bot, depuis le thread UI."""
        if not self._loop or self._loop.is_closed():
            coro.close()
            raise RuntimeError("Le bot n'est pas démarré.")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # --- Thread du bot ---------------------------------------------------
    def _run(self, token: str) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        # « members » est un intent privilégié : il doit être activé dans le
        # portail développeur (Server Members Intent).
        intents = discord.Intents.default()
        intents.members = True
        client = discord.Client(intents=intents)
        self.client = client

        @client.event
        async def on_ready() -> None:
            self._connected = True
            self.bridge.connected(str(client.user), list(client.guilds))

        error = ""
        try:
            loop.run_until_complete(client.start(token))
        except discord.LoginFailure:
            error = "Token invalide. Vérifiez le token du bot."
        except discord.PrivilegedIntentsRequired:
            error = (
                "Intent manquant : activez « Server Members Intent » dans le "
                "portail développeur Discord (onglet Bot)."
            )
        except Exception as exc:  # noqa: BLE001 - filet de sécurité UI
            error = f"Erreur de connexion : {exc}"
        finally:
            self._connected = False
            try:
                if not client.is_closed():
                    loop.run_until_complete(client.close())
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:  # noqa: BLE001
                pass
            loop.close()
            self.bridge.disconnected(error)
