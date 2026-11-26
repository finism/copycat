"""Structures de données typées représentant un serveur Discord exporté.

Toutes les classes sont des ``dataclasses`` sérialisables en JSON via
``dataclasses.asdict``. Elles servent à la fois pour l'export (écriture)
et pour l'import (lecture + reconstruction).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class OverwriteData:
    """Représente une permission overwrite appliquée à un rôle sur un salon.

    Seuls les overwrites de type "role" sont sauvegardés : les overwrites
    "membre" n'ont pas de sens lors d'un clonage vers un autre serveur
    (les membres ne correspondent pas forcément).
    """

    role_name: str
    allow: int
    deny: int


@dataclass
class RoleData:
    """Représente un rôle du serveur avec ses permissions et sa couleur."""

    name: str
    color: int
    hoist: bool
    mentionable: bool
    permissions: int
    position: int
    is_default: bool = False  # True pour le rôle @everyone


@dataclass
class ChannelData:
    """Représente un salon (texte, vocal, forum ou stage)."""

    name: str
    type: str  # "text" | "voice" | "forum" | "stage"
    position: int
    category_name: Optional[str]
    overwrites: list[OverwriteData] = field(default_factory=list)

    topic: Optional[str] = None
    nsfw: bool = False
    slowmode_delay: int = 0

    # Spécifique aux salons vocaux
    bitrate: Optional[int] = None
    user_limit: Optional[int] = None


@dataclass
class CategoryData:
    """Représente une catégorie et ses overwrites de permissions."""

    name: str
    position: int
    overwrites: list[OverwriteData] = field(default_factory=list)


@dataclass
class EmojiData:
    """Représente un émoji personnalisé, image encodée en base64."""

    name: str
    animated: bool
    image_base64: str


@dataclass
class GuildExportData:
    """Racine du fichier JSON exporté : contient tout le serveur."""

    schema_version: int
    guild_name: str
    exported_at: str
    roles: list[RoleData] = field(default_factory=list)
    categories: list[CategoryData] = field(default_factory=list)
    channels: list[ChannelData] = field(default_factory=list)
    emojis: list[EmojiData] = field(default_factory=list)
    icon_base64: Optional[str] = None
    banner_base64: Optional[str] = None

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "GuildExportData":
        """Reconstruit l'objet à partir d'un dictionnaire JSON chargé."""
        return GuildExportData(
            schema_version=data.get("schema_version", 1),
            guild_name=data["guild_name"],
            exported_at=data.get("exported_at", ""),
            roles=[RoleData(**r) for r in data.get("roles", [])],
            categories=[
                CategoryData(
                    name=c["name"],
                    position=c["position"],
                    overwrites=[OverwriteData(**o) for o in c.get("overwrites", [])],
                )
                for c in data.get("categories", [])
            ],
            channels=[
                ChannelData(
                    name=ch["name"],
                    type=ch["type"],
                    position=ch["position"],
                    category_name=ch.get("category_name"),
                    overwrites=[OverwriteData(**o) for o in ch.get("overwrites", [])],
                    topic=ch.get("topic"),
                    nsfw=ch.get("nsfw", False),
                    slowmode_delay=ch.get("slowmode_delay", 0),
                    bitrate=ch.get("bitrate"),
                    user_limit=ch.get("user_limit"),
                )
                for ch in data.get("channels", [])
            ],
            emojis=[EmojiData(**e) for e in data.get("emojis", [])],
            icon_base64=data.get("icon_base64"),
            banner_base64=data.get("banner_base64"),
        )
