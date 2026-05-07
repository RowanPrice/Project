import time
import random

class Reactor:
    def __init__(self, initial_temperature=20, num_rods=5, max_rod_depth=100):
        self.temperature = initial_temperature
        self.rods = [0] * num_rods  # 0 = fully inserted, max_rod_depth = fully withdrawn
        self.max_rod_depth = max_rod_depth
        self.num_rods = num_rods
        self.base_temperature = initial_temperature
        self.heat_factor = 500  # How much temperature increases per unit of rod withdrawal

    def raise_rod(self, rod_index):
        """Raise (withdraw) a control rod to increase reactivity"""
        if 0 <= rod_index < self.num_rods:
            if self.rods[rod_index] < self.max_rod_depth:
                self.rods[rod_index] += 10
                self.update_temperature()
                print(f"Rod {rod_index} raised to depth {self.rods[rod_index]}")

    def lower_rod(self, rod_index):
        """Lower (insert) a control rod to decrease reactivity"""
        if 0 <= rod_index < self.num_rods:
            if self.rods[rod_index] > 0:
                self.rods[rod_index] -= 10
                self.update_temperature()
                print(f"Rod {rod_index} lowered to depth {self.rods[rod_index]}")

    def update_temperature(self):
        """Update core temperature based on average rod position"""
        average_rod_depth = sum(self.rods) / self.num_rods
        reactivity = average_rod_depth / self.max_rod_depth
        self.temperature = self.base_temperature + reactivity * self.heat_factor
        self.temperature += random.uniform(-5, 5)

    def get_status(self):
        """Get current reactor status"""
        return {
            'temperature': round(self.temperature, 1),
            'rods': self.rods.copy(),
            'average_rod_depth': round(sum(self.rods) / self.num_rods, 1)
        }

    def run_simulation(self, duration_seconds=10):
        print("Starting reactor simulation...")
        start_time = time.time()
        while time.time() - start_time < duration_seconds:
            self.update_temperature()
            status = self.get_status()
            print(f"Temperature: {status['temperature']}°C, Average rod depth: {status['average_rod_depth']}")
            time.sleep(1)
        print("Simulation ended.")

# Example usage
if __name__ == "__main__":
    reactor = Reactor()
    print("Initial status:", reactor.get_status())
    
    # Raise some rods
    reactor.raise_rod(0)
    reactor.raise_rod(1)
    print("After raising rods:", reactor.get_status())
    
    # Run a short simulation
    reactor.run_simulation(5)
