from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap, QMouseEvent

from features.dw_object_count.dw_object_count import DwObjectCount
from lib.camera_capture import CameraCapture


class DwObjectCountWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.videoLabel = QLabel("Awaiting to capture...")
        self.videoLabel.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.videoLabel)
        self.dwObjectCount = DwObjectCount()
        """Create Object and Start Camera Capture"""
        self.camera_capture = CameraCapture()
        self.camera_capture.start_capture()
        self.camera_capture.frameCaptured.connect(self.updateVideoLabel)

    def mousePressEvent(self, event: QMouseEvent):
        point = event.pos()
        self.dwObjectCount.save_points(point.x(), point.y())
        super().mousePressEvent(event)

    """Precess frame and object detect"""
    def updateVideoLabel(self, frame):
        frame = self.dwObjectCount.start_detect(frame)
        height, width, channels = frame.shape
        bytes_per_line = channels * width
        p = QImage(frame.data, width, height,
                   bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(p)
        self.videoLabel.setPixmap(pixmap)
