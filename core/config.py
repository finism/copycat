"""Constantes de configuration globale de l'application."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_IS_FROZEN = getattr(sys, "frozen", False)

# Dossier des données utilisateur (backups, token) : à côté de l'exécutable
# une fois compilé, à la racine du projet sinon.
BASE_DIR: Path = Path(sys.executable).resolve().parent if _IS_FROZEN else _PROJECT_ROOT

# Dossier des ressources embarquées (icônes). Compilé en « onefile »,
# PyInstaller les extrait dans un dossier temporaire (sys._MEIPASS), pas à
# côté de l'exécutable.
RESOURCE_DIR: Path = Path(getattr(sys, "_MEIPASS", BASE_DIR)) if _IS_FROZEN else _PROJECT_ROOT

ASSETS_DIR: Path = RESOURCE_DIR / "assets"
BACKUPS_DIR: Path = BASE_DIR / "backups"
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

APP_NAME: str = "Copycat"
APP_VERSION: str = "1.0.0"

# Version du schéma du JSON d'export : permet de le faire évoluer sans
# casser la compatibilité avec les anciens fichiers.
EXPORT_SCHEMA_VERSION: int = 1

# Délai (en secondes) entre deux écritures sur l'API Discord, pour limiter
# les erreurs 429 (rate limit).
IMPORT_THROTTLE_SECONDS: float = 0.4

# Motifs affichés dans le journal d'audit du serveur Discord.
AUDIT_REASON_IMPORT: str = "Import Discord Server Cloner"
AUDIT_REASON_CLEAR: str = "Nettoyage avant import Discord Server Cloner"
