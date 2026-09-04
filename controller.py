from nuclear import Reactor
from battery import Battery
from science import ScienceCentre
import random
import time

class Game:
    def __init__(self):
        self.reactor = Reactor()
        self.power_plant_on = False
        self.battery = Battery(1000000, charge_rate=100000, discharge_rate=80000)
        self.science_centre = ScienceCentre()
        self.money = 10000
        self.enrichment_in_progress = False
        self.enrichment_elapsed = 0
        self.enrichment_duration = 120
        self.enrichment_fuel_amount = 0
        self.enrichment_percentage = 0
        self.fuel_price = 10
        self.active_contract = None
        self.contracts = [
            {
                "title": "National Grid Supply",
                "pay_per_watt": 0.08,
                "total_power_required": 500,
                "time_to_complete": 10,
                "description": "Supply stable power to the national grid."
            },
            {
                "title": "Industrial Power Agreement",
                "pay_per_watt": 0.12,
                "total_power_required": 800,
                "time_to_complete": 15,
                "description": "Provide reliable energy for a high-demand industrial site."
            },
            {
                "title": "Emergency Reserve Contract",
                "pay_per_watt": 0.18,
                "total_power_required": 400,
                "time_to_complete": 5,
                "description": "Keep reserve capacity available for emergency demand."
            },
            {
                "title": "Research Facility Supply",
                "pay_per_watt": 0.15,
                "total_power_required": 1500,
                "time_to_complete": 20,
                "description": "Provide power to a cutting-edge research facility."
            },
            {
                "title": "Dr Frankenstein's Laboratory",
                "pay_per_watt": 0.50,
                "total_power_required": 100,
                "time_to_complete": 1,
                "description": "Supply electricity to Dr Frankenstein's laboratory."
            },
            {
                "title": "Larry's Lamps",
                "pay_per_watt": 0.50,
                "total_power_required": 700,
                "time_to_complete": 20,
                "description": "Supply electricity to a lamp shop."
            }
        ]

    # Battery controls
    def select_battery_mode(self, mode):
        mode = mode.lower()
        if mode not in ("charging", "discharging"):
            raise ValueError("Mode must be 'charging' or 'discharging'")
        self.battery.mode = mode

    def set_battery_rate(self, percentage):
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

    def add_battery_charge(self, amount):
        if amount < 0:
            raise ValueError("Amount cannot be negative")
        allowed = min(amount, self.battery.capacity - self.battery.current_charge)
        self.battery.current_charge += allowed
        return allowed

    def use_battery_charge(self, amount):
        if amount < 0:
            raise ValueError("Amount cannot be negative")
        allowed = min(amount, self.battery.current_charge)
        self.battery.current_charge -= allowed
        return allowed

    def recharge_battery(self):
        self.battery.current_charge = self.battery.capacity

    # Science Centre controls
    def buy_unenriched_fuel(self, amount):
        if amount <= 0 or self.money < amount * self.fuel_price:
            return False
        self.money -= amount * self.fuel_price
        self.science_centre.unenriched_fuel += amount
        return True

    def start_enrichment(self, fuel_amount=100, enrichment_percentage=4.5):
        if self.enrichment_in_progress:
            return False
        if fuel_amount <= 0 or fuel_amount > self.science_centre.unenriched_fuel:
            return False
        if not 0 <= enrichment_percentage <= 20:
            return False

        centrifuge = self.science_centre.centrifuge
        speed_multiplier = min(1.0 + (centrifuge.speed_level - 1) * 0.1, centrifuge.max_multiplier)
        self.enrichment_duration = (30 + fuel_amount * 0.9) / speed_multiplier
        self.enrichment_elapsed = 0
        self.enrichment_fuel_amount = fuel_amount
        self.enrichment_percentage = enrichment_percentage
        self.science_centre.unenriched_fuel -= fuel_amount
        self.enrichment_in_progress = True
        return True

    def update_enrichment(self, elapsed_seconds):
        if elapsed_seconds < 0:
            raise ValueError("Elapsed time cannot be negative")
        if not self.enrichment_in_progress:
            return False

        self.enrichment_elapsed = min(self.enrichment_elapsed + elapsed_seconds, self.enrichment_duration)
        if self.enrichment_elapsed >= self.enrichment_duration:
            self.nuclear_fuel_enrichment(self.enrichment_fuel_amount, self.enrichment_percentage)
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

    def add_upgrade_category(self, category_name):
        if category_name not in self.science_centre.upgrades:
            self.science_centre.upgrades[category_name] = {}
            return True
        return False

    def add_upgrade(self, category_name, upgrade_name, cost, effect):
        if category_name not in self.science_centre.upgrades:
            print(f"Category '{category_name}' does not exist")
            return False
        if upgrade_name in self.science_centre.upgrades[category_name] or cost < 0:
            return False
        self.science_centre.upgrades[category_name][upgrade_name] = {
            "cost": cost,
            "effect": effect,
            "purchased": False
        }
        return True

    def purchase_upgrade(self, category_name, upgrade_name):
        upgrades = self.science_centre.upgrades
        if category_name not in upgrades or upgrade_name not in upgrades[category_name]:
            return False
        upgrade = upgrades[category_name][upgrade_name]
        if upgrade["purchased"]:
            return False
        if self.money < upgrade["cost"]:
            print("Not enough money to purchase this upgrade")
            return False
        self.money -= upgrade["cost"]
        upgrade["purchased"] = True
        print(f"Purchased '{upgrade_name}' for £{upgrade['cost']}")
        print(f"Effect: {upgrade['effect']}")
        return True

    def upgrade_centrifuge_quality(self):
        centrifuge = self.science_centre.centrifuge
        if centrifuge.quality_level >= centrifuge.max_level:
            print(f"Centrifuge quality is already at maximum level {centrifuge.max_level}")
            return 0
        centrifuge.quality_level += 1
        return centrifuge.quality_cost

    def upgrade_centrifuge_speed(self):
        centrifuge = self.science_centre.centrifuge
        if centrifuge.speed_level >= centrifuge.max_level:
            print(f"Centrifuge speed is already at maximum level {centrifuge.max_level}")
            return 0
        centrifuge.speed_level += 1
        return centrifuge.speed_cost

    def nuclear_fuel_enrichment(self, fuel_amount, enrichment_percentage):
        if fuel_amount < 0 or not 0 <= enrichment_percentage <= 20:
            return False
        centrifuge = self.science_centre.centrifuge
        multiplier = min(1.0 + (centrifuge.quality_level - 1) * 0.1, centrifuge.max_multiplier)
        adjusted_enrichment = min(enrichment_percentage * multiplier, 20)
        self.science_centre.enriched_fuel += fuel_amount
        self.science_centre.enrichment_level = adjusted_enrichment
        print(f"Enriched {fuel_amount} units to {adjusted_enrichment:.2f}%")
        return True

    def get_centre_status(self):
        centre = self.science_centre
        centrifuge = centre.centrifuge
        enrichment_multiplier = min(1.0 + (centrifuge.quality_level - 1) * 0.1, centrifuge.max_multiplier)
        speed_multiplier = min(1.0 + (centrifuge.speed_level - 1) * 0.1, centrifuge.max_multiplier)
        return {
            "enriched_fuel": centre.enriched_fuel,
            "unenriched_fuel": centre.unenriched_fuel,
            "enrichment_level": centre.enrichment_level,
            "quality_level": centrifuge.quality_level,
            "speed_level": centrifuge.speed_level,
            "enrichment_multiplier": round(enrichment_multiplier, 2),
            "speed_multiplier": round(speed_multiplier, 2),
            "upgrades": centre.upgrades
        }

    def update_temperature(self):
        """Update core temperature based on average rod position"""
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