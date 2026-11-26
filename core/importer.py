"""Import/reconstruction d'un serveur Discord à partir d'un export JSON.

Chaque objet (rôle, salon, émoji…) gère ses erreurs individuellement : un
échec ponctuel (rate limit, permission manquante, nom dupliqué) est
journalisé sans interrompre le reste de l'import.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import discord

from core.config import AUDIT_REASON_IMPORT as REASON
from core.config import IMPORT_THROTTLE_SECONDS
from core.logger_bridge import LoggerBridge
from core.models import ChannelData, GuildExportData, OverwriteData

RoleMap = dict[str, discord.Role]
CategoryMap = dict[str, discord.CategoryChannel]
Overwrites = dict[discord.Role, discord.PermissionOverwrite]


def load_export(path: Path) -> GuildExportData:
    """Charge et valide un fichier JSON d'export."""
    with path.open("r", encoding="utf-8") as f:
        return GuildExportData.from_dict(json.load(f))


async def import_guild(
    data: GuildExportData,
    target_guild: discord.Guild,
    bridge: LoggerBridge,
) -> None:
    """Reconstruit ``data`` dans ``target_guild``."""
    bridge.log(f"Début de l'import vers « {target_guild.name} »…")
    bridge.progress(0.0)

    await _apply_identity(data, target_guild, bridge)
    bridge.progress(0.05)

    role_map = await _create_roles(data, target_guild, bridge)
    await _fix_role_order(data, target_guild, role_map, bridge)
    bridge.progress(0.30)

    category_map = await _create_categories(data, target_guild, role_map, bridge)
    bridge.progress(0.45)

    await _create_channels(data, target_guild, role_map, category_map, bridge)  # 0.45 -> 0.85
    await _create_emojis(data, target_guild, bridge)

    bridge.progress(1.0)
    bridge.log("Import terminé.", "success")


# --- Étapes ---------------------------------------------------------------
async def _throttle() -> None:
    await asyncio.sleep(IMPORT_THROTTLE_SECONDS)


def _build_overwrites(saved: list[OverwriteData], role_map: RoleMap) -> Overwrites:
    """Reconstruit les overwrites Discord ; les rôles introuvables sont ignorés."""
    return {
        role_map[ow.role_name]: discord.PermissionOverwrite.from_pair(
            discord.Permissions(ow.allow), discord.Permissions(ow.deny)
        )
        for ow in saved
        if ow.role_name in role_map
    }


async def _apply_identity(data: GuildExportData, guild: discord.Guild, bridge: LoggerBridge) -> None:
    """Applique nom, icône et bannière.

    Trois appels distincts plutôt qu'un seul ``edit()`` : l'échec de l'un
    (ex. bannière refusée faute de boost) ne bloque pas les deux autres.
    """
    try:
        await guild.edit(name=data.guild_name, reason=REASON)
        bridge.log(f"Nom du serveur appliqué : {data.guild_name}", "success")
    except discord.HTTPException as exc:
        bridge.log(f"Échec application du nom : {exc}", "warning")
    await _throttle()

    images = (
        ("icon", "Icône", data.icon_base64, ""),
        ("banner", "Bannière", data.banner_base64, " (boost insuffisant probablement)"),
    )
    for field_name, label, encoded, failure_hint in images:
        if not encoded:
            bridge.log(f"{label} : rien à appliquer (absente du serveur source).")
            continue
        try:
            image = base64.b64decode(encoded)
            await guild.edit(reason=REASON, **{field_name: image})
            bridge.log(f"{label} appliquée ({len(image)} octets).", "success")
        except discord.HTTPException as exc:
            bridge.log(f"{label} : échec de l'application{failure_hint} : {exc}", "warning")
        except Exception as exc:  # noqa: BLE001 - base64 ou image invalide
            bridge.log(f"{label} invalide, ignorée : {exc}", "warning")
        await _throttle()


async def _create_roles(data: GuildExportData, guild: discord.Guild, bridge: LoggerBridge) -> RoleMap:
    """Recrée les rôles, du plus haut au plus bas.

    Discord insère chaque nouveau rôle juste EN DESSOUS du dernier rôle créé
    par le bot : créer en position décroissante reproduit donc directement
    la hiérarchie d'origine.
    """
    bridge.log("Recréation des rôles…")
    role_map: RoleMap = {}
    for role_data in sorted(data.roles, key=lambda r: r.position, reverse=True):
        permissions = discord.Permissions(role_data.permissions)
        try:
            if role_data.is_default:
                # @everyone existe déjà : on ne met à jour que ses permissions.
                await guild.default_role.edit(permissions=permissions, reason=REASON)
                role_map[role_data.name] = guild.default_role
                bridge.log("Permissions de @everyone mises à jour.", "success")
            else:
                role_map[role_data.name] = await guild.create_role(
                    name=role_data.name,
                    colour=discord.Colour(role_data.color),
                    hoist=role_data.hoist,
                    mentionable=role_data.mentionable,
                    permissions=permissions,
                    reason=REASON,
                )
                bridge.log(f"Rôle créé : {role_data.name}", "success")
        except discord.HTTPException as exc:
            bridge.log(f"Échec création du rôle « {role_data.name} » : {exc}", "error")
        await _throttle()
    return role_map


async def _fix_role_order(
    data: GuildExportData, guild: discord.Guild, role_map: RoleMap, bridge: LoggerBridge
) -> None:
    """Filet de sécurité : ne réordonne les rôles que si un décalage est détecté.

    Cas typiques : rôle recréé après un échec réseau, ou rôle déjà présent
    sur le serveur cible. ``edit_role_positions`` attend un ordre ASCENDANT
    (position 1 = le plus bas).
    """
    expected = [
        role_map[r.name]
        for r in sorted(data.roles, key=lambda r: r.position)
        if not r.is_default and r.name in role_map
    ]
    if not expected or sorted(expected, key=lambda role: role.position) == expected:
        return
    bridge.log("Ajustement fin de l'ordre des rôles…")
    try:
        await guild.edit_role_positions(
            positions={role: index + 1 for index, role in enumerate(expected)}
        )
    except discord.HTTPException as exc:
        bridge.log(f"Impossible d'ajuster l'ordre des rôles : {exc}", "warning")


async def _create_categories(
    data: GuildExportData, guild: discord.Guild, role_map: RoleMap, bridge: LoggerBridge
) -> CategoryMap:
    bridge.log("Recréation des catégories…")
    category_map: CategoryMap = {}
    for cat in sorted(data.categories, key=lambda c: c.position):
        try:
            category_map[cat.name] = await guild.create_category(
                name=cat.name,
                overwrites=_build_overwrites(cat.overwrites, role_map),
                reason=REASON,
            )
            bridge.log(f"Catégorie créée : {cat.name}", "success")
        except discord.HTTPException as exc:
            bridge.log(f"Échec création catégorie « {cat.name} » : {exc}", "error")
        await _throttle()
    return category_map


async def _create_channel(
    ch: ChannelData,
    guild: discord.Guild,
    category: discord.CategoryChannel | None,
    overwrites: Overwrites,
    bridge: LoggerBridge,
) -> bool:
    """Crée un salon selon son type. Retourne False si le type est inconnu."""
    common = dict(name=ch.name, category=category, overwrites=overwrites, reason=REASON)

    if ch.type == "text":
        await guild.create_text_channel(
            topic=ch.topic, nsfw=ch.nsfw, slowmode_delay=ch.slowmode_delay, **common
        )
    elif ch.type == "voice":
        await guild.create_voice_channel(
            bitrate=ch.bitrate or 64000, user_limit=ch.user_limit or 0, **common
        )
    elif ch.type == "forum":
        await guild.create_forum(topic=ch.topic, nsfw=ch.nsfw, **common)
    elif ch.type == "stage":
        stage = await guild.create_stage_channel(**common)
        # Le topic d'un stage n'est pas accepté à la création : il passe par edit().
        if ch.topic:
            try:
                await stage.edit(topic=ch.topic)
            except discord.HTTPException as exc:
                bridge.log(f"Topic non appliqué pour « {ch.name} » : {exc}", "warning")
    else:
        return False
    return True


async def _create_channels(
    data: GuildExportData,
    guild: discord.Guild,
    role_map: RoleMap,
    category_map: CategoryMap,
    bridge: LoggerBridge,
) -> None:
    bridge.log("Recréation des salons…")
    channels = sorted(data.channels, key=lambda c: c.position)
    for index, ch in enumerate(channels, start=1):
        category = category_map.get(ch.category_name) if ch.category_name else None
        overwrites = _build_overwrites(ch.overwrites, role_map)
        try:
            if await _create_channel(ch, guild, category, overwrites, bridge):
                bridge.log(f"Salon créé : #{ch.name} ({ch.type})", "success")
            else:
                bridge.log(f"Type de salon inconnu ignoré : {ch.type}", "warning")
        except discord.HTTPException as exc:
            bridge.log(f"Échec création salon « {ch.name} » : {exc}", "error")
        bridge.progress(0.45 + 0.40 * index / len(channels))
        await _throttle()


async def _create_emojis(data: GuildExportData, guild: discord.Guild, bridge: LoggerBridge) -> None:
    if not data.emojis:
        return
    bridge.log("Recréation des émojis personnalisés…")
    for index, emoji in enumerate(data.emojis, start=1):
        try:
            await guild.create_custom_emoji(
                name=emoji.name, image=base64.b64decode(emoji.image_base64), reason=REASON
            )
            bridge.log(f"Émoji créé : {emoji.name}", "success")
        except discord.HTTPException as exc:
            bridge.log(f"Échec création émoji « {emoji.name} » : {exc}", "error")
        except Exception as exc:  # noqa: BLE001 - base64 invalide
            bridge.log(f"Émoji « {emoji.name} » invalide, ignoré : {exc}", "warning")
        bridge.progress(0.85 + 0.15 * index / len(data.emojis))
        await _throttle()
