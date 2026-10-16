"""Punto de entrada: ``uv run smartguard`` o ``uv run python -m smartguard``."""

import logging
import sys

from PySide6.QtWidgets import QApplication

from smartguard.core.camera_manager import CameraManager
from smartguard.core.config import Settings
from smartguard.core.db import Database
from smartguard.core.paths import data_dir
from smartguard.ui.main_window import MainWindow
from smartguard.ui.theme import STYLESHEET


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(data_dir() / "smartguard.log", encoding="utf-8")],
    )
    app = QApplication(sys.argv)
    app.setApplicationName("SmartGuard")
    app.setStyleSheet(STYLESHEET)
    settings = Settings.load()
    db_path = data_dir() / "smartguard.db"
    db = Database(db_path)
    manager = CameraManager(settings, db_path)
    window = MainWindow(settings, db, manager)
    window.show()
    manager.start()
    code = app.exec()
    db.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
