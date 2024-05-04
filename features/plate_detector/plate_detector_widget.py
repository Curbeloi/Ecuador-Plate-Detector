import os
import cv2
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap, QKeyEvent
from PyQt5.QtWidgets import QWidget, QLabel, QSplitter, QVBoxLayout
from features.plate_detector.detector import Detector
from features.plate_detector.person_info_widget import PersonInfoWidget
from features.plate_detector.plate import Plate
from features.plate_detector.search_widget import SearchWidget
from lib.camera_capture import CameraCapture


class PlateDetectorWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()
        self.detector = Detector()
        self.splitter_right = None
        self.plate = None
        self.layout = QVBoxLayout(self)
        self.camera_capture = CameraCapture()
        self.camera_label = QLabel()
        self.search = SearchWidget()
        """Temp vars for test"""
        self.plateList = []
        self.plateScanList = ['PCX-7679']

        self.person = PersonInfoWidget(
            os.path.join("assets/images/", "default.jpg"),
            "",
            "",
            "",
            "",
            [
                ("Marca", ""),
                ("Modelo", ""),
                ("Año", ""),
                ("Color", ""),
                ("Placa", "")
            ]
        )

        self.setupInitialLayout()

    def setupInitialLayout(self):
        # Split Main Area
        splitter_main = QSplitter(Qt.Horizontal)
        splitter_main.addWidget(self.camera_label)
        # Split Right Area
        self.splitter_right = QSplitter(Qt.Vertical)
        # Image Capture (Two content)
        self.splitter_right.addWidget(self.search)
        # Image Capture (Three content)
        self.splitter_right.addWidget(self.person)
        splitter_main.addWidget(self.splitter_right)
        # Adjust initial proportions: left larger than right
        splitter_main.setSizes([500, 300])
        self.layout.addWidget(splitter_main)
        self.camera_capture.start_capture()
        self.camera_capture.frameCaptured.connect(self.updateVideoLabel)

    def updateVideoLabel(self, frame):
        result = self.detector.detect(frame)
        frame = result[0]
        height, width = frame.shape[:2]
        aspect_ratio = width / height
        new_height = int(1024 / aspect_ratio)
        frame = cv2.resize(frame, (1024, new_height))
        result[0] = cv2.resize(frame, (1024, new_height))
        height, width, channels = frame.shape
        bytes_per_line = channels * width
        p = QImage(frame.data, width, height,
                   bytes_per_line, QImage.Format_RGB888)
        self.camera_label.setPixmap(QPixmap.fromImage(p))
        if result[1]:
            self.plateDetector(result)

    def plateDetector(self, result):
        path = 'assets/images/capture/'
        if not os.path.exists(path):
            os.makedirs(path)
        self.plate = Plate(result[0]).get()
        if self.plate is not None and self.plate not in self.plateList:
            self.foundPlate(result)

    def foundPlate(self, result):
        self.camera_capture.pause_capture()
        self.plateList.append(self.plate)
        """Save capture"""
        path = 'assets/images/capture/'
        if not os.path.exists(path):
            os.makedirs(path)
        cv2.imwrite(os.path.join(path, f"{self.plate}.jpg"), result[0])
        """Show Capture"""
        self.search.set_capture(os.path.join(path, f"{self.plate}.jpg"))
        self.person = PersonInfoWidget("assets/images/person.jpeg",
                               "Hector Curbelo Barrios",
                               "1757090533",
                               "40",
                               "Pichincha",
                               [
                                   ("Marca", "Toyota"),
                                   ("Modelo", "Corolla"),
                                   ("Año", "2020"),
                                   ("Color", "Azul"),
                                   ("Placa", "ABC123")
                               ])
        self.replaceWidget(self.person, 1)

    def replaceWidget(self, nuevo_widget, index):
        if self.splitter_right.count() > 0:
            widget_actual = self.splitter_right.widget(index)
            widget_actual.setVisible(False)
            widget_actual.setParent(None)
            widget_actual.deleteLater()
        self.splitter_right.insertWidget(index, nuevo_widget)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Space:
            self.person = PersonInfoWidget(
                os.path.join("assets/images/", "default.jpg"),
                "",
                "",
                "",
                "",
                [
                    ("Marca", ""),
                    ("Modelo", ""),
                    ("Año", ""),
                    ("Color", ""),
                    ("Placa", "")
                ]
            )
            self.replaceWidget(self.person, 1)
            self.camera_capture.start_capture()
            self.search.set_loading()

        else:
            super().keyPressEvent(event)
