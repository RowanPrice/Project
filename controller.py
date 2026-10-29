from nuclear import Reactor
from battery import Battery
from science import ScienceCentre
from science import Centrifuge
from administrative import Admin
import random
import time

class Game:
    def __init__(self):
        self.reactor = Reactor()
        self.power_plant_on:bool = True
        self.battery = Battery(1000000, charge_rate=100000, discharge_rate=80000)
        self.science_centre = ScienceCentre()
        self.admin = Admin()
        self.money:int = 100000
        self.energy_production:int = 0
        self.energy_production_multiplier:float = 1.0
        self.enrichment_in_progress:bool = False
        self.enrichment_elapsed:int = 0
        self.enrichment_duration:int = 120
        self.fuel_price:int = 10
        self.active_contract = None

    # Battery controls
    def select_battery_mode(self, mode:str):
        """
        Changes the battery mode

        Parameters
        ----------
        mode: mode for the battery to be changed to - either charging or discharging

        Returns
        -------

        """
        mode = mode.lower()
        if mode not in ("charging", "discharging"):
            raise ValueError("Mode must be 'charging' or 'discharging'")
        self.battery.mode = mode

    def set_battery_rate(self, percentage:int):
        """
        The rate for the battery to charge/discharge at

        Parameters
        ----------
        percentage: percentage to charge at

        Returns
        -------

        """
        if not 0 <= percentage <= 100:
            raise ValueError("Rate percentage must be between 0 and 100")
        self.battery.rate_percentage = percentage

    def update_battery(self, elapsed_seconds):
        if elapsed_seconds < 0:
            raise ValueError("Elapsed time cannot be negative")
        if self.battery.mode is None:
            return 0

        if self.battery.mode == "charging":
            rate = self.battery.max_charge_rate
        else:
            rate = self.battery.max_discharge_rate

        amount = rate * (self.battery.rate_percentage / 100) * elapsed_seconds
        if self.battery.mode == "charging":
            changed = self.add_battery_charge(amount)
            self.battery._status_time += elapsed_seconds
            while self.battery._status_time >= 1:
                print(f"Battery charge: {self.battery.current_charge:g}/{self.battery.capacity:g}")
                self.battery._status_time -= 1
            if self.battery.current_charge >= self.battery.capacity:
                self.battery.mode = None
        else:
            changed = self.use_battery_charge(amount)
            if self.battery.current_charge <= 0:
                self.battery.mode = None
        return changed

    def add_battery_charge(self, amount:int) -> int:
        """
        Adds charge to the battery, cannot go over capacity

        Parameters
        ----------
        amount: amount of charge to be added to the battery

        Returns
        -------
        allowed: amount of charge that has been added to the battery
        """
        if amount < 0:
            raise ValueError("Amount cannot be negative")
        allowed = min(amount, self.battery.capacity - self.battery.current_charge)
        self.battery.current_charge += allowed
        return allowed

    def use_battery_charge(self, amount:int) -> int:
        """
        Removes charge from the battery, cannot go into negative

        Parameters
        ----------
        amount: amount of charge to be removed from the battery

        Returns
        -------
        allowed: amount of charge removed from the battery
        """
        if amount < 0:
            raise ValueError("Amount cannot be negative")
        allowed = min(amount, self.battery.current_charge)
        self.battery.current_charge -= allowed
        return allowed

    def recharge_battery(self):
        """
        Fully recharges battery
        """
        self.battery.current_charge = self.battery.capacity

    def buy_unenriched_fuel(self, amount:int) -> bool:
        """
        Exchanges money for unenriched fuel

        Parameters
        ----------
        amount: amount of fuel to be purchased

        Returns
        -------
        True
        """
        if amount <= 0 or self.money < amount * self.fuel_price:
            return False
        self.money -= amount * self.fuel_price
        self.science_centre.unenriched_fuel += amount
        return True

    def start_enrichment(self, fuel_amount:int=100) -> bool:
        """
        starts conversion of unusable unenriched fuel into usable enriched fuel

        Parameters
        ----------
        fuel_amount: amount of fuel to be enriched

        Returns
        -------
        True: if the enrichment can be started
        False: if the enrichment cannot be started
        """
        if self.enrichment_in_progress:
            return False
        if fuel_amount <= 0 or fuel_amount > self.science_centre.unenriched_fuel:
            return False

        centrifuge = self.science_centre.centrifuge
        self.enrichment_duration = (centrifuge.time_per_fuel * fuel_amount) / 1 + fuel_amount*0.005 + centrifuge.speed_multiplier
        self.enrichment_elapsed = 0
        self.science_centre.unenriched_fuel -= fuel_amount
        self.enrichment_in_progress = True
        return True

    def update_enrichment(self, elapsed_seconds:int):
        if elapsed_seconds < 0:
            raise ValueError("Elapsed time cannot be negative")
        if not self.enrichment_in_progress:
            return False

        self.enrichment_elapsed = min(self.enrichment_elapsed + elapsed_seconds, self.enrichment_duration)
        if self.enrichment_elapsed >= self.enrichment_duration:
            self.enrichment_in_progress = False
            return True
        return False

    def skip_enrichment(self):
        if not self.enrichment_in_progress:
            return False
        self.enrichment_elapsed = self.enrichment_duration
        self.update_enrichment(0)
        return True

    def get_enrichment_status(self):
        if self.enrichment_in_progress:
            progress = self.enrichment_elapsed / self.enrichment_duration
            time_left = self.enrichment_duration - self.enrichment_elapsed
        else:
            progress = 1 if self.enrichment_elapsed >= self.enrichment_duration and self.enrichment_duration else 0
            time_left = 0
        return {
            "in_progress": self.enrichment_in_progress,
            "progress": progress,
            "time_left": time_left,
            "duration": self.enrichment_duration
        }

    def purchase_upgrade(self, category_name, upgrade_name):
        upgrades = self.science_centre.upgrades
        if category_name not in upgrades or upgrade_name not in upgrades[category_name]:
            return False
        upgrade = upgrades[category_name][upgrade_name]
        if upgrade["purchased"]:
            return False
        if self.money < upgrade["cost"]:
            return False
        self.money -= upgrade["cost"]
        upgrade["purchased"] = True
        return True

    def upgrade_centrifuge_quality(self):
        centrifuge = self.science_centre.centrifuge
        if centrifuge.quality_level >= centrifuge.max_level:
            return 0
        centrifuge.quality_level += 1
        return centrifuge.quality_cost

    def upgrade_centrifuge_speed(self):
        centrifuge = self.science_centre.centrifuge
        if centrifuge.speed_level >= centrifuge.max_level:
            return 0
        centrifuge.speed_level += 1
        return centrifuge.speed_cost

    def get_centre_status(self):
        centre = self.science_centre
        centrifuge = centre.centrifuge
        return {
            "enriched_fuel": centre.enriched_fuel,
            "unenriched_fuel": centre.unenriched_fuel,
            "speed_multiplier": centrifuge.speed_multiplier,
            "upgrades": centre.upgrades
        }

    def update_energy(self):
        if not self.power_plant_on:
            self.energy_production = 0
        else:
            self.energy_production = self.energy_production_multiplier * self.reactor.temperature * (10**(self.reactor.temperature/self.reactor.meltdown_temperature))
        

    def update_temperature(self):
        average_rod_depth = sum(self.reactor.rods) / self.reactor.num_rods
        reactivity = average_rod_depth / self.reactor.max_rod_depth
        self.reactor.temperature = self.reactor.base_temperature + reactivity * self.reactor.heat_factor
        self.reactor.temperature += random.uniform(-2, 2)
        if self.reactor.temperature > self.reactor.auto_scram_temperature and self.reactor.auto_scram == True:
            return(True)

    def get_status(self):
        return {
            'temperature': round(self.reactor.temperature, 1),
            'rods': self.reactor.rods.copy(),
            'average_rod_depth': round(sum(self.reactor.rods) / self.reactor.num_rods, 1),
            'current_rod': self.reactor.current_rod
        }

    def auto_scram(self):
        print('Reactor temperature exceeded safe limits. Auto scram initiated')
        time.sleep(1)
        for i in range(len(self.reactor.rods)):
            self.lower_rod(i, self.reactor.max_rod_depth)
            time.sleep(0.3)

    def change_power_plant_state(self):
        """Toggle the power plant state between on and off"""
        self.power_plant_on = not self.power_plant_on
        return self.power_plant_on

    def raise_rod(self, rod_index, raise_amount):
        """Raise a rod to increase reactivity"""
        if 0 <= rod_index < self.reactor.num_rods:
            if self.reactor.rods[rod_index]+raise_amount <= self.reactor.max_rod_depth:
                self.reactor.rods[rod_index] += raise_amount
                self.update_temperature()
                print(f"Rod {rod_index} raised to depth {self.reactor.rods[rod_index]}")
            else:
                self.reactor.rods[rod_index] = self.reactor.max_rod_depth
                print(f"Rod {rod_index} raised to depth {self.reactor.max_rod_depth}")

    def lower_rod(self, rod_index, lower_amount):
        """Lower a rod to decrease reactivity"""
        if 0 <= rod_index and rod_index < self.reactor.num_rods:
            if self.reactor.rods[rod_index]-lower_amount >= 0:
                self.reactor.rods[rod_index] -= lower_amount
                self.update_temperature()
                print(f"Rod {rod_index} lowered to depth {self.reactor.rods[rod_index]}")
            else:
                self.reactor.rods[rod_index] = 0
                print(f"Rod {rod_index} lowered to depth 0")

if __name__ == "__main__":
    reactor = Game()
    reactor.auto_scram()