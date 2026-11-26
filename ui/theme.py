"""Système de design : un terminal à phosphore vert, pas un dashboard.

Une seule police (monospace) partout, angles francs, aucun dégradé, aucun
emoji. Un seul accent — le vert — qui sert aussi de couleur de succès,
comme dans un vrai terminal. L'icône (assets/icon.png) reprend cette teinte.
"""

from __future__ import annotations

import customtkinter as ctk

COLORS: dict[str, str] = {
    "bg": "#0A0C0B",  # fond, noir très légèrement teinté de vert
    "surface": "#111513",  # champs de saisie, survols
    "border": "#242C27",  # filets de séparation
    "text": "#D7E0DA",  # texte principal
    "text_dim": "#7C8A82",  # texte secondaire
    "text_faint": "#46524B",  # horodatages, légendes, ponctuation
    "accent": "#4ADE80",  # vert phosphore
    "accent_hover": "#36C46A",
    "success": "#4ADE80",
    "warning": "#E5B94E",
    "error": "#F2665C",
}
C = COLORS

FONT_MONO = "Consolas"
RADIUS = 2


def apply_theme() -> None:
    ctk.set_appearance_mode("dark")


def font(size: int = 12, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_MONO, size=size, weight=weight)


# --- Styles de widgets réutilisables (à passer en **kwargs) ---------------
def entry_style() -> dict:
    return dict(
        fg_color=C["surface"],
        border_color=C["border"],
        border_width=1,
        corner_radius=RADIUS,
        text_color=C["text"],
        placeholder_text_color=C["text_faint"],
        font=font(11),
        height=30,
    )


def menu_style() -> dict:
    return dict(
        fg_color=C["surface"],
        button_color=C["surface"],
        button_hover_color=C["border"],
        text_color=C["text"],
        text_color_disabled=C["text_faint"],
        font=font(11),
        dropdown_fg_color=C["surface"],
        dropdown_hover_color=C["border"],
        dropdown_text_color=C["text"],
        dropdown_font=font(11),
        corner_radius=RADIUS,
        height=30,
        dynamic_resizing=False,
    )


def primary_button_style() -> dict:
    """Bouton plein, réservé à l'action principale (connexion)."""
    return dict(
        fg_color=C["accent"],
        hover_color=C["accent_hover"],
        text_color=C["bg"],
        text_color_disabled=C["bg"],
        border_width=0,
    )


def outline_button_style() -> dict:
    """Bouton discret au contour fin (déconnexion)."""
    return dict(
        fg_color=C["bg"],
        hover_color=C["surface"],
        text_color=C["text_dim"],
        text_color_disabled=C["text_faint"],
        border_width=1,
        border_color=C["border"],
    )


def link_button_style() -> dict:
    """Bouton-texte sans fond, façon lien ou ligne de commande."""
    return dict(
        fg_color="transparent",
        hover_color=C["surface"],
        text_color_disabled=C["text_faint"],
        corner_radius=RADIUS,
        anchor="w",
    )
