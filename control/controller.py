# control/controller.py

class SteeringController:
    def __init__(self, steering_mapper, servo):
        self.mapper = steering_mapper
        self.servo = servo

    def update(self, steering_value: float):
       steering_value = max(-1.0, min(1.0, steering_value))
       mapped = self.mapper.apply(steering_value)
        mapped *= config.STEERING_GAIN
        mapped = max(-1.0, min(1.0, mapped))
        self.servo.set_normalized(mapped)   