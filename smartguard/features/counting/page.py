"""Conteo de personas, vehículos y animales por cámara, con línea o zona opcional."""

from datetime import date, timedelta

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from smartguard.core.camera_manager import CameraManager
from smartguard.core.config import Settings
from smartguard.core.db import Database
from smartguard.ui.widgets import LiveCameraPanel
from smartguard.vision.counting import CounterConfig, CountTotals

MODES = (("all", "Todo lo que aparece"), ("line", "Lo que cruza una línea"), ("zone", "Lo que entra en una zona"))
HELP = {
    "all": "Cada persona, vehículo o animal se cuenta una vez al aparecer en la cámara.",
    "line": "Pulse «Dibujar» y haga clic en dos puntos (A y B). Entradas: cruzan de izquierda a derecha de la "
            "flecha A→B; salidas: al revés.",
    "zone": "Pulse «Dibujar», haga clic en las esquinas de la zona y termine con clic derecho o «Terminar».",
}


class CountingPage(QWidget):
    def __init__(self, settings: Settings, db: Database, manager: CameraManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.db = db
        self.manager = manager
        self.drawing: list[QPointF] | None = None

        self.live = LiveCameraPanel(settings, manager)
        self.video = self.live.video
        self.video.clicked.connect(self._add_point)
        self.video.rightClicked.connect(self._finish_drawing)

        self.modes = QButtonGroup(self)
        mode_box = QGroupBox("¿Qué contar?")
        mode_layout = QVBoxLayout(mode_box)
        for i, (_, label) in enumerate(MODES):
            button = QRadioButton(label)
            self.modes.addButton(button, i)
            mode_layout.addWidget(button)
        self.modes.idClicked.connect(self._mode_clicked)
        self.help = QLabel()
        self.help.setWordWrap(True)
        mode_layout.addWidget(self.help)
        self.draw_button = QPushButton("Dibujar")
        self.draw_button.clicked.connect(self._start_drawing)
        self.finish_button = QPushButton("Terminar")
        self.finish_button.clicked.connect(self._finish_drawing)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self._cancel_drawing)
        buttons = QHBoxLayout()
        for button in (self.draw_button, self.finish_button, self.cancel_button):
            buttons.addWidget(button)
        mode_layout.addLayout(buttons)

        self.session_box = QGroupBox("Desde que se encendió la cámara")
        self.session = QFormLayout(self.session_box)
        self.today_box = QGroupBox("Hoy (todas las cámaras)")
        self.today = QFormLayout(self.today_box)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(mode_box)
        right_layout.addWidget(self.session_box)
        right_layout.addWidget(self.today_box)
        right_layout.addStretch(1)
        splitter = QSplitter()
        splitter.addWidget(self.live)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        QVBoxLayout(self).addWidget(splitter)

        self.live.cameraChanged.connect(self._camera_changed)
        manager.countsChanged.connect(self._on_counts)
        self.timer = QTimer(self, interval=5000, timeout=self._refresh_today)
        self.timer.start()
        self._camera_changed()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_today()

    def set_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.live.set_settings(settings)

    # --- Estado de la cámara seleccionada -----------------------------------------------------

    def _current_camera(self):
        return self.settings.camera(self.live.camera_id)

    def _camera_changed(self) -> None:
        self._cancel_drawing()
        camera = self._current_camera()
        config = CounterConfig.from_dict(camera.counter if camera else None)
        self.modes.button([m for m, _ in MODES].index(config.kind)).setChecked(True)
        self._update_mode_ui()
        self._show_totals(self.session, None)
        self._refresh_today()
        enabled = bool(camera and camera.count_objects)
        self.session_box.setTitle("Desde que se encendió la cámara" if enabled
                                  else "El conteo está desactivado para esta cámara (ver Configuración)")

    def _mode(self) -> str:
        return MODES[self.modes.checkedId()][0]

    def _update_mode_ui(self) -> None:
        mode = self._mode()
        self.help.setText(HELP[mode])
        drawing = self.drawing is not None
        self.draw_button.setVisible(mode != "all" and not drawing)
        self.finish_button.setVisible(drawing and mode == "zone")
        self.cancel_button.setVisible(drawing)

    # --- Dibujo de línea / zona ---------------------------------------------------------------

    def _mode_clicked(self, _id: int) -> None:
        self._cancel_drawing()
        if self._mode() == "all":
            self._save_counter(CounterConfig())
        self._update_mode_ui()

    def _start_drawing(self) -> None:
        self.drawing = []
        self.video.overlay, self.video.overlay_closed = self.drawing, self._mode() == "zone"
        self._update_mode_ui()

    def _add_point(self, point: QPointF) -> None:
        if self.drawing is None:
            return
        self.drawing.append(point)
        self.video.update()
        if self._mode() == "line" and len(self.drawing) == 2:
            self._finish_drawing()

    def _finish_drawing(self) -> None:
        if self.drawing is None:
            return
        points = tuple((p.x(), p.y()) for p in self.drawing)
        try:
            config = CounterConfig(self._mode(), points)
        except ValueError as error:
            self.help.setText(f"{error}. {HELP[self._mode()]}")
            return
        self._save_counter(config)
        self._cancel_drawing()

    def _cancel_drawing(self) -> None:
        self.drawing = None
        self.video.overlay = []
        self.video.update()
        if self.modes.checkedId() >= 0:
            self._update_mode_ui()

    def _save_counter(self, config: CounterConfig) -> None:
        camera = self._current_camera()
        if camera is None:
            return
        camera.counter = None if config.kind == "all" else config.to_dict()
        self.settings.save()
        self.manager.set_counter(camera.id, config if camera.count_objects else None)

    # --- Señales de las cámaras ---------------------------------------------------------------

    def _on_counts(self, camera_id: str, totals: CountTotals | None) -> None:
        if camera_id == self.live.camera_id:
            self._show_totals(self.session, totals)

    def _refresh_today(self) -> None:
        if not self.isVisible():
            return
        start = date.today()
        counts = self.db.counts_per_label(start.isoformat(), (start + timedelta(days=1)).isoformat())
        totals = CountTotals()
        totals.by_label.update(counts)
        self._show_totals(self.today, totals)

    @staticmethod
    def _show_totals(form: QFormLayout, totals: CountTotals | None) -> None:
        while form.rowCount():
            form.removeRow(0)
        if not totals or not totals.total:
            form.addRow(QLabel("Sin conteos todavía"))
            return
        for label, n in totals.by_label.most_common():
            value = QLabel(str(n))
            value.setProperty("role", "kpi")
            form.addRow(label.capitalize(), value)
        if totals.by_direction.get("out"):
            form.addRow("Entradas / salidas", QLabel(f"{totals.by_direction['in']} / {totals.by_direction['out']}"))
