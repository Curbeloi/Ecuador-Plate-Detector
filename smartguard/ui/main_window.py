"""Ventana principal: barra de navegación + páginas, y un único administrador de cámaras."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from smartguard.core.camera_manager import CameraManager
from smartguard.core.config import Settings
from smartguard.core.db import WEAPON_LABELS, Database, Vehicle, WeaponEvent
from smartguard.features.access.page import AccessPage
from smartguard.features.alerts.page import AlertsPage
from smartguard.features.cameras.page import CamerasPage
from smartguard.features.counting.page import CountingPage
from smartguard.features.registry.page import RegistryPage
from smartguard.features.settings.page import SettingsPage
from smartguard.features.statistics.page import StatisticsPage
from smartguard.ui.icons import icon


class AlertBanner(QFrame):
    """Franja roja persistente con la última alerta de arma; suena hasta que alguien la atiende."""

    def __init__(self, on_view, parent=None):
        super().__init__(parent)
        self.event_id: int | None = None
        self.setStyleSheet("QFrame { background:#d93025; } QLabel { color:white; font-size:18px; font-weight:800; }")
        self.text = QLabel()
        view = QPushButton("Ver alerta")
        view.clicked.connect(lambda: on_view(self.event_id))
        dismiss = QPushButton("Atendida")
        dismiss.clicked.connect(self.dismiss)
        layout = QHBoxLayout(self)
        layout.addWidget(self.text, 1)
        layout.addWidget(view)
        layout.addWidget(dismiss)
        self.beeper = QTimer(self, interval=2000, timeout=QApplication.beep)
        self.hide()

    def show_alert(self, event: WeaponEvent) -> None:
        self.event_id = event.id
        self.text.setText(f"⚠  {WEAPON_LABELS[event.kind].upper()} detectada en {event.camera} · {event.ts[11:]}")
        self.show()
        QApplication.beep()
        self.beeper.start()

    def dismiss(self) -> None:
        self.beeper.stop()
        self.hide()


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, db: Database, manager: CameraManager):
        super().__init__()
        self.settings = settings
        self.db = db
        self.manager = manager
        self.setWindowTitle("SmartGuard — Seguridad del condominio")
        self.setWindowIcon(icon("app"))
        self.resize(1400, 860)
        self.setMinimumSize(1024, 640)

        self.registry = RegistryPage(db)
        self.alerts = AlertsPage(db)
        self.access = AccessPage(settings, db, manager, self._open_vehicle_dialog)
        self.cameras = CamerasPage(settings, manager)
        self.counting = CountingPage(settings, db, manager)
        self.statistics = StatisticsPage(db)
        self.settings_page = SettingsPage(settings)
        self.settings_page.applied.connect(self.apply_settings)

        self.pages = QStackedWidget()
        toolbar = QToolBar("Navegación")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, toolbar)
        group = QActionGroup(self)
        self.actions: list[QAction] = []
        for icon_name, text, page in (
            ("access", "Acceso", self.access),
            ("alerts", "Alertas", self.alerts),
            ("cameras", "Cámaras", self.cameras),
            ("registry", "Registro", self.registry),
            ("counting", "Conteo", self.counting),
            ("statistics", "Estadísticas", self.statistics),
            ("settings", "Configuración", self.settings_page),
        ):
            index = self.pages.addWidget(page)
            action = QAction(icon(icon_name), text, self, checkable=True)
            action.triggered.connect(lambda _checked, i=index: self.pages.setCurrentIndex(i))
            group.addAction(action)
            toolbar.addAction(action)
            self.actions.append(action)
        self.actions[0].setChecked(True)
        self.alerts_action = self.actions[1]
        self.banner = AlertBanner(self._view_alert)
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.banner)
        central_layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.alerts.pendingChanged.connect(self._update_alert_count)
        self._update_alert_count(len(db.weapon_events(review="pending", limit=None)))
        manager.weaponAlert.connect(self._on_weapon_alert)

        self.status = QLabel()
        self.statusBar().addPermanentWidget(self.status)
        manager.statusChanged.connect(self._update_status)
        self._update_status()

    def _on_weapon_alert(self, _camera_id: str, event: WeaponEvent) -> None:
        self.alerts.refresh()
        self.banner.show_alert(event)
        QApplication.alert(self)
        self.raise_()

    def _view_alert(self, event_id: int | None) -> None:
        self.alerts_action.trigger()
        if event_id is not None:
            self.alerts.show_event(event_id)

    def _update_alert_count(self, pending: int) -> None:
        self.alerts_action.setText(f"Alertas ({pending})" if pending else "Alertas")

    def _open_vehicle_dialog(self, vehicle: Vehicle | None, plate: str) -> bool:
        return self.registry.open_dialog(vehicle, plate)

    def _update_status(self, *_args) -> None:
        live = sum(1 for w in self.manager.workers.values() if w.status.startswith("En vivo"))
        self.status.setText(f"Cámaras en vivo: {live} de {len(self.manager.workers)}")

    def apply_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.manager.restart(settings)
        for page in (self.access, self.cameras, self.counting):
            page.set_settings(settings)
        self._update_status()
        self.statusBar().showMessage("Configuración guardada. Reiniciando cámaras…", 5000)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.statusBar().showMessage("Deteniendo cámaras…")
        self.manager.stop()
        super().closeEvent(event)
