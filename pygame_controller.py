from nuclear import Reactor
import random
import time

class Game:
    def __init__(self):
        self.game = Reactor()

    def update_temperature(self):
        """Update core temperature based on average rod position"""
        average_rod_depth = sum(self.game.rods) / self.game.num_rods
        reactivity = average_rod_depth / self.game.max_rod_depth
        self.game.temperature = self.game.base_temperature + reactivity * self.game.heat_factor
        self.game.temperature += random.uniform(-5, 5)
        if self.game.temperature > self.game.auto_scram_temperature and self.game.auto_scram == True:
            return(True)

    def get_status(self):
        return {
            'temperature': round(self.game.temperature, 1),
            'rods': self.game.rods.copy(),
            'average_rod_depth': round(sum(self.game.rods) / self.game.num_rods, 1)
        }

    def auto_scram(self):
        print('Reactor temperature exceeded safe limits. Auto scram initiated')
        time.sleep(1)
        for i in self.game.rods:
            self.lower_rod(i, self.game.max_rod_depth)

    def raise_rod(self, rod_index, raise_amount):
        """Raise a rod to increase reactivity"""
        if 0 <= rod_index < self.game.num_rods:
            if self.game.rods[rod_index]+raise_amount <= self.game.max_rod_depth:
                self.game.rods[rod_index] += raise_amount
                self.update_temperature()
                print(f"Rod {rod_index} raised to depth {self.game.rods[rod_index]}")
            else:
                self.game.rods[rod_index] = self.game.max_rod_depth
                print(f"Rod {rod_index} raised to depth {self.game.max_rod_depth}")

    def lower_rod(self, rod_index, lower_amount):
        """Lower a rod to decrease reactivity"""
        if 0 <= rod_index and rod_index < self.game.num_rods:
            if self.game.rods[rod_index]-lower_amount >= 0:
                self.game.rods[rod_index] -= lower_amount
                self.update_temperature()
                print(f"Rod {rod_index} lowered to depth {self.game.rods[rod_index]}")
            else:
                self.game.rods[rod_index] = 0
                print(f"Rod {rod_index} lowered to depth 0")

if __name__ == "__main__":
    game = Game()
    game.auto_scram()