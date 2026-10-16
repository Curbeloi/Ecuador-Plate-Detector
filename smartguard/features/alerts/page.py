"""Alertas de armas: lista, evidencia y revisión humana (amenaza confirmada / falsa alarma)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smartguard.core.db import (
    CONFIRMED,
    FALSE_ALARM,
    PENDING,
    REVIEW_LABELS,
    WEAPON_LABELS,
    Database,
    WeaponEvent,
)
from smartguard.core.frame_utils import load_pixmap

REVIEW_COLORS = {PENDING: "#d93025", CONFIRMED: "#a50e0e", FALSE_ALARM: "#5f6368"}
FILTERS = (
    ("Sin revisar", PENDING),
    ("Todas", ""),
    ("Amenazas confirmadas", CONFIRMED),
    ("Falsas alarmas", FALSE_ALARM),
)


class AlertsPage(QWidget):
    pendingChanged = Signal(int)
    """Cantidad de alertas sin revisar, para el contador de la barra de navegación."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.events: list[WeaponEvent] = []

        title = QLabel("Alertas de armas")
        title.setProperty("role", "title")
        self.filter = QComboBox()
        for label, value in FILTERS:
            self.filter.addItem(label, value)
        self.filter.currentIndexChanged.connect(self.refresh)
        note = QLabel("La detección automática puede equivocarse: revise la foto antes de actuar.")
        note.setProperty("role", "kpi-caption")

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(("Fecha y hora", "Cámara", "Tipo", "Confianza", "Estado"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._show_selected)

        self.snapshot = QLabel("Seleccione una alerta")
        self.snapshot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.snapshot.setMinimumSize(480, 300)
        self.crop = QLabel()
        self.crop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail = QLabel()
        self.confirm = QPushButton("Amenaza confirmada")
        self.confirm.setStyleSheet("background:#d93025; color:white; font-weight:700; padding:8px;")
        self.confirm.clicked.connect(lambda: self._review(CONFIRMED))
        self.false_alarm = QPushButton("Falsa alarma")
        self.false_alarm.clicked.connect(lambda: self._review(FALSE_ALARM))
        buttons = QHBoxLayout()
        buttons.addWidget(self.confirm)
        buttons.addWidget(self.false_alarm)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(QLabel("Mostrar:"))
        header.addWidget(self.filter)
        left_layout.addLayout(header)
        left_layout.addWidget(note)
        left_layout.addWidget(self.table, 1)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.snapshot, 1)
        right_layout.addWidget(self.crop)
        right_layout.addWidget(self.detail)
        right_layout.addLayout(buttons)
        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        QVBoxLayout(self).addWidget(splitter)
        self.refresh()

    def refresh(self) -> None:
        selected = self._selected()
        self.events = self.db.weapon_events(review=self.filter.currentData())
        self.table.setRowCount(len(self.events))
        for row, event in enumerate(self.events):
            values = (event.ts, event.camera, WEAPON_LABELS[event.kind], f"{event.confidence:.0%}",
                      REVIEW_LABELS[event.review])
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 4:
                    item.setForeground(QColor(REVIEW_COLORS[event.review]))
                self.table.setItem(row, col, item)
        ids = [e.id for e in self.events]
        if selected and selected.id in ids:
            self.table.selectRow(ids.index(selected.id))
        else:
            self._show_selected()
        self.pendingChanged.emit(len(self.db.weapon_events(review=PENDING, limit=None)))

    def show_event(self, event_id: int) -> None:
        """Muestra una alerta concreta (desde el aviso global)."""
        self.filter.setCurrentIndex(0)
        ids = [e.id for e in self.events]
        if event_id in ids:
            self.table.selectRow(ids.index(event_id))

    def _selected(self) -> WeaponEvent | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return self.events[rows[0].row()] if rows else None

    def _show_selected(self) -> None:
        event = self._selected()
        self.confirm.setEnabled(event is not None)
        self.false_alarm.setEnabled(event is not None)
        if event is None:
            self.snapshot.setText("Seleccione una alerta")
            self.crop.clear()
            self.detail.clear()
            return
        self.snapshot.setPixmap(load_pixmap(event.snapshot_path, 900, 520))
        self.crop.setPixmap(load_pixmap(event.crop_path, 240, 160))
        reviewed = f" · revisada {event.reviewed_at}" if event.reviewed_at else ""
        self.detail.setText(f"<b>{WEAPON_LABELS[event.kind]}</b> en <b>{event.camera}</b> · {event.ts} · "
                            f"confianza {event.confidence:.0%} · {REVIEW_LABELS[event.review]}{reviewed}")

    def _review(self, review: str) -> None:
        if event := self._selected():
            self.db.set_weapon_review(event.id, review)
            self.refresh()
