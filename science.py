class Centrifuge:
    def __init__(self):
        self.quality_level = 1
        self.speed_level = 1
        self.quality_cost = 500
        self.speed_cost = 300
        self.max_level = 10
        self.max_multiplier = 1.5


class ScienceCentre:
    def __init__(self):
        self.upgrades = {
            "Reactor Systems": {
                "Advanced Reactor": {"cost": 5000, "effect": "Increases base heat factor by 20%", "purchased": False},
                "Backup Generators": {"cost": 3000, "effect": "Prevents reactor shutdown during power loss", "purchased": False},
                "Safety Systems": {"cost": 4000, "effect": "Reduces meltdown risk by 30%", "purchased": False}
            },
            "Cooling Systems": {
                "Enhanced Cooling": {"cost": 2500, "effect": "Reduces core temperature by 50°C", "purchased": False},
                "Passive Cooling": {"cost": 1500, "effect": "Slowly cools reactor when idle", "purchased": False},
                "Liquid Helium System": {"cost": 6000, "effect": "Ultra-efficient cooling, -100°C", "purchased": False}
            },
            "Infrastructure": {
                "Security System": {"cost": 4000, "effect": "Protects facility from sabotage", "purchased": False},
                "Research Lab": {"cost": 6000, "effect": "Enables advanced fuel research", "purchased": False},
                "Control Room Upgrade": {"cost": 3500, "effect": "Better monitoring capabilities", "purchased": False}
            },
            "Enrichment": {
                "Centrifuge Efficiency": {"cost": 2000, "effect": "Improves centrifuge base efficiency", "purchased": False},
                "Advanced Filtration": {"cost": 3500, "effect": "Better uranium separation", "purchased": False},
                "High-Speed Centrifuge": {"cost": 5500, "effect": "Significantly faster enrichment", "purchased": False}
            }
        }
        self.enriched_fuel = 0
        self.unenriched_fuel = 0
        self.enrichment_level = 0.0
        self.centrifuge = Centrifuge()