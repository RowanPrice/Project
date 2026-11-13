from nuclear import Reactor
from battery import Battery
from science import ScienceCenter
from science import Centrifuge
from administrative import Admin
import random
import time

class Game:
    """
    Class to manage game state

    Attributes
    ----------
        reactor
            creates the reactor class
        power_plant_on
            whether the power plant is on, allowing energy to be made and control rods to be moved
        battery
            creates the battery class
        science_center
            creates the science center class
        admin
            creates the admin class
        money
            the amount of money the user has available
        energy_production
            users current energy production, based off of the reactor temperature and the users energy production multiplier
        energy_production_multiplier
            users energy production multiplier, based off of their upgrades
        enrichment_in_progress
            whether enrichment is currently in progress
        enrichment_elapsed
            the time elapsed during current enrichment
        enrichment_duration
            the time that needs to be elapsed for enrichment to stop
        fuel_price
            price per unit of unenriched fuel
        active_contract
            index of the current active contract, -1 if no contract is active
        scrammed_recently
            whether the plant has scrammed recently; this exists as scram is used to lower the rods when the plant is off and dont want constant scramming
    """
    def __init__(self):
        self.reactor = Reactor()
        self.power_plant_on:bool = True
        self.battery = Battery(1000000, charge_rate=100000, discharge_rate=80000)
        self.science_center = ScienceCenter()
        self.admin = Admin()
        self.money:int = 100000
        self.energy_production:int = 0
        self.energy_production_multiplier:float = 1.0
        self.enrichment_in_progress:bool = False
        self.enrichment_elapsed:int|float = 0
        self.enrichment_duration:int|float = 120
        self.fuel_price:int = 1000
        self.active_contract = -1
        self.scrammed_recently = False

    # Battery controls
    def select_battery_mode(self, mode:str):
        """
        Changes the battery mode

        Parameters
        ----------
            mode: str
                mode for the battery to be changed to - either charging or discharging

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
            percentage: int
                percentage to charge at

        Returns
        -------

        """
        if not 0 <= percentage <= 100:
            raise ValueError("Rate percentage must be between 0 and 100")
        self.battery.rate_percentage = percentage

    def update_battery(self, elapsed_seconds:int|float) -> int|float:
        """
        if the battery's mode is charging or discharging, handle calling either of the applicable functions

        Parameters
        ----------
            elapsed_seconds: int
                time passed since last update

        Returns
        -------
            changed: int
                the amount the battery charged or discharged(this is what is returned during the functions; allowed)
        """
        if elapsed_seconds < 0:
            raise ValueError("Elapsed time cannot be negative")
        if self.battery.mode is None:
            return 0

        if self.battery.mode == "charging":
            rate = min(self.battery.max_charge_rate, self.energy_production)
        else:
            rate = self.battery.max_discharge_rate

        amount = rate * elapsed_seconds
        if self.battery.mode == "charging":
            changed = self.add_battery_charge(amount)
            self.battery.status_time += elapsed_seconds
            while self.battery.status_time >= 1:
                print(f"Battery charge: {self.battery.current_charge:g}/{self.battery.capacity:g}")
                self.battery.status_time -= 1
            if self.battery.current_charge >= self.battery.capacity:
                self.battery.mode = None
        else:
            changed = self.use_battery_charge(amount)
            if self.battery.current_charge <= 0:
                self.battery.mode = None
        return changed

    def add_battery_charge(self, amount:int|float) -> int|float:
        """
        Adds charge to the battery, cannot go over capacity

        Parameters
        ----------
            amount: int
                amount of charge to be added to the battery

        Returns
        -------
            allowed: int
                amount of charge that has been added to the battery
        """
        if amount < 0:
            raise ValueError("Amount cannot be negative")
        allowed = min(amount, self.battery.capacity - self.battery.current_charge)
        self.battery.current_charge += allowed
        return allowed

    def use_battery_charge(self, amount:int|float) -> int|float:
        """
        Removes charge from the battery, cannot go into negative

        Parameters
        ----------
            amount: int
                amount of charge to be removed from the battery

        Returns
        -------
            allowed: int
                amount of charge removed from the battery
        """
        if amount < 0:
            raise ValueError("Amount cannot be negative")
        allowed = min(amount, self.battery.current_charge)
        self.battery.current_charge -= allowed
        return allowed

    def recharge_battery(self):
        """
        sets battery charge to its maximum

        Returns
        -------

        """
        self.battery.current_charge = self.battery.capacity

    def buy_unenriched_fuel(self, amount:int) -> bool:
        """
        Exchanges money for unenriched fuel

        Parameters
        ----------
            amount: int
                amount of fuel to be purchased

        Returns
        -------
            bool
                returns false if user cannot buy fuel, returns true otherwise
        """
        if amount <= 0 or self.money < amount * self.fuel_price:
            return False
        self.money -= amount * self.fuel_price
        self.science_center.unenriched_fuel += amount
        return True

    def start_enrichment(self, fuel_amount:int=100) -> bool:
        """
        starts conversion of unusable unenriched fuel into usable enriched fuel

        Parameters
        ----------
            fuel_amount: int
                amount of fuel to be enriched

        Returns
        -------
            bool
                false if the enrichment cannot be started, true otherwise
        """
        if self.enrichment_in_progress:
            return False
        if fuel_amount <= 0 or fuel_amount > self.science_center.unenriched_fuel:
            return False

        centrifuge = self.science_center.centrifuge
        self.enrichment_duration = (centrifuge.time_per_fuel * fuel_amount) / 1 + fuel_amount*0.005 + centrifuge.speed_multiplier
        self.enrichment_elapsed = 0
        self.science_center.unenriched_fuel -= fuel_amount
        self.enrichment_in_progress = True
        return True

    def update_enrichment(self, elapsed_seconds:int|float):
        """
        updates the enrichment duration and stops it if time is up

        Parameters
        ----------
            elapsed_seconds: int|float
                time since last update

        Returns
        -------
            bool
                if enrichment is over return true, return false otherwise
        """
        if not self.enrichment_in_progress:
            return False

        self.enrichment_elapsed = min(self.enrichment_elapsed + elapsed_seconds, self.enrichment_duration)
        if self.enrichment_elapsed >= self.enrichment_duration:
            self.enrichment_in_progress = False
            return True
        return False

    def skip_enrichment(self):
        """
        checks if enrichment is going and if it is, skip the duration

        Returns
        -------
            bool
                returns false if enrichment is not happening, returns true otherwise
        """
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
        """
        purchases upgrades if user hasn't already purchased them and they have enough money

        Parameters
        ----------
            category_name: str
                category of upgrade to be purchased from
            upgrade_name: str
                name of the upgrade to be purchased

        Returns
        -------
            bool
                returns false if upgrade can't be purchased for whatever reason, returns true otherwise
        """
        upgrades = self.science_center.upgrades
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

    def get_center_status(self):
        """
        gets the center status of the centrifuge

        Returns
        -------
            dict
                collection of science center attributes
        """
        centre = self.science_center
        centrifuge = centre.centrifuge
        return {
            "enriched_fuel": centre.enriched_fuel,
            "unenriched_fuel": centre.unenriched_fuel,
            "speed_multiplier": centrifuge.speed_multiplier,
            "upgrades": centre.upgrades
        }

    def update_energy(self):
        """
        if the power plant is off, energy is set to 0. if it is on energy is calculated and set by a formula

        Returns
        -------

        """
        if not self.power_plant_on:
            self.energy_production = 0
        else:
            self.energy_production = 1000 * self.energy_production_multiplier * self.reactor.temperature * (1+10**(self.reactor.temperature/self.reactor.meltdown_temperature))

    def update_money(self, elapsed_seconds:int|float):
        """
        adds money based on current energy output and pay per watt for the current contract

        Parameters
        ----------
            elapsed_seconds: int|float
                time since last update

        Returns
        -------

        """
        try:
            if self.active_contract >= 0:
                self.money += round(self.energy_production * self.admin.contracts[self.active_contract]["pay_per_watt"] * elapsed_seconds, 2)
        except:
            print("No active contract")

    def update_current_contract(self, elapsed_seconds:int|float):
        """
        updates the contracts power required and pays out the money on completion after the power requirements are filled

        Parameters
        ----------
            elapsed_seconds: int
                time since last update

        Returns
        -------

        """
        if self.active_contract is not -1 and 0 <= self.active_contract < len(self.admin.contracts):
            self.admin.contracts[self.active_contract]["total_power_required"] = int(self.admin.contracts[self.active_contract]["total_power_required"]) - self.energy_production * elapsed_seconds
            if self.admin.contracts[self.active_contract]["total_power_required"] <= 0:
                self.money += self.admin.contracts[self.active_contract]["money_on_completion"]
                self.admin.contracts[self.active_contract]["total_power_required"] = 0
                self.active_contract = -1

    def update_temperature(self):
        """
        updates temperatures based on reactivity and whether the amount of enriched fuel is below the required amount for 100% efficiency

        Returns
        -------
            bool
                returns true if the reactor should auto scram
        """
        average_rod_depth = sum(self.reactor.rods) / self.reactor.num_rods
        reactivity = average_rod_depth / self.reactor.max_rod_depth
        self.reactor.temperature = (self.reactor.base_temperature + reactivity * self.reactor.heat_factor) * self.reactor.temperature_penalty
        if self.power_plant_on:
            self.reactor.temperature += random.uniform(-0.5, 0.5)
        if self.science_center.enriched_fuel < self.reactor.required_fuel:
            self.reactor.temperature_penalty = self.science_center.enriched_fuel/self.reactor.required_fuel
        elif self.reactor.temperature_penalty < 1:
            self.reactor.temperature_penalty = 1
        if self.reactor.temperature > self.reactor.auto_scram_temperature and self.reactor.auto_scram == True:
            return True
        return False

    def update_fuel(self, elapsed_seconds:int|float):
        """
        removes fuel depending on the time passed

        Parameters
        ----------
            elapsed_seconds: int
                time since last update

        Returns
        -------

        """
        self.science_center.enriched_fuel -= elapsed_seconds * self.science_center.fuel_usage_rate

    def get_status(self):
        """
        gets reactor status

        Returns
        -------
            dict
                collection of reactor attributes
        """
        return {
            'temperature': round(self.reactor.temperature, 1),
            'rods': self.reactor.rods.copy(),
            'average_rod_depth': round(sum(self.reactor.rods) / self.reactor.num_rods, 1),
            'current_rod': self.reactor.current_rod,
            'power_plant_on': self.power_plant_on,
            'energy_production': self.energy_production
        }

    def scram(self):
        """
        forcefully lowers all rods to their maximum depth to lower the reactor temperature

        Returns
        -------

        """
        print('Reactor temperature exceeded safe limits. Auto scram initiated')
        for i in range(len(self.reactor.rods)):
            self.lower_rod(i, self.reactor.max_rod_depth)
            self.scrammed_recently = True

    def change_power_plant_state(self):
        """
        toggles the power plant mode

        Returns
        -------
            bool
                whether the power plant mode is on
        """
        self.power_plant_on = not self.power_plant_on
        return self.power_plant_on

    def raise_rod(self, rod_index:int, raise_amount:int):
        """
        raise a rod to increase reactivity

        Parameters
        ----------
            rod_index: int
                the index of the rod to be raised
            raise_amount: int
                the amount the rod should be raised

        Returns
        -------

        """
        if 0 <= rod_index < self.reactor.num_rods:
            if self.reactor.rods[rod_index]+raise_amount <= self.reactor.max_rod_depth:
                self.reactor.rods[rod_index] += raise_amount
                self.update_temperature()
                print(f"Rod {rod_index} raised to depth {self.reactor.rods[rod_index]}")
            else:
                self.reactor.rods[rod_index] = self.reactor.max_rod_depth
                print(f"Rod {rod_index} raised to depth {self.reactor.max_rod_depth}")

    def lower_rod(self, rod_index:int, lower_amount:int):
        """
        lowers a rod to decrease reactivity

        Parameters
        ----------
            rod_index: int
                the index of the rod to be raised
            lower_amount: int
                the amount the rod should be raised

        Returns
        -------

        """
        if 0 <= rod_index < self.reactor.num_rods:
            if self.reactor.rods[rod_index]-lower_amount >= 0:
                self.reactor.rods[rod_index] -= lower_amount
                self.update_temperature()
                print(f"Rod {rod_index} lowered to depth {self.reactor.rods[rod_index]}")
            else:
                self.reactor.rods[rod_index] = 0
                print(f"Rod {rod_index} lowered to depth 0")

if __name__ == "__main__":
    reactor = Game()
    reactor.scram()