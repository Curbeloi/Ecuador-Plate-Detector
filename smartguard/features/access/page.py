"""Control de acceso en la garita: video en vivo, decisión por placa e historial."""

import time
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QGridLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smartguard.core.camera_manager import CameraManager
from smartguard.core.config import Settings
from smartguard.core.db import AUTHORIZED, BLOCKED, DECISION_LABELS, UNKNOWN, Database, PlateEvent, Vehicle
from smartguard.core.frame_utils import load_pixmap
from smartguard.ui.theme import DECISION_COLORS, text_color_for
from smartguard.ui.widgets import LiveCameraPanel
from smartguard.vision.ecuador import canonical, format_plate, parse_plate


class DecisionCard(QFrame):
    """Tarjeta grande con el resultado de la última placa: AUTORIZADO / BLOQUEADO / NO REGISTRADO."""

    def __init__(self, on_register: Callable[[str, Vehicle | None], None], parent=None):
        super().__init__(parent)
        self.on_register = on_register
        self.plate_text = ""
        self.vehicle: Vehicle | None = None
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self.banner = QLabel()
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setMinimumHeight(56)
        self.plate = QLabel()
        self.plate.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plate.setStyleSheet("font-size: 34px; font-weight: 800; letter-spacing: 2px;")
        self.meta = QLabel()
        self.meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.meta.setProperty("role", "kpi-caption")
        self.crop = QLabel()
        self.crop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop.setMinimumHeight(70)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.RichText)
        self.action = QPushButton()
        self.action.clicked.connect(lambda: self.on_register(self.plate_text, self.vehicle))

        layout = QVBoxLayout(self)
        layout.addWidget(self.banner)
        layout.addWidget(self.plate)
        layout.addWidget(self.meta)
        layout.addWidget(self.crop)
        layout.addWidget(self.details)
        layout.addWidget(self.action)
        self.show_idle()

    def _set_banner(self, text: str, color: str) -> None:
        self.banner.setText(text)
        self.banner.setStyleSheet(
            f"background:{color}; color:{text_color_for(color)}; font-size:24px; font-weight:800; border-radius:8px;"
        )

    def show_idle(self) -> None:
        self._set_banner("ESPERANDO VEHÍCULO", "#5f6368")
        self.plate.setText("—")
        self.meta.clear()
        self.crop.clear()
        self.details.clear()
        self.action.hide()

    def show_result(self, plate: str, decision: str, vehicle: Vehicle | None, meta: str, crop_path: str = "") -> None:
        self.plate_text, self.vehicle = plate, vehicle
        self._set_banner(DECISION_LABELS[decision].upper(), DECISION_COLORS[decision])
        self.plate.setText(format_plate(plate))
        parsed = parse_plate(plate, max_corrections=0)
        self.meta.setText(" · ".join(x for x in (parsed.province if parsed else "", meta) if x))
        if crop_path:
            self.crop.setPixmap(load_pixmap(crop_path, 260, 80))
        else:
            self.crop.clear()
        if vehicle:
            car = " ".join(x for x in (vehicle.brand, vehicle.model, vehicle.color) if x) or "—"
            rows = [("Propietario", vehicle.owner_name), ("Casa / depto.", vehicle.unit),
                    ("Cédula", vehicle.owner_id_number), ("Teléfono", vehicle.phone), ("Vehículo", car),
                    ("Notas", vehicle.notes)]
            self.details.setText("<br>".join(f"<b>{k}:</b> {v}" for k, v in rows if v))
            self.action.setText("Editar registro")
        else:
            self.details.setText("Esta placa no está en el registro del condominio.")
            self.action.setText("Registrar vehículo")
        self.action.show()


SEVERITY = {AUTHORIZED: 0, UNKNOWN: 1, BLOCKED: 2}
ALERT_HOLD_S = 8
"""Durante este tiempo una alerta (bloqueado / no registrado) no se reemplaza por un evento menos grave."""


class AccessPage(QWidget):
    def __init__(self, settings: Settings, db: Database, manager: CameraManager,
                 open_vehicle_dialog: Callable[[Vehicle | None, str], bool], parent=None):
        super().__init__(parent)
        self.db = db
        self.manager = manager
        self.open_vehicle_dialog = open_vehicle_dialog
        self.events: list[PlateEvent] = []
        self._shown = (AUTHORIZED, 0.0)
        """(decisión, momento) del evento que muestra la tarjeta."""

        self.live = LiveCameraPanel(settings, manager)

        self.card = DecisionCard(self._register)
        self.lookup = QLineEdit()
        self.lookup.setPlaceholderText("Consultar placa manualmente (ej. PBZ-5579)")
        self.lookup.returnPressed.connect(self._manual_lookup)
        lookup_button = QPushButton("Consultar")
        lookup_button.clicked.connect(self._manual_lookup)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Hora", "Placa", "Decisión", "Cámara"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellClicked.connect(self._show_event_row)

        right = QWidget()
        right_layout = QGridLayout(right)
        right_layout.addWidget(self.card, 0, 0, 1, 2)
        right_layout.addWidget(self.lookup, 1, 0)
        right_layout.addWidget(lookup_button, 1, 1)
        recent = QLabel("Últimos accesos")
        recent.setProperty("role", "title")
        right_layout.addWidget(recent, 2, 0, 1, 2)
        right_layout.addWidget(self.table, 3, 0, 1, 2)
        right_layout.setRowStretch(3, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.live)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        manager.accessEvent.connect(self._on_access)
        self.refresh_events()

    def set_settings(self, settings: Settings) -> None:
        self.live.set_settings(settings)

    def _on_access(self, camera_id: str, access) -> None:
        event: PlateEvent = access.event
        shown_decision, shown_at = self._shown
        recent_alert = time.monotonic() - shown_at < ALERT_HOLD_S
        if not recent_alert or SEVERITY[event.decision] >= SEVERITY[shown_decision]:
            self._shown = (event.decision, time.monotonic())
            self._show_event(event, access.vehicle)
        self.refresh_events()
        if event.decision == BLOCKED:
            QApplication.beep()

    def refresh_events(self) -> None:
        self.events = self.db.plate_events(limit=100)
        self.table.setRowCount(len(self.events))
        for row, event in enumerate(self.events):
            values = (event.ts[11:], format_plate(event.plate), DECISION_LABELS[event.decision], event.camera)
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 2:
                    item.setForeground(QColor(DECISION_COLORS[event.decision]))
                self.table.setItem(row, col, item)

    def _show_event(self, event: PlateEvent, vehicle: Vehicle | None) -> None:
        time = event.ts[11:] if event.ts.startswith(datetime.now().strftime("%Y-%m-%d")) else event.ts
        self.card.show_result(event.plate, event.decision, vehicle, f"{event.camera} · {time}", event.crop_path)

    def _show_event_row(self, row: int, _column: int) -> None:
        event = self.events[row]
        self._show_event(event, self.db.find_vehicle(event.plate))

    def _manual_lookup(self) -> None:
        plate = canonical(self.lookup.text())
        if not plate:
            return
        vehicle = self.db.find_vehicle(plate)
        self.card.show_result(plate, vehicle.status if vehicle else UNKNOWN, vehicle, "Consulta manual")

    def _register(self, plate: str, vehicle: Vehicle | None) -> None:
        if self.open_vehicle_dialog(vehicle, plate):
            updated = self.db.find_vehicle(plate)
            self.card.show_result(plate, updated.status if updated else UNKNOWN, updated, "Registro actualizado")
