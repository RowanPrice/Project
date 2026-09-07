"""Component wear, equipment faults, and the regulator.

Nothing in a power station stays new.  Pumps wear, steam generator tubes thin,
the condenser fouls, the turbine collects deposits.  Each component here has a
health that decays with use -- faster at high power, faster still if you skip
maintenance -- and a failure probability that rises as health falls.

Faults are not scripted.  Each one is a hazard rate evaluated every step, so
the reactor coolant pump that trips does so because its bearing was worn and
the dice went against you, not because the game decided it was time for a
plot point.  What you get in exchange for that honesty is that maintenance
genuinely pays for itself, and that no two runs go the same way.

The regulator is the other half.  It counts trips, safety system challenges,
frequency excursions and unplanned releases, and it inspects on a schedule you
do not control.  A poor inspection costs money; a very poor one costs you the
licence, which ends the run.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

DAY = 86400.0


@dataclass
class Component:
    key: str
    name: str
    #: 1.0 is new, 0.0 is failed.
    health: float = 1.0
    #: Health lost per day of operation at full duty.
    wear_per_day: float = 0.004
    #: Failure hazard per day at zero health.
    hazard_per_day: float = 0.55
    failed: bool = False
    repair_cost: float = 250_000.0
    repair_days: float = 1.0
    repairing_until: float | None = None
    #: True once condition monitoring has flagged it.
    warned: bool = False

    @property
    def under_repair(self) -> bool:
        return self.repairing_until is not None

    def hazard(self) -> float:
        """Probability of failure per day at the current health."""
        if self.failed or self.under_repair:
            return 0.0
        # Bathtub curve: negligible while healthy, steep once worn.
        margin = max(0.0, self.health)
        return self.hazard_per_day * (1.0 - margin) ** 3.2


@dataclass
class Maintenance:
    """The station's plant health, faults and regulatory standing."""

    components: dict[str, Component] = field(default_factory=dict)
    rng: random.Random = field(default_factory=random.Random)

    #: Regulatory record.
    trips: int = 0
    safety_challenges: int = 0
    violations: list[str] = field(default_factory=list)
    safety_score: float = 92.0
    next_inspection: float = 21.0 * DAY
    licence_revoked: bool = False

    def __post_init__(self) -> None:
        if self.components:
            return
        self.components = {
            component.key: component
            for component in (
                Component("rcp1", "Reactor Coolant Pump 1", wear_per_day=0.0045,
                          repair_cost=1_400_000, repair_days=2.5),
                Component("rcp2", "Reactor Coolant Pump 2", wear_per_day=0.0045,
                          repair_cost=1_400_000, repair_days=2.5),
                Component("rcp3", "Reactor Coolant Pump 3", wear_per_day=0.0045,
                          repair_cost=1_400_000, repair_days=2.5),
                Component("rcp4", "Reactor Coolant Pump 4", wear_per_day=0.0045,
                          repair_cost=1_400_000, repair_days=2.5),
                Component("sg_tubes", "Steam Generator Tubing", wear_per_day=0.0016,
                          hazard_per_day=0.30, repair_cost=6_800_000, repair_days=8.0),
                Component("turbine", "Main Turbine", wear_per_day=0.0028,
                          hazard_per_day=0.40, repair_cost=4_200_000, repair_days=6.0),
                Component("condenser", "Main Condenser", wear_per_day=0.0035,
                          hazard_per_day=0.45, repair_cost=1_900_000, repair_days=3.0),
                Component("feedwater", "Feedwater Pumps", wear_per_day=0.0040,
                          repair_cost=900_000, repair_days=1.5),
                Component("generator", "Main Generator", wear_per_day=0.0020,
                          hazard_per_day=0.35, repair_cost=5_600_000, repair_days=9.0),
                Component("offsite", "Offsite Power Supply", wear_per_day=0.0006,
                          hazard_per_day=0.22, repair_cost=0.0, repair_days=0.4),
            )
        }

    # -- wear -------------------------------------------------------------

    def step_wear(self, duty: float, dt: float, wear_modifier: float = 1.0,
                  now: float = 0.0, warn: bool = False) -> list[str]:
        """Age the plant.  ``duty`` is the fraction of rated output being made."""
        messages: list[str] = []
        days = dt / DAY
        for component in self.components.values():
            if component.repairing_until is not None:
                if now >= component.repairing_until:
                    component.repairing_until = None
                    component.failed = False
                    component.health = 1.0
                    component.warned = False
                    messages.append(f"{component.name} returned to service")
                continue
            if component.failed:
                continue
            load = 0.25 + 0.75 * max(0.0, min(duty, 1.2))
            component.health = max(
                0.0, component.health - component.wear_per_day * load * days * wear_modifier
            )
            if warn and not component.warned and component.health < 0.30:
                component.warned = True
                messages.append(
                    f"Condition monitoring: {component.name} degraded to "
                    f"{component.health * 100:.0f}% -- schedule maintenance"
                )
        return messages

    def roll_failures(self, dt: float, crew_skill: float = 0.0) -> list[Component]:
        """Evaluate every component's hazard and return whatever just broke."""
        days = dt / DAY
        broken: list[Component] = []
        for component in self.components.values():
            hazard = component.hazard() * (1.0 - 0.4 * crew_skill)
            if hazard <= 0:
                continue
            if self.rng.random() < hazard * days:
                component.failed = True
                broken.append(component)
        return broken

    def begin_repair(self, key: str, now: float) -> Component | None:
        component = self.components.get(key)
        if component is None or component.under_repair:
            return None
        component.repairing_until = now + component.repair_days * DAY
        return component

    def worst_component(self) -> Component:
        return min(self.components.values(), key=lambda c: c.health)

    # -- regulator --------------------------------------------------------

    def record_trip(self, reason: str) -> None:
        self.trips += 1
        self.safety_score = max(0.0, self.safety_score - 3.5)
        self.violations.append(reason)
        if len(self.violations) > 40:
            del self.violations[:-40]

    def record_challenge(self, reason: str, weight: float = 6.0) -> None:
        self.safety_challenges += 1
        self.safety_score = max(0.0, self.safety_score - weight)
        self.violations.append(reason)
        if len(self.violations) > 40:
            del self.violations[:-40]

    def recover(self, dt: float, bonus: float = 0.0) -> None:
        """Safety standing slowly recovers with uneventful operation."""
        self.safety_score = min(100.0, self.safety_score + (0.55 + bonus * 0.05) * dt / DAY)

    def inspect(self, now: float) -> tuple[str, float, str]:
        """Run a regulatory inspection.  Returns (grade, fine, narrative)."""
        self.next_inspection = now + self.rng.uniform(16.0, 30.0) * DAY
        score = self.safety_score
        worst = self.worst_component()
        if score >= 85:
            return ("Green", 0.0,
                    "Inspection closed with no findings. The regulator notes the "
                    "plant is being run the way it was designed to be run.")
        if score >= 70:
            return ("White", 120_000.0,
                    f"Minor findings. {worst.name} is at {worst.health * 100:.0f}% "
                    "and the inspector would like to know when you plan to do "
                    "something about it.")
        if score >= 50:
            return ("Yellow", 850_000.0,
                    "Substantive findings. Increased oversight, an enforcement "
                    "notice, and a fine. Further degradation will not be treated "
                    "sympathetically.")
        if score >= 30:
            return ("Red", 3_400_000.0,
                    "Serious findings across multiple areas. The plant is placed "
                    "under special measures and a substantial penalty is imposed.")
        self.licence_revoked = True
        return ("Licence revoked", 0.0,
                "The nuclear site licence is withdrawn with immediate effect. "
                "The reactor is ordered to cold shutdown and the station will not "
                "restart.")
