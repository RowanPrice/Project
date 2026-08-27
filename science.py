class Centrifuge:
    """Represents the uranium enrichment centrifuge"""
    def __init__(self):
        self.quality_level = 1  # Base quality level (max 10)
        self.speed_level = 1    # Base speed level (max 10)
        self.quality_cost = 500  # Cost to upgrade quality
        self.speed_cost = 300    # Cost to upgrade speed
        self.max_level = 10
        self.max_multiplier = 1.5
    
    def upgrade_quality(self):
        """Upgrade centrifuge quality to produce higher enrichment"""
        if self.quality_level >= self.max_level:
            print(f"Centrifuge quality is already at maximum level {self.max_level}")
            return 0
        self.quality_level += 1
        return self.quality_cost
    
    def upgrade_speed(self):
        """Upgrade centrifuge speed to enrich faster"""
        if self.speed_level >= self.max_level:
            print(f"Centrifuge speed is already at maximum level {self.max_level}")
            return 0
        self.speed_level += 1
        return self.speed_cost
    
    def get_enrichment_multiplier(self):
        """Quality multiplier for enrichment percentage"""
        multiplier = 1.0 + (self.quality_level - 1) * 0.1  # +10% per quality level
        return min(multiplier, self.max_multiplier)  # Cap at 1.5x
    
    def get_speed_multiplier(self):
        """Speed multiplier for enrichment time"""
        multiplier = 1.0 + (self.speed_level - 1) * 0.1  # +10% per speed level
        return min(multiplier, self.max_multiplier)  # Cap at 1.5x
    
    def get_status(self):
        """Get centrifuge status"""
        return {
            'quality_level': self.quality_level,
            'speed_level': self.speed_level,
            'enrichment_multiplier': round(self.get_enrichment_multiplier(), 2),
            'speed_multiplier': round(self.get_speed_multiplier(), 2)
        }


class ScienceCentre:
    def __init__(self):
        self.upgrades = {}  # Dict of {category: {upgrade_name: {'cost': int, 'effect': str, 'purchased': bool}}}
        self.nuclear_fuel = 0
        self.enrichment_level = 0.0
        self.centrifuge = Centrifuge()  # Single centrifuge
        
        # Initialize default upgrade categories and upgrades
        self._setup_default_upgrades()
    
    def _setup_default_upgrades(self):
        """Set up default upgrade categories and upgrades"""
        # Reactor Systems
        self.add_upgrade_category("Reactor Systems")
        self.add_upgrade("Reactor Systems", "Advanced Reactor", 5000, "Increases base heat factor by 20%")
        self.add_upgrade("Reactor Systems", "Backup Generators", 3000, "Prevents reactor shutdown during power loss")
        self.add_upgrade("Reactor Systems", "Safety Systems", 4000, "Reduces meltdown risk by 30%")
        
        # Cooling Systems
        self.add_upgrade_category("Cooling Systems")
        self.add_upgrade("Cooling Systems", "Enhanced Cooling", 2500, "Reduces core temperature by 50°C")
        self.add_upgrade("Cooling Systems", "Passive Cooling", 1500, "Slowly cools reactor when idle")
        self.add_upgrade("Cooling Systems", "Liquid Helium System", 6000, "Ultra-efficient cooling, -100°C")
        
        # Infrastructure
        self.add_upgrade_category("Infrastructure")
        self.add_upgrade("Infrastructure", "Security System", 4000, "Protects facility from sabotage")
        self.add_upgrade("Infrastructure", "Research Lab", 6000, "Enables advanced fuel research")
        self.add_upgrade("Infrastructure", "Control Room Upgrade", 3500, "Better monitoring capabilities")
        
        # Enrichment
        self.add_upgrade_category("Enrichment")
        self.add_upgrade("Enrichment", "Centrifuge Efficiency", 2000, "Improves centrifuge base efficiency")
        self.add_upgrade("Enrichment", "Advanced Filtration", 3500, "Better uranium separation")
        self.add_upgrade("Enrichment", "High-Speed Centrifuge", 5500, "Significantly faster enrichment")
    
    def add_upgrade_category(self, category_name):
        """Add a new upgrade category"""
        if category_name not in self.upgrades:
            self.upgrades[category_name] = {}
            return True
        return False
    
    def add_upgrade(self, category_name, upgrade_name, cost, effect):
        """Add an upgrade to a category"""
        if category_name not in self.upgrades:
            print(f"Category '{category_name}' does not exist. Create it first with add_upgrade_category()")
            return False
        
        if upgrade_name in self.upgrades[category_name]:
            print(f"Upgrade '{upgrade_name}' already exists in category '{category_name}'")
            return False
        
        if cost < 0:
            print("Cost cannot be negative")
            return False
        
        self.upgrades[category_name][upgrade_name] = {
            'cost': cost,
            'effect': effect,
            'purchased': False
        }
        return True
    
    def purchase_upgrade(self, category_name, upgrade_name):
        """Purchase an upgrade"""
        if category_name not in self.upgrades:
            print(f"Category '{category_name}' does not exist")
            return False
        
        if upgrade_name not in self.upgrades[category_name]:
            print(f"Upgrade '{upgrade_name}' not found in '{category_name}'")
            return False
        
        upgrade = self.upgrades[category_name][upgrade_name]
        
        if upgrade['purchased']:
            print(f"Upgrade '{upgrade_name}' has already been purchased")
            return False
        
        upgrade['purchased'] = True
        print(f"Purchased '{upgrade_name}' from '{category_name}' category for {upgrade['cost']} credits")
        print(f"Effect: {upgrade['effect']}")
        return True
    
    def upgrade_centrifuge_quality(self):
        """Upgrade the centrifuge's quality for higher enrichment"""
        cost = self.centrifuge.upgrade_quality()
        if cost > 0:
            print(f"Centrifuge quality upgraded to level {self.centrifuge.quality_level} (Cost: {cost})")
        return True
    
    def upgrade_centrifuge_speed(self):
        """Upgrade the centrifuge's speed for faster enrichment"""
        cost = self.centrifuge.upgrade_speed()
        if cost > 0:
            print(f"Centrifuge speed upgraded to level {self.centrifuge.speed_level} (Cost: {cost})")
        return True
    
    def nuclear_fuel_enrichment(self, fuel_amount, enrichment_percentage):
        """Enrich nuclear fuel using the centrifuge"""
        if fuel_amount < 0:
            print("Fuel amount cannot be negative")
            return False
        
        if not (0 <= enrichment_percentage <= 100):
            print("Enrichment percentage must be between 0 and 100")
            return False
        
        adjusted_enrichment = enrichment_percentage * self.centrifuge.get_enrichment_multiplier()
        adjusted_enrichment = min(adjusted_enrichment, 100)  # Cap at 100%
        
        self.nuclear_fuel += fuel_amount
        self.enrichment_level = adjusted_enrichment
        
        print(f"Enriched {fuel_amount} units to {adjusted_enrichment:.2f}% (base: {enrichment_percentage}%)")
        return True
    
    def get_centre_status(self):
        """Display current status of the science centre"""
        status = self.centrifuge.get_status()
        print(f"\n=== Science Centre Status ===")
        print(f"Nuclear Fuel: {self.nuclear_fuel} units")
        print(f"Current Enrichment Level: {self.enrichment_level:.2f}%")
        print(f"\nCentrifuge:")
        print(f"  Quality Level: {status['quality_level']} (Multiplier: {status['enrichment_multiplier']}x)")
        print(f"  Speed Level: {status['speed_level']} (Multiplier: {status['speed_multiplier']}x)")
        print(f"\nUpgrades by Category:")
        for category, upgrades_dict in self.upgrades.items():
            print(f"  {category}:")
            for upgrade_name, upgrade_info in upgrades_dict.items():
                status_str = "✓ Purchased" if upgrade_info['purchased'] else "Available"
                print(f"    - {upgrade_name}: {upgrade_info['cost']} credits [{status_str}]")
                print(f"      Effect: {upgrade_info['effect']}")


# Example usage
if __name__ == "__main__":
    centre = ScienceCentre()
    
    # Create upgrade categories
    centre.add_upgrade_category("Reactor Systems")
    centre.add_upgrade_category("Cooling Systems")
    centre.add_upgrade_category("Infrastructure")
    
    # Add upgrades to categories
    centre.add_upgrade("Reactor Systems", "Advanced Reactor", 5000, "Increases base heat factor by 20%")
    centre.add_upgrade("Reactor Systems", "Backup Generators", 3000, "Prevents reactor shutdown during power loss")
    
    centre.add_upgrade("Cooling Systems", "Enhanced Cooling", 2500, "Reduces core temperature by 50°C")
    centre.add_upgrade("Cooling Systems", "Passive Cooling", 1500, "Slowly cools reactor when idle")
    
    centre.add_upgrade("Infrastructure", "Security System", 4000, "Protects facility from sabotage")
    centre.add_upgrade("Infrastructure", "Research Lab", 6000, "Enables advanced fuel research")
    
    # Purchase some upgrades
    centre.purchase_upgrade("Reactor Systems", "Advanced Reactor")
    centre.purchase_upgrade("Cooling Systems", "Enhanced Cooling")
    
    # Enrich fuel
    centre.nuclear_fuel_enrichment(100, 85.5)
    
    # Upgrade centrifuge
    centre.upgrade_centrifuge_quality()
    centre.upgrade_centrifuge_speed()
    
    # Enrich again with upgraded centrifuge
    centre.nuclear_fuel_enrichment(50, 80.0)
    
    # Show status
    centre.get_centre_status()
