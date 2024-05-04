import os

from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt


class PersonInfoWidget(QWidget):
    def __init__(self, imagePath, name, identification, yearOld, estate, vehicle):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.imagePath = imagePath
        self.name = name
        self.identification = identification
        self.yearOld = yearOld
        self.estate = estate
        self.vehicle = vehicle
        self.initUI()

    def initUI(self):
        bgColor = self.palette().window().color()
        luminance = (0.299 * bgColor.red() + 0.587 * bgColor.green() + 0.114 * bgColor.blue()) / 255
        textColor = "white" if luminance < 0.5 else "black"
        self.setStyleSheet(f"QLabel {{ color: {textColor}; }}")

        imgLabel = QLabel(self)
        pixmap = QPixmap(self.imagePath)
        imgLabel.setPixmap(pixmap.scaled(100, 100, Qt.KeepAspectRatio))
        self.layout.addWidget(imgLabel)

        infoLayout = QVBoxLayout()
        nameLabel = QLabel(f"Nombre: {self.name}")
        idLabel = QLabel(f"ID: {self.identification}")
        yearLabel = QLabel(f"Edad: {self.yearOld}")
        stateLabel = QLabel(f"Provincia: {self.estate}")
        infoLayout.addWidget(nameLabel)
        infoLayout.addWidget(idLabel)
        infoLayout.addWidget(stateLabel)
        infoLayout.addWidget(yearLabel)

        self.layout.addLayout(infoLayout)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        self.layout.addWidget(separator)

        bottomLayout = QVBoxLayout()
        vehicleLabels = []
        for key, valor in self.vehicle:
            label = QLabel(f"{key}: {valor}")
            bottomLayout.addWidget(label)
            vehicleLabels.append(label)

        self.layout.addLayout(bottomLayout)
        self.setLayout(self.layout)


