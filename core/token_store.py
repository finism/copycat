"""Sauvegarde locale optionnelle du token du bot, pour éviter de le ressaisir.

⚠️ Le token est stocké en clair dans un fichier local (non chiffré). C'est
acceptable pour un usage personnel sur une machine de confiance, mais ce
fichier ne doit jamais être partagé, commité dans un dépôt Git, ou envoyé
à qui que ce soit — il donne un accès complet au bot.
"""

from __future__ import annotations

from pathlib import Path

from core.config import BASE_DIR

TOKEN_FILE: Path = BASE_DIR / ".copycat_token"


def save_token(token: str) -> None:
    """Enregistre le token localement (écrase toute valeur précédente)."""
    TOKEN_FILE.write_text(token.strip(), encoding="utf-8")


def load_token() -> str | None:
    """Retourne le token sauvegardé, ou None si aucun n'est enregistré."""
    if not TOKEN_FILE.exists():
        return None
    content = TOKEN_FILE.read_text(encoding="utf-8").strip()
    return content or None


def clear_token() -> None:
    """Supprime le token sauvegardé, s'il existe."""
    TOKEN_FILE.unlink(missing_ok=True)
