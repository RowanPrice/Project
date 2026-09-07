"""Grid-scale battery storage.

A 400 MWh lithium-iron-phosphate installation sitting between the generator
and the grid.  It exists for three reasons, all of them things a reactor is
bad at:

* **Speed.**  The reactor takes minutes to change output and hours to change
  it very much.  The battery is at full power in under a second, which is the
  only way to sell frequency response.
* **Arbitrage.**  Overnight prices go negative; the evening peak goes to
  several hundred pounds.  Charging at one and discharging at the other is
  free money, limited only by round-trip efficiency and how much you are
  willing to age the cells.
* **Cover.**  When the reactor trips, the battery can hold a contract up for
  the twenty minutes it takes to admit what has happened.

None of it is free.  Every joule makes a round trip at about 88% efficiency,
and every cycle takes a little capacity away permanently -- faster if you
charge hard, faster still if you run the pack near empty or near full.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Battery:
    #: Energy capacity when new, MWh.
    nominal_capacity_mwh: float = 400.0
    #: State of charge in MWh.
    charge_mwh: float = 200.0
    #: Maximum charge and discharge power, MW.
    max_power_mw: float = 200.0
    #: One-way efficiency; the round trip is the square of this.
    efficiency: float = 0.94
    #: Remaining fraction of the original capacity.
    health: float = 1.0
    #: Equivalent full cycles accumulated.
    cycles: float = 0.0
    #: Commanded power: positive discharges to the grid, negative charges.
    power_demand_mw: float = 0.0
    #: Actual power flowing, which ramps and is limited by state of charge.
    power_mw: float = 0.0
    #: When true the battery answers grid frequency automatically.
    frequency_response: bool = False
    #: Droop: MW of response per hertz of deviation.
    droop_mw_per_hz: float = 380.0
    #: Cumulative energy through the pack, MWh.
    throughput_mwh: float = 0.0
    installed: bool = True

    @property
    def capacity_mwh(self) -> float:
        return self.nominal_capacity_mwh * self.health

    @property
    def state_of_charge(self) -> float:
        if self.capacity_mwh <= 0:
            return 0.0
        return max(0.0, min(1.0, self.charge_mwh / self.capacity_mwh))

    def available_discharge_mw(self) -> float:
        """Power the pack could deliver right now."""
        if not self.installed or self.state_of_charge <= 0.02:
            return 0.0
        # Taper the last 10% so the pack does not simply fall off a cliff.
        taper = min(1.0, self.state_of_charge / 0.10)
        return self.max_power_mw * self.health * taper

    def available_charge_mw(self) -> float:
        if not self.installed or self.state_of_charge >= 0.99:
            return 0.0
        taper = min(1.0, (1.0 - self.state_of_charge) / 0.08)
        return self.max_power_mw * self.health * taper

    def step(self, dt: float, frequency: float = 50.0) -> float:
        """Advance the battery.  Returns net power to the grid in MW.

        Positive is a discharge (adding to the plant's output); negative is a
        charge (subtracting from it).
        """
        if not self.installed or dt <= 0:
            self.power_mw = 0.0
            return 0.0

        demand = self.power_demand_mw
        if self.frequency_response:
            # Droop response with a 15 mHz deadband, the way a real dynamic
            # containment unit behaves. Under-frequency means the system is
            # short, so the battery discharges.
            error = 50.0 - frequency
            if abs(error) > 0.015:
                demand += self.droop_mw_per_hz * error
        demand = max(-self.available_charge_mw(), min(demand, self.available_discharge_mw()))

        # The pack itself is effectively instantaneous; the inverter ramps in
        # a fraction of a second.
        ramp = self.max_power_mw * min(1.0, dt / 0.4)
        self.power_mw += max(-ramp, min(ramp, demand - self.power_mw))

        hours = dt / 3600.0
        if self.power_mw > 0:
            drawn = self.power_mw * hours / self.efficiency
            drawn = min(drawn, self.charge_mwh)
            self.charge_mwh -= drawn
            delivered = drawn * self.efficiency
            self.throughput_mwh += delivered
        elif self.power_mw < 0:
            taken = -self.power_mw * hours
            stored = taken * self.efficiency
            room = max(0.0, self.capacity_mwh - self.charge_mwh)
            stored = min(stored, room)
            self.charge_mwh += stored
            self.throughput_mwh += stored

        self._age(dt)
        return self.power_mw

    def _age(self, dt: float) -> None:
        if self.capacity_mwh <= 0:
            return
        hours = dt / 3600.0
        # Cycle ageing, worse at high C-rate and at the extremes of charge.
        c_rate = abs(self.power_mw) / max(self.capacity_mwh, 1.0)
        energy = abs(self.power_mw) * hours
        equivalent_cycles = energy / (2.0 * self.capacity_mwh)
        self.cycles += equivalent_cycles
        stress = 1.0 + 1.6 * c_rate
        soc = self.state_of_charge
        if soc > 0.85 or soc < 0.15:
            stress *= 1.35
        self.health = max(0.4, self.health - equivalent_cycles * 4.5e-5 * stress)
        # Calendar ageing: cells die of old age whether used or not.
        self.health = max(0.4, self.health - hours * 1.1e-6)

    def replacement_cost(self) -> float:
        """Cost to bring the pack back to new, GBP."""
        return (1.0 - self.health) * self.nominal_capacity_mwh * 165_000.0
