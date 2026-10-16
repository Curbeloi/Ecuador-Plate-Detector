"""Registro de vehículos de residentes: alta, edición, bloqueo y exportación."""

import csv
import dataclasses

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smartguard.core.db import DECISION_LABELS, Database, Vehicle
from smartguard.features.registry.vehicle_dialog import VehicleDialog
from smartguard.ui.theme import DECISION_COLORS
from smartguard.vision.ecuador import format_plate

COLUMNS = ("Placa", "Estado", "Propietario", "Casa / depto.", "Cédula", "Teléfono", "Vehículo")


class RegistryPage(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.vehicles: list[Vehicle] = []

        title = QLabel("Registro de vehículos")
        title.setProperty("role", "title")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por placa, propietario, cédula o casa…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        add = QPushButton("Nuevo vehículo")
        add.clicked.connect(lambda: self.open_dialog())
        self.edit_button = QPushButton("Editar")
        self.edit_button.clicked.connect(self._edit_selected)
        self.delete_button = QPushButton("Eliminar")
        self.delete_button.clicked.connect(self._delete_selected)
        export = QPushButton("Exportar CSV")
        export.clicked.connect(self._export)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._edit_selected)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.summary = QLabel()

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.search, 1)
        for button in (add, self.edit_button, self.delete_button, export):
            toolbar.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(toolbar)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.summary)
        self.refresh()

    def refresh(self) -> None:
        self.vehicles = self.db.list_vehicles(self.search.text())
        self.table.setRowCount(len(self.vehicles))
        for row, v in enumerate(self.vehicles):
            vehicle = " ".join(x for x in (v.brand, v.model, v.color, v.year) if x)
            values = (format_plate(v.plate), DECISION_LABELS[v.status], v.owner_name, v.unit,
                      v.owner_id_number, v.phone, vehicle)
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 1:
                    item.setForeground(QColor(DECISION_COLORS[v.status]))
                if col == 0:
                    item.setData(Qt.ItemDataRole.FontRole, self._bold())
                self.table.setItem(row, col, item)
        blocked = sum(v.status == "blocked" for v in self.vehicles)
        self.summary.setText(f"{len(self.vehicles)} vehículos · {blocked} bloqueados")
        self._update_buttons()

    def _bold(self):
        font = self.font()
        font.setBold(True)
        return font

    def _selected(self) -> Vehicle | None:
        rows = self.table.selectionModel().selectedRows()
        return self.vehicles[rows[0].row()] if rows else None

    def _update_buttons(self) -> None:
        has_selection = self._selected() is not None
        self.edit_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)

    def open_dialog(self, vehicle: Vehicle | None = None, plate: str = "") -> bool:
        dialog = VehicleDialog(self.db, dataclasses.replace(vehicle) if vehicle else None, plate, self)
        if dialog.exec():
            self.refresh()
            return True
        return False

    def _edit_selected(self) -> None:
        if vehicle := self._selected():
            self.open_dialog(vehicle)

    def _delete_selected(self) -> None:
        vehicle = self._selected()
        if vehicle is None:
            return
        answer = QMessageBox.question(
            self, "Eliminar vehículo", f"¿Eliminar {format_plate(vehicle.plate)} ({vehicle.owner_name}) del registro?"
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.db.delete_vehicle(vehicle.id)
            self.refresh()

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar registro", "vehiculos.csv", "CSV (*.csv)")
        if not path:
            return
        fields = [f.name for f in dataclasses.fields(Vehicle)]
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            for vehicle in self.db.list_vehicles():
                writer.writerow(dataclasses.asdict(vehicle))
