import cv2
import torch


class ObjectCount:

    def __init__(self):
        super().__init__()
        self.detected_cars = []
        self.model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
        self.count_detection = 0

    def start_detector(self, frame):
        cv2.putText(img=frame, text=f"Autos: {self.count_detection}", org=(350, 300),
                    fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=1, color=(0, 0, 0), thickness=3)
        prediction = self.model(frame)
        bboxes = self.get_bboxes(prediction)
        for box in bboxes:
            cv2.rectangle(img=frame, pt1=(box[0], box[1]), pt2=(box[2], box[3]), color=(0, 255, 0), thickness=1)

            matched = False
            for detected_car in self.detected_cars:
                print(self.bbox_iou(box, detected_car))
                if self.bbox_iou(box, detected_car) > 0.01:
                    matched = True
                    break

            if not matched:
                self.detected_cars.append(box)
                self.count_detection += 1

        return frame

    @staticmethod
    def get_center(bbox):
        center = ((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2)
        return center

    @staticmethod
    def get_bboxes(detector):
        df = detector.pandas().xyxy[0]
        df = df[df["confidence"] >= 0.7]
        df = df[df["name"] == "car"]
        return df[["xmin", "ymin", "xmax", "ymax"]].values.astype(int)

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
