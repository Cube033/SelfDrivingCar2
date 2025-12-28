# input/mock_input.py

import time

class MockSteeringInput:
    def values(self):
        sequence = [-1.0, -0.5, 0.0, 0.5, 1.0, 0.0]
        for v in sequence:
            yield v
            time.sleep(1)