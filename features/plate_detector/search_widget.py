import os

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QMovie, QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel


class SearchWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.set_loading()

    def set_loading(self):
        """Remove all into the layout"""
        self.empty_layout()
        """Set Loading Widget into the layout"""
        imgLoading = QLabel(self)
        imgLoading.setStyleSheet("background-color: white")
        movie = QMovie(os.path.join("assets/images/", "b.gif"))
        movie.setScaledSize(QSize(260, 260))
        imgLoading.setMovie(movie)
        movie.start()
        self.layout.addWidget(imgLoading)

    def set_capture(self, path):
        """Remove all into the layout"""
        self.empty_layout()
        """Set Capture Widget into the layout"""
        image_label = QLabel(self)
        pixmap = QPixmap(path).scaled(self.size(), Qt.KeepAspectRatioByExpanding)
        image_label.setPixmap(pixmap)
        self.layout.addWidget(image_label)

    def empty_layout(self):
        for i in reversed(range(self.layout.count())):
            widget_to_remove = self.layout.itemAt(i).widget()
            self.layout.removeWidget(widget_to_remove)
            widget_to_remove.setParent(None)
