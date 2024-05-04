import cv2
import numpy as np
import torch
import matplotlib.path as matplotlib
from yolov5.utils.metrics import bbox_iou


class DwObjectCount:
    def __init__(self):
        super().__init__()
        self.model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
        self.points = []
        self.dw_done = False
        self.polygon_points = None
        self.detected_cars = []
        self.count_detection = 0

    def save_points(self, x, y):
        if len(self.points) < 5:
            self.points.append((x, y))
            self.polygon_points = np.array(self.points)
        else:
            self.dw_done = True

    def start_detect(self, frame):
        frame = frame
        prediction = self.model(frame)
        bboxes = self.get_bboxes(prediction)

        for box in bboxes:
            xc, yc = self.get_center(box)
            if self.is_valid_detection(xc, yc):
                matched = False
                for detected_car in self.detected_cars:
                    if self.bbox_iou(box, detected_car) > 0.1:
                        matched = True
                        break

                if not matched:
                    self.detected_cars.append(box)
                    self.count_detection += 1

            cv2.putText(img=frame, text=f"Autos: {self.count_detection}", org=(100, 100),
                        fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=1, color=(0, 0, 0), thickness=3)
            cv2.circle(img=frame, center=(xc, yc), radius=5, color=(0, 255, 255), thickness=1)
            cv2.rectangle(img=frame, pt1=(box[0], box[1]), pt2=(box[2], box[3]), color=(255, 255, 0), thickness=1)

        if len(self.points) > 1 and not self.dw_done:
            array_points = np.array(self.points, dtype=np.int32)
            cv2.polylines(frame, [array_points], isClosed=True, color=(0, 255, 0), thickness=2)

        if self.polygon_points is not None:
            cv2.polylines(frame, [self.polygon_points], isClosed=True, color=(0, 255, 0), thickness=2)

        if self.dw_done:
            self.dw_done = False

        return frame

    def is_valid_detection(self, xc, yc):
        if len(self.points) == 4:
            return matplotlib.Path(self.points).contains_point((xc, yc))
        else:
            return False

    @staticmethod
    def get_bboxes(detector):
        df = detector.pandas().xyxy[0]
        df = df[df["confidence"] >= 0.5]
        df = df[df["name"] == "car"]
        return df[["xmin", "ymin", "xmax", "ymax"]].values.astype(int)

    @staticmethod
    def get_center(bbox):
        center = ((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2)
        return center

    @staticmethod
    def bbox_iou(bbox1, bbox2):
        x1, y1, x2, y2 = bbox1
        x1g, y1g, x2g, y2g = bbox2

        inter_x1 = max(x1, x1g)
        inter_y1 = max(y1, y1g)
        inter_x2 = min(x2, x2g)
        inter_y2 = min(y2, y2g)

        inter_area = max(inter_x2 - inter_x1, 0) * max(inter_y2 - inter_y1, 0)
        bbox1_area = (x2 - x1) * (y2 - y1)
        bbox2_area = (x2g - x1g) * (y2g - y1g)

        iou = inter_area / float(bbox1_area + bbox2_area - inter_area)
        return iou

