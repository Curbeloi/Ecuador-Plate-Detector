from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap

from lib.camera_capture import CameraCapture
from features.object_count.object_count import ObjectCount


class ObjectCountWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.videoLabel = QLabel("Awaiting to capture...")
        self.videoLabel.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.videoLabel)
        self.objectCount = ObjectCount()
        """Create Object and Start Camera Capture"""
        self.camera_capture = CameraCapture()
        self.camera_capture.start_capture()
        self.camera_capture.frameCaptured.connect(self.updateVideoLabel)

    """Precess frame and object detect"""
    def updateVideoLabel(self, frame):
        frame = self.objectCount.start_detector(frame)
        height, width, channels = frame.shape
        bytes_per_line = channels * width
        p = QImage(frame.data, width, height,
                   bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(p)
        self.videoLabel.setPixmap(pixmap)
