"""Point d'entrée de l'application Discord Server Cloner.

Lance l'interface graphique CustomTkinter. Compatible PyInstaller
(voir README.md pour la commande de compilation en .exe Windows).
"""

from __future__ import annotations

from ui.main_window import MainWindow
from ui.theme import apply_theme


def main() -> None:
    apply_theme()
    app = MainWindow()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
