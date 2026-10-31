class Admin:
    def __init__(self):
        self.contracts = [
                    {
                        "title": "National Grid Supply",
                        "pay_per_watt": 0.08,
                        "total_power_required": 50000,
                        "money_on_completion": 10000,
                        "description": "Supply stable power to the national grid."
                    },
                    {
                        "title": "Industrial Power Agreement",
                        "pay_per_watt": 0.12,
                        "total_power_required": 80000,
                        "money_on_completion": 15000,
                        "description": "Provide reliable energy for a high-demand industrial site."
                    },
                    {
                        "title": "Emergency Reserve Contract",
                        "pay_per_watt": 0.18,
                        "total_power_required": 40000,
                        "money_on_completion": 8000,
                        "description": "Keep reserve capacity available for emergency demand."
                    },
                    {
                        "title": "Research Facility Supply",
                        "pay_per_watt": 0.15,
                        "total_power_required": 150000,
                        "money_on_completion": 20000,
                        "description": "Provide power to a cutting-edge research facility."
                    },
                    {
                        "title": "Dr Frankenstein's Laboratory",
                        "pay_per_watt": 0.50,
                        "total_power_required": 10000,
                        "money_on_completion": 5000,
                        "description": "Supply electricity to Dr Frankenstein's laboratory."
                    },
                    {
                        "title": "Larry's Lamps",
                        "pay_per_watt": 0.50,
                        "total_power_required": 70000,
                        "money_on_completion": 10000,
                        "description": "Supply electricity to a lamp shop."
                    }
                ]