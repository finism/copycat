"""Fenêtre principale : une console, pas un dashboard.

À gauche, une colonne fixe (connexion, serveurs, commandes). À droite, le
terminal : le journal occupe tout l'espace, avec en pied une ligne de prompt
(état courant + curseur clignotant) et une barre de progression ASCII.

Le bot tourne dans un autre thread : l'UI ne lit son état que par les
événements du ``LoggerBridge``, consommés dans ``_poll_bridge``.
"""

from __future__ import annotations

import re
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import Callable, Coroutine

import customtkinter as ctk
import discord
from PIL import Image

from core.bot_client import BotClient
from core.cleaner import clear_guild
from core.config import APP_NAME, APP_VERSION, ASSETS_DIR, BACKUPS_DIR
from core.exporter import export_guild
from core.importer import import_guild, load_export
from core.logger_bridge import BridgeEvent, EventKind, LoggerBridge
from core.token_store import clear_token, load_token, save_token
from ui.theme import (
    C,
    RADIUS,
    entry_style,
    font,
    link_button_style,
    menu_style,
    outline_button_style,
    primary_button_style,
)

POLL_INTERVAL_MS = 120
CURSOR_BLINK_MS = 530
SIDEBAR_WIDTH = 272
PROGRESS_CELLS = 22
NO_GUILD = "—"
MAX_NAME_CHARS = 20

# États de connexion (pilotés par l'UI et les événements du bridge)
OFFLINE, CONNECTING, ONLINE, DISCONNECTING = "offline", "connecting", "online", "disconnecting"

# niveau de log -> (tag affiché, couleur du tag, couleur du message)
LOG_STYLES: dict[str, tuple[str, str, str]] = {
    "info": ("info", C["text_faint"], C["text_dim"]),
    "success": (" ok ", C["success"], C["text"]),
    "warning": ("warn", C["warning"], C["warning"]),
    "error": ("fail", C["error"], C["error"]),
}

BANNER = (
    (r"  /\_/\ ", ""),
    (r" ( o.o )  ", f"{APP_NAME.lower()} v{APP_VERSION}"),
    (r"  > ^ <   ", "clone de serveurs discord · by fetch"),
)

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def _rule(parent: ctk.CTkBaseClass, vertical: bool = False) -> tk.Frame:
    """Filet de séparation d'un pixel (Frame Tk brut : net à toutes les échelles)."""
    size = {"width": 1} if vertical else {"height": 1}
    return tk.Frame(parent, bg=C["border"], bd=0, highlightthickness=0, **size)


def _caption(parent: ctk.CTkBaseClass, text: str) -> ctk.CTkLabel:
    """Titre d'étape. Retourné pour pouvoir surligner l'étape en cours."""
    label = ctk.CTkLabel(
        parent, text=text, font=font(10, "bold"), text_color=C["text_faint"], anchor="w"
    )
    label.pack(fill="x", pady=(18, 6))
    return label


def _short(name: str) -> str:
    """Tronque un nom de serveur pour qu'il tienne dans la colonne."""
    return name if len(name) <= MAX_NAME_CHARS else name[: MAX_NAME_CHARS - 1] + "…"


def _link_button(
    parent: ctk.CTkBaseClass, text: str, command: Callable[[], None], color: str, size: int = 10
) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, command=command, font=font(size), text_color=color,
        height=22 if size <= 10 else 30, width=0, **link_button_style(),
    )


class MainWindow(ctk.CTk):
    """Fenêtre principale de l'application."""

    def __init__(self) -> None:
        super().__init__()

        self.bridge = LoggerBridge()
        self.bot = BotClient(self.bridge)

        self._guilds_by_label: dict[str, discord.Guild] = {}
        self._conn_state = OFFLINE
        self._busy = False  # une tâche (export/import/nettoyage) est en cours
        self._prompt_text = ""
        self._cursor_visible = True
        self._after_ids: dict[str, str] = {}
        self._step_captions: dict[int, ctk.CTkLabel] = {}

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1060x700")
        self.minsize(900, 660)
        self.configure(fg_color=C["bg"])
        self._set_window_icon()

        self._build_layout()
        self._print_banner()
        self._refresh_command_hints()
        self._refresh_controls()
        self._set_progress(0.0)

        self._schedule("poll", POLL_INTERVAL_MS, self._poll_bridge)
        self._schedule("blink", CURSOR_BLINK_MS, self._blink_cursor)

    def _set_window_icon(self) -> None:
        ico_path = ASSETS_DIR / "icon.ico"
        if ico_path.exists():
            try:
                self.iconbitmap(str(ico_path))
            except Exception:  # noqa: BLE001 - .ico non supporté hors Windows
                pass

    def _schedule(self, key: str, delay_ms: int, callback: Callable[[], None]) -> None:
        self._after_ids[key] = self.after(delay_ms, callback)

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, fg_color=C["bg"], width=SIDEBAR_WIDTH, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.pack_propagate(False)
        _rule(self, vertical=True).grid(row=0, column=1, sticky="ns")
        terminal = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        terminal.grid(row=0, column=2, sticky="nsew")

        self._build_sidebar(sidebar)
        self._build_terminal(terminal)

    # -- Colonne de gauche ------------------------------------------------
    def _build_sidebar(self, sidebar: ctk.CTkFrame) -> None:
        content = ctk.CTkFrame(sidebar, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=18, pady=(18, 14))

        self._build_brand(content)
        self._build_connection_section(content)
        self._build_guild_section(content)
        self._build_commands_section(content)
        self._build_status(content)

    def _build_brand(self, parent: ctk.CTkBaseClass) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")

        logo_path = ASSETS_DIR / "icon.png"
        if logo_path.exists():
            logo = Image.open(logo_path).convert("RGBA").resize((96, 96), Image.LANCZOS)
            self._logo = ctk.CTkImage(light_image=logo, dark_image=logo, size=(32, 32))
            ctk.CTkLabel(row, image=self._logo, text="").pack(side="left", padx=(0, 10))

        names = ctk.CTkFrame(row, fg_color="transparent")
        names.pack(side="left")
        ctk.CTkLabel(
            names, text=APP_NAME.lower(), font=font(16, "bold"), text_color=C["text"],
            anchor="w", height=18,
        ).pack(anchor="w")
        ctk.CTkLabel(
            names, text=f"v{APP_VERSION} · by fetch", font=font(10),
            text_color=C["text_faint"], anchor="w", height=14,
        ).pack(anchor="w")

    def _build_connection_section(self, parent: ctk.CTkBaseClass) -> None:
        self._step_captions[1] = _caption(parent, "1. connecter le bot")

        self.token_entry = ctk.CTkEntry(
            parent, placeholder_text="collez ici le token du bot", show="•", **entry_style()
        )
        self.token_entry.pack(fill="x")
        self.token_entry.bind("<Return>", lambda _event: self.on_connect_clicked())

        options = ctk.CTkFrame(parent, fg_color="transparent")
        options.pack(fill="x", pady=(6, 8))
        self.remember_token_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            options,
            text="se souvenir",
            variable=self.remember_token_var,
            font=font(10),
            text_color=C["text_dim"],
            fg_color=C["accent"],
            hover_color=C["accent_hover"],
            checkmark_color=C["bg"],
            border_color=C["text_faint"],
            border_width=1,
            checkbox_width=13,
            checkbox_height=13,
            corner_radius=RADIUS,
        ).pack(side="left")
        self.reveal_btn = _link_button(options, "afficher", self._toggle_token_visibility, C["text_dim"])
        self.reveal_btn.pack(side="right")

        self.connect_btn = ctk.CTkButton(
            parent, text="connecter", font=font(12, "bold"), corner_radius=RADIUS,
            height=30, command=self.on_connect_clicked, **primary_button_style(),
        )
        self.connect_btn.pack(fill="x")

        saved_token = load_token()
        if saved_token:
            self.token_entry.insert(0, saved_token)
            self.remember_token_var.set(True)

    def _build_guild_section(self, parent: ctk.CTkBaseClass) -> None:
        self._step_captions[2] = _caption(parent, "2. choisir les serveurs")
        self.source_menu = self._build_guild_menu(parent, "source", "copier depuis")
        self.target_menu = self._build_guild_menu(parent, "cible", "coller dans")
        self.refresh_btn = _link_button(
            parent, "»  actualiser la liste", self.on_refresh_guilds_clicked, C["text_dim"]
        )
        self.refresh_btn.pack(anchor="w")

    def _build_guild_menu(self, parent: ctk.CTkBaseClass, role: str, hint: str) -> ctk.CTkOptionMenu:
        legend = ctk.CTkFrame(parent, fg_color="transparent")
        legend.pack(fill="x")
        ctk.CTkLabel(
            legend, text=role, font=font(10), text_color=C["text_dim"], height=14
        ).pack(side="left")
        ctk.CTkLabel(
            legend, text=hint, font=font(10), text_color=C["text_faint"], height=14
        ).pack(side="right")

        menu = ctk.CTkOptionMenu(
            parent, values=[NO_GUILD], command=lambda _choice: self._refresh_command_hints(),
            **menu_style(),
        )
        menu.pack(fill="x", pady=(2, 6))
        return menu

    def _build_commands_section(self, parent: ctk.CTkBaseClass) -> None:
        self._step_captions[3] = _caption(parent, "3. lancer une commande")
        commands = (
            ("export", "exporter la source", self.on_export_clicked, C["text"]),
            ("import", "importer vers la cible", self.on_import_clicked, C["text"]),
            ("clear", "vider la cible", self.on_clear_clicked, C["error"]),
        )
        for name, label, handler, color in commands:
            button = ctk.CTkButton(
                parent, text=f"›  {label}", command=handler, font=font(12), text_color=color,
                text_color_disabled=C["text_faint"], fg_color=C["surface"], hover_color=C["border"],
                border_width=1, border_color=C["border"], corner_radius=RADIUS, height=30, anchor="w",
            )
            button.pack(fill="x")
            # Sous chaque commande : ce qu'elle va faire, avec les vrais noms de serveurs.
            hint = ctk.CTkLabel(
                parent, font=font(10), text_color=C["text_faint"], anchor="w", height=14
            )
            hint.pack(fill="x", padx=(2, 0), pady=(2, 8))
            setattr(self, f"{name}_btn", button)
            setattr(self, f"{name}_hint", hint)

    def _build_status(self, parent: ctk.CTkBaseClass) -> None:
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(side="bottom", fill="x")
        _rule(box).pack(fill="x", pady=(0, 10))

        self.status_label = ctk.CTkLabel(box, font=font(10), anchor="w", height=14)
        self.status_label.pack(fill="x")
        self.status_detail = ctk.CTkLabel(
            box, font=font(10), text_color=C["text_faint"], anchor="w", height=14
        )
        self.status_detail.pack(fill="x")

    # -- Zone principale : terminal ---------------------------------------
    def _build_terminal(self, panel: ctk.CTkFrame) -> None:
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(12, 8))
        ctk.CTkLabel(
            header, text="~/copycat/journal", font=font(10), text_color=C["text_faint"]
        ).pack(side="left")
        _link_button(header, "effacer", self._clear_log, C["text_dim"]).pack(side="right")
        _link_button(header, "copier", self._copy_log, C["text_dim"]).pack(side="right", padx=4)

        _rule(panel).grid(row=1, column=0, sticky="ew")

        self.log_box = ctk.CTkTextbox(
            panel,
            fg_color=C["bg"],
            text_color=C["text_dim"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["text_faint"],
            corner_radius=0,
            border_width=0,
            font=font(12),
            wrap="word",
            spacing3=3,
            state="disabled",
        )
        self.log_box.grid(row=2, column=0, sticky="nsew", padx=(14, 4), pady=8)
        self._configure_log_tags()

        _rule(panel).grid(row=3, column=0, sticky="ew")

        footer = ctk.CTkFrame(panel, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=20, pady=10)
        ctk.CTkLabel(footer, text="›", font=font(13, "bold"), text_color=C["accent"]).pack(
            side="left", padx=(0, 8)
        )
        self.prompt_label = ctk.CTkLabel(footer, font=font(12), text_color=C["text"], anchor="w")
        self.prompt_label.pack(side="left")
        self.progress_label = ctk.CTkLabel(footer, font=font(11), anchor="e")
        self.progress_label.pack(side="right")

    def _configure_log_tags(self) -> None:
        self.log_box.tag_config("timestamp", foreground=C["text_faint"])
        self.log_box.tag_config("banner_art", foreground=C["accent"])
        self.log_box.tag_config("banner_text", foreground=C["text_dim"])
        for level, (_tag, tag_color, message_color) in LOG_STYLES.items():
            self.log_box.tag_config(f"tag_{level}", foreground=tag_color)
            self.log_box.tag_config(f"msg_{level}", foreground=message_color)

    # ------------------------------------------------------------------
    # Journal, prompt, progression
    # ------------------------------------------------------------------
    def _write_log(self, *segments: tuple[str, str]) -> None:
        """Ajoute au journal une suite de segments ``(texte, tag de couleur)``."""
        self.log_box.configure(state="normal")
        for text, tag in segments:
            self.log_box.insert("end", text, tag)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _log(self, message: str, level: str = "info", timestamp: float | None = None) -> None:
        tag, _, _ = LOG_STYLES.get(level, LOG_STYLES["info"])
        level = level if level in LOG_STYLES else "info"
        clock = time.strftime("%H:%M:%S", time.localtime(timestamp))
        self._write_log(
            (f"{clock} ", "timestamp"),
            (f"[{tag}] ", f"tag_{level}"),
            (f"{message}\n", f"msg_{level}"),
        )

    def _print_banner(self) -> None:
        self._write_log(("\n", "banner_art"))
        for art, text in BANNER:
            self._write_log((art, "banner_art"), (f"{text}\n", "banner_text"))
        self._write_log(("\n", "banner_art"))
        self._log("1. connectez le bot   2. choisissez source et cible   3. lancez une commande")

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _copy_log(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.log_box.get("1.0", "end-1c"))
        self._log("Journal copié dans le presse-papiers.")

    def _set_prompt(self, text: str) -> None:
        self._prompt_text = text
        self._render_prompt()

    def _render_prompt(self) -> None:
        cursor = "█" if self._cursor_visible else " "
        self.prompt_label.configure(text=f"{self._prompt_text} {cursor}")

    def _blink_cursor(self) -> None:
        self._cursor_visible = not self._cursor_visible
        self._render_prompt()
        self._schedule("blink", CURSOR_BLINK_MS, self._blink_cursor)

    def _set_progress(self, value: float) -> None:
        filled = round(value * PROGRESS_CELLS)
        bar = "█" * filled + "·" * (PROGRESS_CELLS - filled)
        self.progress_label.configure(
            text=f"[{bar}] {int(value * 100):>3}%",
            text_color=C["accent"] if self._busy or value >= 1.0 else C["text_faint"],
        )

    # ------------------------------------------------------------------
    # État des contrôles
    # ------------------------------------------------------------------
    def _refresh_controls(self) -> None:
        """Aligne tous les widgets sur l'état courant (connexion + tâche en cours)."""
        state = self._conn_state
        can_act = state == ONLINE and not self._busy
        action_state = "normal" if can_act else "disabled"

        for widget in (
            self.export_btn, self.import_btn, self.clear_btn,
            self.refresh_btn, self.source_menu, self.target_menu,
        ):
            widget.configure(state=action_state)
        self.token_entry.configure(state="normal" if state == OFFLINE else "disabled")

        button_text = {
            OFFLINE: "connecter",
            CONNECTING: "connexion…",
            ONLINE: "déconnecter",
            DISCONNECTING: "déconnexion…",
        }[state]
        button_style = primary_button_style() if state in (OFFLINE, CONNECTING) else outline_button_style()
        self.connect_btn.configure(
            text=button_text,
            state="normal" if state == OFFLINE or can_act else "disabled",
            **button_style,
        )

        status_text, status_color = {
            OFFLINE: ("● hors ligne", C["text_faint"]),
            CONNECTING: ("● connexion…", C["warning"]),
            ONLINE: ("● en ligne", C["success"]),
            DISCONNECTING: ("● déconnexion…", C["warning"]),
        }[state]
        self.status_label.configure(text=status_text, text_color=status_color)

        # L'étape à faire maintenant ressort ; les autres restent discrètes.
        active_steps = {OFFLINE: {1}, ONLINE: set() if self._busy else {2, 3}}.get(state, set())
        for step, caption in self._step_captions.items():
            caption.configure(text_color=C["accent"] if step in active_steps else C["text_faint"])
        if not self._busy and state in (OFFLINE, ONLINE):
            self._set_prompt(self._idle_prompt())
        if state != ONLINE:
            self.status_detail.configure(text="aucun bot connecté")

    def _toggle_token_visibility(self) -> None:
        hidden = self.token_entry.cget("show") != ""
        self.token_entry.configure(show="" if hidden else "•")
        self.reveal_btn.configure(text="masquer" if hidden else "afficher")

    def _idle_prompt(self) -> str:
        """Ce que l'utilisateur doit faire maintenant, affiché quand rien ne tourne."""
        if self._conn_state == ONLINE:
            return "prêt — choisissez source et cible, puis une commande"
        return "étape 1 — collez le token du bot, puis « connecter »"

    def _refresh_command_hints(self) -> None:
        """Décrit chaque commande avec les serveurs réellement sélectionnés."""
        source = self._guilds_by_label.get(self.source_menu.get())
        target = self._guilds_by_label.get(self.target_menu.get())
        source_name = _short(source.name) if source else "la source"
        target_name = _short(target.name) if target else "la cible"
        self.export_hint.configure(text=f"{source_name} → fichier .json")
        self.import_hint.configure(text=f"fichier .json → {target_name}")
        self.clear_hint.configure(text=f"efface tout dans {target_name}")

    def _set_guilds(self, guilds: list[discord.Guild]) -> None:
        """Remplit les deux menus en conservant la sélection quand c'est possible."""
        names = [g.name for g in guilds]
        self._guilds_by_label = {
            # Deux serveurs homonymes sont distingués par la fin de leur ID.
            (g.name if names.count(g.name) == 1 else f"{g.name} #{str(g.id)[-4:]}"): g
            for g in guilds
        }
        labels = list(self._guilds_by_label) or [NO_GUILD]

        # Par défaut la cible diffère de la source, pour éviter d'écraser
        # par mégarde le serveur qu'on vient d'exporter.
        defaults = {self.source_menu: labels[0], self.target_menu: labels[min(1, len(labels) - 1)]}
        for menu, default in defaults.items():
            current = menu.get()
            menu.configure(values=labels)
            menu.set(current if current in self._guilds_by_label else default)
        self._refresh_command_hints()

    def _selected_guild(self, menu: ctk.CTkOptionMenu, role: str) -> discord.Guild | None:
        guild = self._guilds_by_label.get(menu.get())
        if guild is None:
            messagebox.showwarning(APP_NAME, f"Sélectionnez un serveur {role} valide.")
        return guild

    # ------------------------------------------------------------------
    # Actions utilisateur
    # ------------------------------------------------------------------
    def on_connect_clicked(self) -> None:
        if self._conn_state == ONLINE:
            self._conn_state = DISCONNECTING
            self._refresh_controls()
            self._set_prompt("déconnexion…")
            self.bot.stop()
            return
        if self._conn_state != OFFLINE:
            return

        token = self.token_entry.get().strip()
        if not token:
            messagebox.showwarning(APP_NAME, "Veuillez saisir un token de bot Discord.")
            return
        if self.remember_token_var.get():
            save_token(token)
        else:
            clear_token()

        self._conn_state = CONNECTING
        self._refresh_controls()
        self._set_prompt("connexion à discord…")
        self._log("Connexion au bot Discord en cours…")
        self.bot.start(token)

    def on_refresh_guilds_clicked(self) -> None:
        guilds = self.bot.guilds
        self._set_guilds(guilds)
        self.status_detail.configure(text=self._guild_count_text(len(guilds)))
        self._log(f"{len(guilds)} serveur(s) trouvé(s).")

    def on_export_clicked(self) -> None:
        guild = self._selected_guild(self.source_menu, "source")
        if guild is None:
            return

        path_str = filedialog.asksaveasfilename(
            title="Enregistrer l'export sous…",
            initialdir=str(BACKUPS_DIR),
            initialfile=_INVALID_FILENAME_CHARS.sub("_", f"{guild.name}_export.json"),
            defaultextension=".json",
            filetypes=[("Fichier JSON", "*.json")],
        )
        if not path_str:
            return

        self._run_task(
            "export",
            f"export de « {guild.name} »…",
            export_guild(guild, Path(path_str), self.bridge),
        )

    def on_import_clicked(self) -> None:
        target = self._selected_guild(self.target_menu, "cible")
        if target is None:
            return

        path_str = filedialog.askopenfilename(
            title="Choisir un fichier d'export JSON",
            initialdir=str(BACKUPS_DIR),
            filetypes=[("Fichier JSON", "*.json")],
        )
        if not path_str:
            return

        try:
            data = load_export(Path(path_str))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_NAME, f"Fichier d'export invalide :\n{exc}")
            return

        confirmed = messagebox.askyesno(
            APP_NAME,
            f"Ceci va recréer « {data.guild_name} » dans « {target.name} » :\n"
            f"{len(data.roles)} rôles, {len(data.categories)} catégories, "
            f"{len(data.channels)} salons, {len(data.emojis)} émojis.\n\n"
            f"Cette action est irréversible et peut fortement modifier le serveur. "
            f"Continuer ?",
        )
        if not confirmed:
            return

        self._run_task(
            "import",
            f"import vers « {target.name} »…",
            import_guild(data, target, self.bridge),
        )

    def on_clear_clicked(self) -> None:
        target = self._selected_guild(self.target_menu, "cible")
        if target is None:
            return

        confirmed = messagebox.askyesno(
            APP_NAME,
            f"Ceci va supprimer TOUS les rôles, salons, catégories et émojis "
            f"de « {target.name} ».\n\nCette action est IRRÉVERSIBLE. Continuer ?",
            icon="warning",
        )
        if not confirmed:
            return

        typed_name = simpledialog.askstring(
            APP_NAME,
            f"Pour confirmer, tapez exactement le nom du serveur :\n« {target.name} »",
            parent=self,
        )
        if typed_name != target.name:
            messagebox.showinfo(APP_NAME, "Nom incorrect, nettoyage annulé.")
            return

        self._run_task(
            "nettoyage",
            f"nettoyage de « {target.name} »…",
            clear_guild(target, self.bridge),
        )

    def _run_task(self, name: str, prompt: str, coro: Coroutine) -> None:
        """Lance ``coro`` sur le thread du bot ; sa fin revient par ``TASK_DONE``."""
        try:
            future = self.bot.run_coro(coro)
        except RuntimeError as exc:
            self._log(str(exc), "error")
            return

        self._busy = True
        self._refresh_controls()
        self._set_progress(0.0)
        self._set_prompt(prompt)
        future.add_done_callback(
            lambda f: self.bridge.task_done(name, None if f.cancelled() else f.exception())
        )

    # ------------------------------------------------------------------
    # Événements venus du thread du bot
    # ------------------------------------------------------------------
    def _poll_bridge(self) -> None:
        handlers: dict[EventKind, Callable[[BridgeEvent], None]] = {
            EventKind.LOG: lambda e: self._log(e.message, e.level, e.timestamp),
            EventKind.PROGRESS: lambda e: self._set_progress(e.progress or 0.0),
            EventKind.CONNECTED: self._on_connected,
            EventKind.DISCONNECTED: self._on_disconnected,
            EventKind.TASK_DONE: self._on_task_done,
        }
        for event in self.bridge.poll():
            handlers[event.kind](event)
        self._schedule("poll", POLL_INTERVAL_MS, self._poll_bridge)

    @staticmethod
    def _guild_count_text(count: int) -> str:
        return f"{count} serveur{'s' if count > 1 else ''} accessible{'s' if count > 1 else ''}"

    def _on_connected(self, event: BridgeEvent) -> None:
        guilds = list(event.payload or [])
        self._conn_state = ONLINE
        self._set_guilds(guilds)
        self._refresh_controls()
        self.status_label.configure(text=f"● {event.message}")
        self.status_detail.configure(text=self._guild_count_text(len(guilds)))
        self._log(f"Connecté en tant que {event.message}.", "success", event.timestamp)

    def _on_disconnected(self, event: BridgeEvent) -> None:
        if event.message:
            self._log(event.message, "error", event.timestamp)
        else:
            self._log("Bot déconnecté.", timestamp=event.timestamp)
        if self._busy:
            self._log("La tâche en cours a été interrompue par la déconnexion.", "warning")
            self._busy = False

        self._conn_state = OFFLINE
        self._set_guilds([])
        self._refresh_controls()
        self._set_progress(0.0)

    def _on_task_done(self, event: BridgeEvent) -> None:
        if not self._busy:
            return  # tâche déjà soldée par une déconnexion
        self._busy = False
        self._refresh_controls()

        error = event.payload
        if error is None:
            self._set_progress(1.0)
            return
        self._set_progress(0.0)
        self._log(f"Erreur pendant l'opération « {event.message} » : {error}", "error")
        messagebox.showerror(
            APP_NAME, f"Une erreur est survenue pendant l'opération « {event.message} » :\n{error}"
        )

    def on_close(self) -> None:
        for after_id in self._after_ids.values():
            self.after_cancel(after_id)
        try:
            self.bot.stop()
        finally:
            self.destroy()
