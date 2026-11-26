"""Suppression complète du contenu d'un serveur Discord (salons, rôles, émojis).

Sert à préparer un serveur déjà configuré à recevoir un import propre.
Opération irréversible : la confirmation utilisateur est gérée côté UI.
"""

from __future__ import annotations

import asyncio
from typing import Any, Sequence

import discord

from core.config import AUDIT_REASON_CLEAR as REASON
from core.config import IMPORT_THROTTLE_SECONDS
from core.logger_bridge import LoggerBridge


async def _delete_all(
    items: Sequence[Any],
    label: str,
    bridge: LoggerBridge,
    progress_start: float,
    progress_span: float,
) -> None:
    """Supprime ``items`` un par un ; un échec est journalisé sans tout arrêter."""
    bridge.log(f"Suppression : {len(items)} {label}(s)…")
    for index, item in enumerate(items, start=1):
        try:
            await item.delete(reason=REASON)
            bridge.log(f"Supprimé ({label}) : {item.name}", "success")
        except discord.HTTPException as exc:
            bridge.log(f"Échec suppression ({label}) « {item.name} » : {exc}", "warning")
        bridge.progress(progress_start + progress_span * index / len(items))
        await asyncio.sleep(IMPORT_THROTTLE_SECONDS)


async def clear_guild(guild: discord.Guild, bridge: LoggerBridge) -> None:
    """Supprime tous les salons, rôles (hors @everyone) et émojis de ``guild``."""
    bridge.log(f"Nettoyage du serveur « {guild.name} » en cours…")
    bridge.progress(0.0)

    # Les salons d'abord, les catégories ensuite : Discord peut refuser de
    # supprimer une catégorie encore référencée.
    categories = list(guild.categories)
    channels = [c for c in guild.channels if not isinstance(c, discord.CategoryChannel)]
    await _delete_all(channels + categories, "salon", bridge, 0.0, 0.55)

    # @everyone et les rôles « managed » (intégrations, boosters, bots) ne
    # peuvent pas être supprimés : on les ignore plutôt que d'échouer.
    roles = [r for r in guild.roles if not r.is_default() and not r.managed]
    await _delete_all(roles, "rôle", bridge, 0.55, 0.35)

    await _delete_all(list(guild.emojis), "émoji", bridge, 0.90, 0.10)

    bridge.progress(1.0)
    bridge.log("Nettoyage terminé.", "success")
