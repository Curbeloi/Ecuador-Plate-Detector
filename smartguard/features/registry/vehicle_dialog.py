"""Formulario para registrar o editar un vehículo y su propietario."""

import sqlite3

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from smartguard.core.db import AUTHORIZED, BLOCKED, DECISION_LABELS, Database, Vehicle
from smartguard.vision.ecuador import canonical, format_plate, is_valid_cedula, parse_plate


class VehicleDialog(QDialog):
    def __init__(self, db: Database, vehicle: Vehicle | None = None, plate: str = "", parent=None):
        super().__init__(parent)
        self.db = db
        self.vehicle = vehicle or Vehicle(plate=plate)
        self.setWindowTitle("Editar vehículo" if self.vehicle.id else "Registrar vehículo")
        self.setMinimumWidth(420)

        self.plate = QLineEdit(format_plate(self.vehicle.plate) if self.vehicle.plate else "")
        self.plate.setPlaceholderText("PBZ-5579")
        self.plate_hint = QLabel()
        self.plate.textChanged.connect(self._update_plate_hint)
        self.status = QComboBox()
        for status in (AUTHORIZED, BLOCKED):
            self.status.addItem(DECISION_LABELS[status], status)
        self.status.setCurrentIndex(self.status.findData(self.vehicle.status))
        self.owner_name = QLineEdit(self.vehicle.owner_name)
        self.owner_id_number = QLineEdit(self.vehicle.owner_id_number)
        self.owner_id_number.setPlaceholderText("Cédula de 10 dígitos")
        self.unit = QLineEdit(self.vehicle.unit)
        self.unit.setPlaceholderText("Casa 12, Torre B 304…")
        self.phone = QLineEdit(self.vehicle.phone)
        self.brand = QLineEdit(self.vehicle.brand)
        self.model = QLineEdit(self.vehicle.model)
        self.color = QLineEdit(self.vehicle.color)
        self.year = QLineEdit(self.vehicle.year)
        self.notes = QPlainTextEdit(self.vehicle.notes)
        self.notes.setFixedHeight(70)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow("Placa *", self.plate)
        form.addRow("", self.plate_hint)
        form.addRow("Estado", self.status)
        form.addRow("Propietario", self.owner_name)
        form.addRow("Cédula", self.owner_id_number)
        form.addRow("Casa / depto.", self.unit)
        form.addRow("Teléfono", self.phone)
        form.addRow("Marca", self.brand)
        form.addRow("Modelo", self.model)
        form.addRow("Color", self.color)
        form.addRow("Año", self.year)
        form.addRow("Notas", self.notes)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._update_plate_hint()

    def _update_plate_hint(self) -> None:
        plate = parse_plate(self.plate.text(), max_corrections=0)
        if plate:
            self.plate_hint.setText(f"{plate.province} · {plate.service}")
        elif self.plate.text().strip():
            self.plate_hint.setText("No tiene formato de placa ecuatoriana (se guardará igual)")
        else:
            self.plate_hint.clear()

    def _save(self) -> None:
        plate = canonical(self.plate.text())
        if not plate:
            QMessageBox.warning(self, "Falta la placa", "Ingrese la placa del vehículo.")
            return
        cedula = self.owner_id_number.text().strip()
        if cedula and not is_valid_cedula(cedula):
            answer = QMessageBox.question(
                self, "Cédula inválida", f"La cédula {cedula} no pasa la validación. ¿Guardar de todos modos?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        v = self.vehicle
        v.plate = plate
        v.status = self.status.currentData()
        v.owner_name = self.owner_name.text().strip()
        v.owner_id_number = cedula
        v.unit = self.unit.text().strip()
        v.phone = self.phone.text().strip()
        v.brand = self.brand.text().strip()
        v.model = self.model.text().strip()
        v.color = self.color.text().strip()
        v.year = self.year.text().strip()
        v.notes = self.notes.toPlainText().strip()
        try:
            self.db.save_vehicle(v)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Placa duplicada", f"La placa {format_plate(plate)} ya está registrada.")
            return
        self.accept()
