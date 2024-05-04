import os
import cv2
from ultralytics import YOLO
from lib.util import read_license_plate

license_plate_detector = YOLO('assets/models/license_plate_detector.pt')


class Plate:
    def __init__(self, frame):
        self.license_plate_text = None
        self.frame = frame
        self.license_plates = license_plate_detector(frame)[0]

    def get(self):
        for r in self.license_plates:
            boxes = r.boxes
            # object details
            x1, y1, x2, y2 = map(int, boxes[0].xyxy[0])
            # crop license plate
            license_plate_crop = self.frame[y1:y2, x1: x2, :]
            # improve the image
            alpha = 1.0
            beta = 0
            contrast_image = cv2.convertScaleAbs(license_plate_crop, alpha=alpha, beta=beta)
            # read license plate number
            result = read_license_plate(contrast_image)
            cv2.imwrite(os.path.join('assets/images/capture/', f"{result}-1.jpg"), contrast_image)
            if result is not None:
                self.license_plate_text = result
                break
            break

        return self.license_plate_text
