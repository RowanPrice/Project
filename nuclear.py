import time
import random
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame
from pygame.locals import (
    K_0,
    K_1,
    K_2,
    K_3,
    K_4,
    K_5,
    K_6,
    K_7,
    K_8,
    K_9,
    K_UP,
    K_DOWN,
    KEYDOWN,
    QUIT,
)


class Reactor:
    def __init__(self, initial_temperature=20, num_rods=5, max_rod_depth=100, auto_scram_temperature=1000 , auto_scram=True, cold_shutdown_temperature=93, meltdown_temperature=2700):
        pygame.init()
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

    def raise_rod(self, rod_index, raise_amount):
        """Raise a rod to increase reactivity"""
        if 0 <= rod_index < self.num_rods:
            if self.rods[rod_index]+raise_amount <= self.max_rod_depth:
                self.rods[rod_index] += raise_amount
                self.update_temperature()
                print(f"Rod {rod_index} raised to depth {self.rods[rod_index]}")
            else:
                self.rods[rod_index] = self.max_rod_depth
                print(f"Rod {rod_index} raised to depth {self.max_rod_depth}")

    def lower_rod(self, rod_index, lower_amount):
        """Lower a rod to decrease reactivity"""
        if 0 <= rod_index and rod_index < self.num_rods:
            if self.rods[rod_index]-lower_amount >= 0:
                self.rods[rod_index] -= lower_amount
                self.update_temperature()
                print(f"Rod {rod_index} lowered to depth {self.rods[rod_index]}")
            else:
                self.rods[rod_index] = 0
                print(f"Rod {rod_index} lowered to depth 0")



    def update_temperature(self):
        """Update core temperature based on average rod position"""
        average_rod_depth = sum(self.rods) / self.num_rods
        reactivity = average_rod_depth / self.max_rod_depth
        self.temperature = self.base_temperature + reactivity * self.heat_factor
        self.temperature += random.uniform(-5, 5)
        if self.temperature > self.auto_scram_temperature and self.auto_scram == True:
            return(True)

    def get_status(self):
        return {
            'temperature': round(self.temperature, 1),
            'rods': self.rods.copy(),
            'average_rod_depth': round(sum(self.rods) / self.num_rods, 1)
        }

    def auto_scram(self):
        print('Reactor temperature exceeded safe limits. Auto scram initiated')
        time.sleep(1)
        for i in self.rods:
            reactor.lower_rod(i, self.max_rod_depth)

    def run_simulation(self, duration_seconds=10):
        current_rod = 0
        print("Starting reactor simulation...")
        start_time = time.time()
        while time.time() - start_time < duration_seconds:
            self.update_temperature()
            if self.update_temperature():
                self.auto_scram()
                break
            status = self.get_status()
            print(f"Temperature: {status['temperature']}°C, Average rod depth: {status['average_rod_depth']}")
            time.sleep(1)
            for event in pygame.event.get():
                if event.type == KEYDOWN and event.key in [K_0, K_1, K_2, K_3, K_4, K_5, K_6, K_7, K_8, K_9]:
                    for key in [K_0, K_1, K_2, K_3, K_4, K_5, K_6, K_7, K_8, K_9]:
                        if key == event.key:
                            current_rod = key
                #if event.type == KEYDOWN and event.key == K_0:
                 #   current_rod = 0
                #elif event.type == KEYDOWN and event.key == K_1:
                #    current_rod = 1
                #elif event.type == KEYDOWN and event.key == K_2:
                #    current_rod = 2
                #elif event.type == KEYDOWN and event.key == K_3:
                #    current_rod = 3
                #elif event.type == KEYDOWN and event.key == K_4:
                #    current_rod = 4
                #elif event.type == KEYDOWN and event.key == K_5:
                #    current_rod = 5
                elif event.type == KEYDOWN and event.key == K_UP:
                    reactor.raise_rod(current_rod, 10)
                elif event.type == KEYDOWN and event.key == K_DOWN:
                    reactor.raise_rod(current_rod, -10)



        print("Simulation ended.")

if __name__ == "__main__":
    reactor = Reactor()
    print("Initial status:", reactor.get_status())
    
    reactor.raise_rod(0, 100)
    reactor.raise_rod(1, 100)
    reactor.raise_rod(2, 100)
    reactor.raise_rod(3, 100)
    reactor.raise_rod(4, 101)
    #reactor.lower_rod(2, 1000)

    print("After raising rods:", reactor.get_status())
    
    reactor.run_simulation(7)
