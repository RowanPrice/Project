import time

class reactor:
    def __init__(self, temperature, rods):
        self.temperature = temperature
        self.rods = rods

    def heat_up(self,rod_depth):
