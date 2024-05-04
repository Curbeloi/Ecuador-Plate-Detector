from PyQt5.QtWidgets import QApplication, QMainWindow, QSplitter, QLabel, QToolBar, QAction, QVBoxLayout, QWidget, \
    QActionGroup
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap

from features.dw_object_count.dw_object_count_widget import DwObjectCountWidget
from features.plate_detector.plate_detector_widget import PlateDetectorWidget
from lib.camera_capture import CameraCapture
from features.object_count.object_count_widget import ObjectCountWidget
from features.plate_detector.detector import Detector


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.actionGroup = None
        self.detector = Detector()
        self.toolbar = None
        self.central_widget = None
        self.setWindowTitle("Smart Traffic")
        # self.showFullScreen()
        self.initUI()
        self.camera_capture = CameraCapture()
        self.camera_label = QLabel()
        # Last Image Capture
        self.splitter_right = None
        self.setMinimumSize(1280, 720)
        self.setMaximumSize(1280, 720)
        self.start_action = None
        self.detector_action = None
        self.dw_action = None
        self.count_action = None
        self.std_action = None
        self.stt_action = None

    def initUI(self):
        self.toolbar = QToolBar()
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self.actionGroup = QActionGroup(self)

        self.start_action = QAction(QIcon("assets/images/home.png"), "Inicio", self)
        self.start_action.setCheckable(True)

        self.detector_action = QAction(QIcon("assets/images/camera.png"), "Detención de Placas", self)
        self.detector_action.setCheckable(True)

        self.dw_action = QAction(QIcon("assets/images/zone.png"), "Zona de Conteo", self)
        self.dw_action.setCheckable(True)

        self.count_action = QAction(QIcon("assets/images/conteo.png"), "Conteo de Objetos", self)
        self.count_action.setCheckable(True)

        self.std_action = QAction(QIcon("assets/images/std.png"), "Estadísticas", self)
        self.std_action.setCheckable(True)

        self.stt_action = QAction(QIcon("assets/images/stt.png"), "Configuraciones", self)
        self.stt_action.setCheckable(True)

        # Action Group
        self.actionGroup.addAction(self.start_action)
        self.actionGroup.addAction(self.detector_action)
        self.actionGroup.addAction(self.dw_action)
        self.actionGroup.addAction(self.count_action)
        self.actionGroup.addAction(self.std_action)
        self.actionGroup.addAction(self.stt_action)

        # Add action to toolbar
        self.toolbar.addAction(self.start_action)
        self.toolbar.addAction(self.detector_action)
        self.toolbar.addAction(self.dw_action)
        self.toolbar.addAction(self.count_action)
        self.toolbar.addAction(self.std_action)
        self.toolbar.addAction(self.stt_action)

        # Connect actions
        self.start_action.triggered.connect(self.setInitialLayout)
        self.detector_action.triggered.connect(self.setupPlateDetector)
        self.dw_action.triggered.connect(self.setupCountDwLayout)
        self.count_action.triggered.connect(self.setupCountLayout)
        self.std_action.triggered.connect(self.setupStdLayout)
        self.stt_action.triggered.connect(self.setupSttLayout)

        self.setupInitialLayout()

    def setupInitialLayout(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QVBoxLayout(self.central_widget)
        image_label = QLabel(self.central_widget)
        pixmap = QPixmap("assets/images/fondo.jpg")
        image_label.setPixmap(pixmap)
        image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(image_label)

    def setInitialLayout(self, checked):
        if checked:
            self.clearLayout()
            self.central_widget = QWidget()
            self.setCentralWidget(self.central_widget)
            layout = QVBoxLayout(self.central_widget)
            image_label = QLabel(self.central_widget)
            pixmap = QPixmap("assets/images/fondo.jpg").scaled(self.size(), Qt.KeepAspectRatioByExpanding)
            image_label.setPixmap(pixmap)
            image_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(image_label)

    def setupPlateDetector(self, checked):
        if checked:
            self.clearLayout()
            captureWindget = PlateDetectorWidget()
            self.setCentralWidget(captureWindget)

    def setupCountDwLayout(self, checked):
        if checked:
            self.clearLayout()
            dwObjectCount = DwObjectCountWidget()
            self.setCentralWidget(dwObjectCount)

    def setupCountLayout(self, checked):
        if checked:
            self.clearLayout()
            objectCount = ObjectCountWidget()
            self.setCentralWidget(objectCount)

    def setupStdLayout(self, checked):
        if checked:
            self.clearLayout()

    def setupSttLayout(self, checked):
        if checked:
            self.clearLayout()

    def clearLayout(self):
        if self.centralWidget():
            self.centralWidget().deleteLater()


app = QApplication([])
window = MainWindow()
window.show()
app.exec_()
