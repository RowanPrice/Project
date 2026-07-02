from nuclear import Reactor
import random
import time

class Game:
    def __init__(self):
        self.reactor = Reactor()

    def update_temperature(self):
        """Update core temperature based on average rod position"""
        average_rod_depth = sum(self.reactor.rods) / self.reactor.num_rods
        reactivity = average_rod_depth / self.reactor.max_rod_depth
        self.reactor.temperature = self.reactor.base_temperature + reactivity * self.reactor.heat_factor
        self.reactor.temperature += random.uniform(-5, 5)
        if self.reactor.temperature > self.reactor.auto_scram_temperature and self.reactor.auto_scram == True:
            return(True)

    def get_status(self):
        return {
            'temperature': round(self.reactor.temperature, 1),
            'rods': self.reactor.rods.copy(),
            'average_rod_depth': round(sum(self.reactor.rods) / self.reactor.num_rods, 1)
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