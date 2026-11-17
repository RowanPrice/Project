class Centrifuge:
    def __init__(self):
        self.time_per_fuel = 1.2
        self.speed_multiplier = 0

class ScienceCenter:
    def __init__(self, enriched_fuel:int = 100, unenriched_fuel:int = 100, fuel_usage_rate:int = 1):
        self.enriched_fuel = enriched_fuel
        self.unenriched_fuel = unenriched_fuel
        self.fuel_usage_rate = fuel_usage_rate
        self.centrifuge = Centrifuge()