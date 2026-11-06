class Centrifuge:
    def __init__(self):
        self.time_per_fuel = 1.2
        self.speed_multiplier = 0

class ScienceCenter:
    def __init__(self):
        self.upgrades = {
            "Reactor Systems": {
                "Advanced Reactor": {"cost": 1, "effect": "Increases base heat factor by 20%", "purchased": False},
                "Backup Generators": {"cost": 1, "effect": "Fuel lasts longer", "purchased": False},
            },
            "Energy Systems": {
                "Improved Turbines": {"cost": 1, "effect": "Increases energy production by 10%", "purchased": False},
                "Passive Cooling": {"cost": 1, "effect": "Slowly cools reactor when idle", "purchased": False},
                "Liquid Helium System": {"cost": 1, "effect": "reduces temperature by 100°C", "purchased": False}
            },
            "Contract Systems": {
                "Increased Reputation": {"cost": 1, "effect": "Better paying contracts are more likely to appear", "purchased": False},
                "Grateful Companies": {"cost": 1, "effect": "Payment on contract completion increased by 15%", "purchased": False},
                "Better connections": {"cost": 1, "effect": "Better paying contracts are more likely to appear", "purchased": False}
            },
            "Hiring Systems": {
                "Enhanced Cooling": {"cost": 1, "effect": "Reduces core temperature by 50°C", "purchased": False},
                "Passive Cooling": {"cost": 1, "effect": "Slowly cools reactor when idle", "purchased": False},
                "Liquid Helium System": {"cost": 1, "effect": "reduces temperature by 100°C", "purchased": False}
            },
            "Safety Systems": {
                "Better control rods": {"cost": 1, "effect": "Control rods lower temperature faster", "purchased": False},
                "Stronger Heat Containment": {"cost": 1, "effect": "Slightly increases the meltdown temperature", "purchased": False},
                "Auto Scram System": {"cost": 1, "effect": "Automatically lowers the control rods when you would otherwise meltdown", "purchased": False}
            },
            "Battery Systems": {
                "More Capacitors": {"cost": 1, "effect": "Charge and discharge speed increased", "purchased": False},
                "Battery Slider": {"cost": 1, "effect": "Allow percentage slider for charging/discharging", "purchased": False},
                "Burst Discharge": {"cost": 1,"effect": "A", "purchased": False}
            },
            "Enrichment Systems": {
                "Centrifuge Efficiency": {"cost": 1, "effect": "Improves centrifuge speed", "purchased": False},
                "Advanced Filtration": {"cost": 1, "effect": "More enriched fuel is produced", "purchased": False},
                "High-Speed Centrifuge": {"cost": 1, "effect": "Significantly faster enrichment", "purchased": False},
                "Light-Speed Centrifuge": {"cost": 1, "effect": "Enrichment is instant", "purchased": False}
            }
        }
        self.enriched_fuel = 0
        self.unenriched_fuel = 100
        self.centrifuge = Centrifuge()