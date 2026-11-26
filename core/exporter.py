"""Export complet d'un serveur Discord vers un fichier JSON."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import discord

from core.config import EXPORT_SCHEMA_VERSION
from core.logger_bridge import LoggerBridge
from core.models import (
    CategoryData,
    ChannelData,
    EmojiData,
    GuildExportData,
    OverwriteData,
    RoleData,
)


def _by_position(items: list) -> list:
    return sorted(items, key=lambda item: item.position)


def _role_overwrites(overwrites: dict) -> list[OverwriteData]:
    """Ne conserve que les overwrites appliqués à des rôles (pas à des membres)."""
    result: list[OverwriteData] = []
    for target, overwrite in overwrites.items():
        if isinstance(target, discord.Role):
            allow, deny = overwrite.pair()
            result.append(OverwriteData(target.name, allow.value, deny.value))
    return result


def _channel_data(channel: Any, kind: str, **specifics: Any) -> ChannelData:
    """Construit un ``ChannelData`` : champs communs + ceux propres au type."""
    return ChannelData(
        name=channel.name,
        type=kind,
        position=channel.position,
        category_name=channel.category.name if channel.category else None,
        overwrites=_role_overwrites(channel.overwrites),
        **specifics,
    )


async def _read_image(asset: Optional[discord.Asset], label: str, bridge: LoggerBridge) -> Optional[str]:
    """Télécharge une image du serveur et la retourne en base64 (None si absente)."""
    if asset is None:
        return None
    try:
        return base64.b64encode(await asset.read()).decode("ascii")
    except Exception as exc:  # noqa: BLE001
        bridge.log(f"Impossible d'exporter {label} : {exc}", "warning")
        return None


async def export_guild(
    guild: discord.Guild,
    output_path: Path,
    bridge: LoggerBridge,
    include_emojis: bool = True,
) -> GuildExportData:
    """Exporte ``guild`` vers le fichier JSON ``output_path`` et retourne les données."""
    bridge.log(f"Début de l'export du serveur « {guild.name} »…")
    bridge.progress(0.0)

    export = GuildExportData(
        schema_version=EXPORT_SCHEMA_VERSION,
        guild_name=guild.name,
        exported_at=datetime.now(timezone.utc).isoformat(),
    )

    bridge.log("Export de l'icône et de la bannière…")
    export.icon_base64 = await _read_image(guild.icon, "l'icône", bridge)
    export.banner_base64 = await _read_image(guild.banner, "la bannière", bridge)
    bridge.progress(0.05)

    bridge.log("Export des rôles…")
    export.roles = [
        RoleData(
            name=role.name,
            color=role.color.value,
            hoist=role.hoist,
            mentionable=role.mentionable,
            permissions=role.permissions.value,
            position=role.position,
            is_default=role.is_default(),
        )
        for role in _by_position(guild.roles)
    ]
    bridge.progress(0.15)

    bridge.log("Export des catégories…")
    export.categories = [
        CategoryData(category.name, category.position, _role_overwrites(category.overwrites))
        for category in _by_position(guild.categories)
    ]
    bridge.progress(0.30)

    bridge.log("Export des salons texte…")
    for channel in _by_position(guild.text_channels):
        export.channels.append(
            _channel_data(
                channel,
                "text",
                topic=channel.topic,
                nsfw=channel.nsfw,
                slowmode_delay=channel.slowmode_delay,
            )
        )
    bridge.progress(0.45)

    bridge.log("Export des salons vocaux…")
    for channel in _by_position(guild.voice_channels):
        export.channels.append(
            _channel_data(
                channel,
                "voice",
                nsfw=channel.nsfw,
                bitrate=channel.bitrate,
                user_limit=channel.user_limit,
            )
        )
    bridge.progress(0.55)

    bridge.log("Export des forums…")
    for channel in _by_position(guild.forums):
        export.channels.append(
            _channel_data(
                channel,
                "forum",
                topic=channel.topic,
                nsfw=channel.nsfw,
                slowmode_delay=channel.default_thread_slowmode_delay or 0,
            )
        )
    bridge.progress(0.65)

    bridge.log("Export des salons de conférence (stages)…")
    for channel in _by_position(guild.stage_channels):
        export.channels.append(_channel_data(channel, "stage", topic=channel.topic))
    bridge.progress(0.75)

    if include_emojis:
        bridge.log("Export des émojis personnalisés…")
        for emoji in guild.emojis:
            try:
                image = base64.b64encode(await emoji.read()).decode("ascii")
            except Exception as exc:  # noqa: BLE001
                bridge.log(f"Impossible d'exporter l'émoji {emoji.name} : {exc}", "warning")
                continue
            export.emojis.append(EmojiData(emoji.name, emoji.animated, image))
    bridge.progress(0.90)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(export), f, ensure_ascii=False, indent=2)

    bridge.progress(1.0)
    bridge.log(
        f"Export terminé : {len(export.roles)} rôles, {len(export.categories)} catégories, "
        f"{len(export.channels)} salons, {len(export.emojis)} émojis → {output_path}",
        "success",
    )
    return export
