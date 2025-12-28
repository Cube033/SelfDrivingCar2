# control/arm_controller.py

class ArmController:
    def __init__(self):
        self.armed = False

    def arm(self):
        if not self.armed:
            print("[ARM] System armed")
        self.armed = True

    def disarm(self):
        if self.armed:
            print("[ARM] System disarmed")
        self.armed = False