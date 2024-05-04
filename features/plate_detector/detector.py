import numpy as np
import cv2
from tensorflow.lite.python.interpreter import Interpreter
import string
import random


class Detector:
    def __init__(self, min_confidence=0.5):
        self.model_path = "assets/models/detect.tflite"
        self.label_path = "assets/labels/labelmap.txt"
        self.min_confidence = min_confidence
        self.interpreter = Interpreter(model_path=self.model_path)
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
        self.height = self.input_details[0]['shape'][1]
        self.width = self.input_details[0]['shape'][2]
        self.float_input = (self.input_details[0]['dtype'] == np.float32)
        self.input_mean = 127.5
        self.input_std = 127.5
        self.min_conf = 0.5
        self.labels = self.load_labels()

    @staticmethod
    def randomName():
        charter = string.ascii_letters + string.digits
        return ''.join(random.choice(charter) for _ in range(6))

    def load_labels(self):
        with open(self.label_path, 'r') as file:
            return [line.strip() for line in file.readlines()]

    def detect(self, frame):
        isSave = False
        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        imH, imW, _ = frame.shape
        image_resized = cv2.resize(image_rgb, (self.width, self.height))
        input_data = np.expand_dims(image_resized, axis=0)

        if self.float_input:
            input_data = (np.float32(input_data) -
                          self.input_mean) / self.input_std

        self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
        self.interpreter.invoke()

        boxes = self.interpreter.get_tensor(self.output_details[1]['index'])[0]
        classes = self.interpreter.get_tensor(self.output_details[3]['index'])[
            0]
        scores = self.interpreter.get_tensor(self.output_details[0]['index'])[
            0]

        for i in range(len(scores)):
            if (scores[i] > self.min_conf) and (scores[i] <= 1.0):
                ymin, xmin, ymax, xmax = boxes[i]
                (xmin, xmax, ymin, ymax) = (
                    xmin * imW, xmax * imW, ymin * imH, ymax * imH)
                cv2.rectangle(frame, (int(xmin), int(ymin)),
                              (int(xmax), int(ymax)), (10, 255, 0), 2)

                object_name = self.labels[int(classes[i])]
                label = '%s: %d%%' % (object_name, int(scores[i]*100))

                if scores[i] > 0.95:
                    isSave = True
                labelSize, baseLine = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                label_ymin = max(ymin, labelSize[1] + 10)
                cv2.rectangle(frame, (int(xmin), int(label_ymin-labelSize[1]-10)), (int(
                    xmin+labelSize[0]), int(label_ymin+baseLine-10)), (255, 255, 255), cv2.FILLED)
                cv2.putText(frame, label, (int(xmin), int(label_ymin-7)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

        return [frame, isSave, self.randomName()]
