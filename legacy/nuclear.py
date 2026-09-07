class Reactor:
    def __init__(self, initial_temperature=20, num_rods=5, max_rod_depth=100, auto_scram_temperature=1000 , auto_scram=True, cold_shutdown_temperature=93, meltdown_temperature=2700):
        self.temperature = initial_temperature
        self.rods = [0] * num_rods  # 0 = fully inserted, max_rod_depth = fully withdrawn
        self.max_rod_depth = max_rod_depth
        self.num_rods = num_rods
        self.base_temperature = initial_temperature
        self.auto_scram_temperature = auto_scram_temperature # this is much higher than the actual temperature for an autoscram, which is only a few degrees off of normal operating temperature
        self.auto_scram = auto_scram
        self.cold_shutdown_temperature = cold_shutdown_temperature
        self.meltdown_temperature = meltdown_temperature
        self.heat_factor = 1000 # How much temperature increases per unit of rod withdrawal
        self.current_rod = 0