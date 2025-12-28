# control/controller.py

import config


class SteeringController:
    def __init__(self, steering_mapper, servo):
        self.mapper = steering_mapper
        self.servo = servo

    def update(self, steering_value: float):
        # clamp input
        steering_value = max(-1.0, min(1.0, steering_value))

        # apply mapper (dead zone + invert)
        mapped = self.mapper.apply(steering_value)

        # steering gain
        mapped *= config.STEERING_GAIN

        # final clamp
        mapped = max(-1.0, min(1.0, mapped))

        # send to servo
        self.servo.set_normalized(mapped)