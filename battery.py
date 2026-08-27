class Battery:
    def __init__(self, capacity, charge_rate=1, discharge_rate=1):
        self.capacity = capacity
        self.current_charge = 0
        self.max_charge_rate = charge_rate
        self.max_discharge_rate = discharge_rate
        self.mode = None
        self.rate_percentage = 100
        self._status_time = 0

