"""Configuración: cámaras del condominio, modelos, umbrales y carpeta de capturas."""

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from smartguard.core.config import DEVICES, OCR_MODELS, PLATE_DETECTOR_MODELS, TRACKING_MODELS, Camera, Settings
from smartguard.core.paths import DEMO_VIDEO, data_dir
from smartguard.core.video_source import probe_source
from smartguard.vision.weapons import WEAPON_MODELS

SOURCE_KINDS = ("Cámara IP (RTSP/HTTP)", "Cámara local (USB / integrada)", "Archivo de video")
RTSP_HELP = (
    "Ejemplos: Hikvision <code>rtsp://usuario:clave@192.168.1.64:554/Streaming/Channels/101</code> · "
    "Dahua <code>rtsp://usuario:clave@192.168.1.108:554/cam/realmonitor?channel=1&amp;subtype=0</code>"
)


class ProbeThread(QThread):
    finished_with = Signal(bool, str)

    def __init__(self, source: str, parent=None):
        super().__init__(parent)
        self.source = source

    def run(self) -> None:
        self.finished_with.emit(*probe_source(self.source))


def _source_kind(source: str) -> int:
    if source.strip().isdigit():
        return 1
    return 0 if "://" in source else 2


class CameraEditor(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.camera: Camera | None = None
        self.name = QLineEdit()
        self.kind = QComboBox()
        self.kind.addItems(SOURCE_KINDS)
        self.url = QLineEdit()
        self.url.setPlaceholderText("rtsp://usuario:clave@IP:554/...")
        self.index = QSpinBox()
        self.index.setRange(0, 9)
        self.file = QLineEdit()
        browse = QPushButton("Elegir…")
        browse.clicked.connect(self._browse)
        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.addWidget(self.file, 1)
        file_layout.addWidget(browse)
        url_row = QWidget()
        url_layout = QVBoxLayout(url_row)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.addWidget(self.url)
        help_label = QLabel(RTSP_HELP)
        help_label.setWordWrap(True)
        help_label.setProperty("role", "kpi-caption")
        url_layout.addWidget(help_label)
        self.source_stack = QStackedWidget()
        for widget in (url_row, self.index, file_row):
            self.source_stack.addWidget(widget)
        self.kind.currentIndexChanged.connect(self.source_stack.setCurrentIndex)

        self.enabled = QCheckBox("Cámara activa")
        self.read_plates = QCheckBox("Leer placas (control de acceso)")
        self.count_objects = QCheckBox("Contar personas, vehículos y animales")
        self.save_photos = QCheckBox("Guardar una foto de cada vehículo")
        self.detect_weapons = QCheckBox("Detectar armas de fuego y armas blancas")
        self.loop_video = QCheckBox("Repetir el video al terminar (solo archivos)")
        self.max_fps = QSpinBox()
        self.max_fps.setRange(1, 30)
        self.max_fps.setSuffix(" cuadros/s")
        self.max_fps.setToolTip("5 bastan para contar y detectar armas; la cámara de placas necesita unos 10. "
                                "Menos cuadros por cámara permiten atender más cámaras con el mismo equipo.")
        self.count_objects.toggled.connect(self.save_photos.setEnabled)
        self.test = QPushButton("Probar conexión")
        self.test.clicked.connect(self._probe)
        self.test_result = QLabel()
        self.test_result.setWordWrap(True)

        form = QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow("Nombre", self.name)
        form.addRow("Tipo", self.kind)
        form.addRow("Fuente", self.source_stack)
        form.addRow("", self.enabled)
        form.addRow("", self.read_plates)
        form.addRow("", self.count_objects)
        form.addRow("", self.save_photos)
        form.addRow("", self.detect_weapons)
        form.addRow("", self.loop_video)
        form.addRow("Análisis", self.max_fps)
        form.addRow(self.test, self.test_result)

        for signal in (self.name.textChanged, self.url.textChanged, self.file.textChanged):
            signal.connect(self._store)
        for signal in (self.kind.currentIndexChanged, self.index.valueChanged, self.max_fps.valueChanged):
            signal.connect(self._store)
        for box in (self.enabled, self.read_plates, self.count_objects, self.save_photos, self.detect_weapons,
                    self.loop_video):
            box.toggled.connect(self._store)

    def load(self, camera: Camera | None) -> None:
        self.camera = None  # evita que _store escriba mientras se cargan los campos
        self.setEnabled(camera is not None)
        if camera is None:
            return
        kind = _source_kind(camera.source)
        self.name.setText(camera.name)
        self.kind.setCurrentIndex(kind)
        self.source_stack.setCurrentIndex(kind)
        self.url.setText(camera.source if kind == 0 else "")
        self.index.setValue(int(camera.source) if kind == 1 else 0)
        self.file.setText(camera.source if kind == 2 else "")
        self.enabled.setChecked(camera.enabled)
        self.read_plates.setChecked(camera.read_plates)
        self.count_objects.setChecked(camera.count_objects)
        self.save_photos.setChecked(camera.save_vehicle_photos)
        self.save_photos.setEnabled(camera.count_objects)
        self.detect_weapons.setChecked(camera.detect_weapons)
        self.loop_video.setChecked(camera.loop_video)
        self.max_fps.setValue(camera.max_fps)
        self.test_result.clear()
        self.camera = camera

    def _source(self) -> str:
        return (self.url.text().strip(), str(self.index.value()), self.file.text().strip())[self.kind.currentIndex()]

    def _store(self) -> None:
        if self.camera is None:
            return
        c = self.camera
        c.name = self.name.text().strip() or "Cámara"
        c.source = self._source()
        c.enabled = self.enabled.isChecked()
        c.read_plates = self.read_plates.isChecked()
        c.count_objects = self.count_objects.isChecked()
        c.save_vehicle_photos = self.save_photos.isChecked()
        c.detect_weapons = self.detect_weapons.isChecked()
        c.loop_video = self.loop_video.isChecked()
        c.max_fps = self.max_fps.value()
        self.changed.emit()

    def _browse(self) -> None:
        start = str(DEMO_VIDEO.parent) if DEMO_VIDEO.exists() else ""
        path, _ = QFileDialog.getOpenFileName(self, "Elegir video", start, "Videos (*.mp4 *.mov *.avi *.mkv)")
        if path:
            self.file.setText(path)

    def _probe(self) -> None:
        self.test.setEnabled(False)
        self.test_result.setText("Probando…")
        thread = ProbeThread(self._source(), self)
        thread.finished_with.connect(self._probe_done)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _probe_done(self, ok: bool, message: str) -> None:
        self.test.setEnabled(True)
        color = "#1e8e3e" if ok else "#d93025"
        self.test_result.setText(f"<span style='color:{color}'>{message}</span>")


class SettingsPage(QWidget):
    applied = Signal(object)
    """Emite la nueva ``Settings`` ya guardada."""

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.draft = settings.copy()

        self.camera_list = QListWidget()
        self.camera_list.currentRowChanged.connect(self._select_camera)
        add = QPushButton("Agregar cámara")
        add.clicked.connect(self._add_camera)
        remove = QPushButton("Eliminar")
        remove.clicked.connect(self._remove_camera)
        self.editor = CameraEditor()
        self.editor.changed.connect(self._camera_edited)
        list_column = QVBoxLayout()
        list_column.addWidget(self.camera_list, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(remove)
        list_column.addLayout(buttons)
        cameras_box = QGroupBox("Cámaras del condominio")
        cameras_layout = QHBoxLayout(cameras_box)
        cameras_layout.addLayout(list_column, 1)
        cameras_layout.addWidget(self.editor, 2)

        self.device = QComboBox()
        self.device.addItems(DEVICES)
        self.tracking_model = QComboBox()
        self.tracking_model.addItems(TRACKING_MODELS)
        self.plate_model = QComboBox()
        self.plate_model.addItems(PLATE_DETECTOR_MODELS)
        self.ocr_model = QComboBox()
        self.ocr_model.addItems(OCR_MODELS)
        self.tracking_conf = self._spin(0.1, 0.9)
        self.plate_conf = self._spin(0.1, 0.9)
        self.ocr_conf = self._spin(0.3, 0.99)
        self.votes = QSpinBox()
        self.votes.setRange(1, 10)
        self.cooldown = QSpinBox()
        self.cooldown.setRange(5, 3600)
        self.cooldown.setSuffix(" s")
        self.weapon_model = QComboBox()
        for name, spec in WEAPON_MODELS.items():
            self.weapon_model.addItem(spec.description, name)
        self.weapon_conf = self._spin(0.1, 0.95)
        self.weapon_votes = QSpinBox()
        self.weapon_votes.setRange(1, 10)
        self.weapon_cooldown = QSpinBox()
        self.weapon_cooldown.setRange(5, 600)
        self.weapon_cooldown.setSuffix(" s")
        models_box = QGroupBox("Detección")
        models = QFormLayout(models_box)
        models.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        models.addRow("Dispositivo", self.device)
        models.addRow("Modelo de seguimiento (YOLO26)", self.tracking_model)
        models.addRow("Confianza mínima de seguimiento", self.tracking_conf)
        models.addRow("Detector de placas", self.plate_model)
        models.addRow("Confianza mínima de placa", self.plate_conf)
        models.addRow("OCR de placas", self.ocr_model)
        models.addRow("Confianza mínima del OCR", self.ocr_conf)
        models.addRow("Lecturas iguales para confirmar", self.votes)
        models.addRow("No repetir la misma placa durante", self.cooldown)
        models.addRow("Detector de armas", self.weapon_model)
        models.addRow("Confianza mínima de arma", self.weapon_conf)
        models.addRow("Detecciones seguidas para alertar", self.weapon_votes)
        models.addRow("No repetir la alerta durante", self.weapon_cooldown)

        self.captures = QLineEdit()
        self.captures.setPlaceholderText(str(data_dir() / "captures"))
        choose = QPushButton("Elegir…")
        choose.clicked.connect(self._choose_captures)
        open_data = QPushButton("Abrir carpeta de datos")
        open_data.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir()))))
        storage_box = QGroupBox("Almacenamiento")
        storage = QHBoxLayout(storage_box)
        storage.addWidget(QLabel("Capturas"))
        storage.addWidget(self.captures, 1)
        storage.addWidget(choose)
        storage.addWidget(open_data)

        save = QPushButton("Guardar y reiniciar cámaras")
        save.setDefault(True)
        save.clicked.connect(self._save)
        discard = QPushButton("Descartar cambios")
        discard.clicked.connect(lambda: self.load(Settings.load()))
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(discard)
        actions.addWidget(save)

        content = QWidget()
        layout = QVBoxLayout(content)
        title = QLabel("Configuración")
        title.setProperty("role", "title")
        layout.addWidget(title)
        layout.addWidget(cameras_box)
        layout.addWidget(models_box)
        layout.addWidget(storage_box)
        layout.addLayout(actions)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        QVBoxLayout(self).addWidget(scroll)
        self.load(settings)

    @staticmethod
    def _spin(low: float, high: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setSingleStep(0.05)
        return spin

    def load(self, settings: Settings) -> None:
        self.draft = settings.copy()
        s = self.draft
        self.device.setCurrentText(s.device)
        self.tracking_model.setCurrentText(s.tracking_model)
        self.plate_model.setCurrentText(s.plate_detector_model)
        self.ocr_model.setCurrentText(s.ocr_model)
        self.tracking_conf.setValue(s.tracking_confidence)
        self.plate_conf.setValue(s.plate_confidence)
        self.ocr_conf.setValue(s.ocr_min_confidence)
        self.votes.setValue(s.votes_required)
        self.cooldown.setValue(int(s.repeat_cooldown_s))
        self.weapon_model.setCurrentIndex(max(self.weapon_model.findData(s.weapon_model), 0))
        self.weapon_conf.setValue(s.weapon_confidence)
        self.weapon_votes.setValue(s.weapon_votes_required)
        self.weapon_cooldown.setValue(int(s.weapon_cooldown_s))
        self.captures.setText(s.captures_dir)
        self._fill_camera_list(0)

    def _fill_camera_list(self, select: int) -> None:
        self.camera_list.blockSignals(True)
        self.camera_list.clear()
        for camera in self.draft.cameras:
            self.camera_list.addItem(camera.name + ("" if camera.enabled else " (inactiva)"))
        self.camera_list.blockSignals(False)
        if self.draft.cameras:
            self.camera_list.setCurrentRow(min(select, len(self.draft.cameras) - 1))
        self._select_camera(self.camera_list.currentRow())

    def _select_camera(self, row: int) -> None:
        self.editor.load(self.draft.cameras[row] if 0 <= row < len(self.draft.cameras) else None)

    def _camera_edited(self) -> None:
        row = self.camera_list.currentRow()
        camera = self.draft.cameras[row]
        self.camera_list.item(row).setText(camera.name + ("" if camera.enabled else " (inactiva)"))

    def _add_camera(self) -> None:
        self.draft.cameras.append(Camera(name=f"Cámara {len(self.draft.cameras) + 1}", source=""))
        self._fill_camera_list(len(self.draft.cameras) - 1)

    def _remove_camera(self) -> None:
        row = self.camera_list.currentRow()
        if row < 0:
            return
        camera = self.draft.cameras[row]
        answer = QMessageBox.question(self, "Eliminar cámara", f"¿Eliminar «{camera.name}»?")
        if answer == QMessageBox.StandardButton.Yes:
            del self.draft.cameras[row]
            self._fill_camera_list(row)

    def _choose_captures(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Carpeta de capturas", self.captures.text())
        if path:
            self.captures.setText(path)

    def _save(self) -> None:
        s = self.draft
        s.device = self.device.currentText()
        s.tracking_model = self.tracking_model.currentText()
        s.plate_detector_model = self.plate_model.currentText()
        s.ocr_model = self.ocr_model.currentText()
        s.tracking_confidence = round(self.tracking_conf.value(), 2)
        s.plate_confidence = round(self.plate_conf.value(), 2)
        s.ocr_min_confidence = round(self.ocr_conf.value(), 2)
        s.votes_required = self.votes.value()
        s.repeat_cooldown_s = float(self.cooldown.value())
        s.weapon_model = self.weapon_model.currentData()
        s.weapon_confidence = round(self.weapon_conf.value(), 2)
        s.weapon_votes_required = self.weapon_votes.value()
        s.weapon_cooldown_s = float(self.weapon_cooldown.value())
        s.captures_dir = self.captures.text().strip()
        missing = [c.name for c in s.cameras if c.enabled and not c.source]
        if missing:
            QMessageBox.warning(self, "Falta la fuente", f"Indique la fuente de: {', '.join(missing)}")
            return
        latest = Settings.load()  # la página de Conteo guarda la línea/zona por su cuenta
        for camera in s.cameras:
            if saved := latest.camera(camera.id):
                camera.counter = saved.counter
        s.save()
        self.applied.emit(s.copy())
