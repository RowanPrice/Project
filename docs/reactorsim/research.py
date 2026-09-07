"""Fuel supply, enrichment, and the plant improvement programme.

Two things live here.

**Enrichment**, done properly.  Natural uranium is 0.711% U-235 and a PWR
wants around 4.5%, and the work required to make the change is measured in
separative work units.  The SWU function is

    V(x) = (2x - 1) ln( x / (1 - x) )

and the separative work needed to make one kilogram of product at assay xp,
from feed at xf, throwing away tails at xw, is

    SWU/kg = V(xp) + (F/P - 1) V(xw) - (F/P) V(xf),  F/P = (xp - xw)/(xf - xw)

Both terms matter to the player.  Push the tails assay down and each kilogram
of product needs less natural uranium but far more separative work; let the
tails rise and you burn through feed instead.  Uranium and SWU have separate
prices that move independently, so the optimum moves, and choosing it is a
real decision rather than a slider.

**Upgrades**, which change the physics rather than describing it.  Every entry
in the catalogue writes into a modifier dictionary that the rest of the
simulation reads: buying better steam generators genuinely raises the heat
transfer coefficient in ``thermal.py``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


def swu_value(assay_fraction: float) -> float:
    """The separative potential function V(x).  ``assay_fraction`` is 0-1."""
    x = min(max(assay_fraction, 1e-6), 1.0 - 1e-6)
    return (2.0 * x - 1.0) * math.log(x / (1.0 - x))


def enrichment_requirements(
    product_kg: float,
    product_assay: float,
    feed_assay: float = 0.711,
    tails_assay: float = 0.25,
) -> tuple[float, float]:
    """Return ``(feed_kg, swu)`` needed to produce ``product_kg`` of fuel.

    Assays are in weight percent.
    """
    xp = product_assay / 100.0
    xf = feed_assay / 100.0
    xw = tails_assay / 100.0
    if not (xw < xf < xp < 1.0):
        raise ValueError("require tails < feed < product")
    feed_ratio = (xp - xw) / (xf - xw)
    swu_per_kg = (
        swu_value(xp)
        + (feed_ratio - 1.0) * swu_value(xw)
        - feed_ratio * swu_value(xf)
    )
    return product_kg * feed_ratio, product_kg * swu_per_kg


@dataclass
class Upgrade:
    key: str
    category: str
    name: str
    cost: float
    description: str
    #: Modifier keys and the values they contribute.
    effects: dict[str, float] = field(default_factory=dict)
    #: Upgrades that must be bought first.
    requires: tuple[str, ...] = ()
    purchased: bool = False
    #: Days of engineering work before the benefit arrives.
    install_days: float = 0.0
    installing_until: float | None = None

    @property
    def installed(self) -> bool:
        return self.purchased and self.installing_until is None


UPGRADE_CATALOGUE: tuple[Upgrade, ...] = (
    # -- Reactor -----------------------------------------------------------
    Upgrade(
        key="rod_drives",
        category="Reactor",
        name="High-Speed Rod Drives",
        cost=1_400_000,
        description=(
            "Replaces the drive motors so the control banks move at 3.8% per "
            "second instead of 2.4%. Faster reactivity control, and a faster "
            "way to make a mistake."
        ),
        effects={"rod_speed": 1.6},
        install_days=2.0,
    ),
    Upgrade(
        key="auto_rod_control",
        category="Reactor",
        name="Automatic Rod Control",
        cost=2_600_000,
        description=(
            "Closes the loop between coolant average temperature and the "
            "control banks, so the reactor holds its temperature programme "
            "without a hand on the switch."
        ),
        effects={"auto_rod_control": 1.0},
        install_days=3.0,
    ),
    Upgrade(
        key="flux_mapping",
        category="Reactor",
        name="Incore Flux Mapping",
        cost=1_900_000,
        description=(
            "A movable detector system and the software to read it. Shows the "
            "projected xenon curve nine hours ahead, which is the difference "
            "between planning a power reduction and regretting one."
        ),
        effects={"xenon_forecast": 1.0},
        install_days=2.0,
    ),
    Upgrade(
        key="grey_rods",
        category="Reactor",
        name="Grey Control Rods",
        cost=4_200_000,
        description=(
            "Low-worth stainless banks for load following. Halves the "
            "differential worth of the control group, making fine power "
            "control possible without pushing boron around."
        ),
        effects={"rod_worth_fine": 0.55},
        requires=("auto_rod_control",),
        install_days=6.0,
    ),
    Upgrade(
        key="burnable_poison",
        category="Reactor",
        name="Integral Burnable Absorbers",
        cost=5_800_000,
        description=(
            "Gadolinia mixed into the fuel pellets holds down beginning-of-cycle "
            "excess reactivity without soluble boron, which buys back a much "
            "more negative moderator coefficient."
        ),
        effects={"boron_offset": -320.0},
        install_days=0.0,
    ),

    # -- Thermal -----------------------------------------------------------
    Upgrade(
        key="sg_retube",
        category="Thermal",
        name="Steam Generator Retube",
        cost=7_500_000,
        description=(
            "New Inconel 690 tube bundles. Raises steam generator heat transfer "
            "by 12% and resets tube degradation to zero."
        ),
        effects={"sg_htc": 1.12, "sg_repair": 1.0},
        install_days=9.0,
    ),
    Upgrade(
        key="turbine_blades",
        category="Thermal",
        name="Advanced Turbine Blading",
        cost=6_400_000,
        description=(
            "Three-dimensional last-stage blades and improved moisture "
            "separation. Two points of cycle efficiency, which on this plant is "
            "70 MW you were previously throwing into the sea."
        ),
        effects={"cycle_efficiency": 1.06},
        install_days=12.0,
    ),
    Upgrade(
        key="steam_dumps",
        category="Thermal",
        name="Enlarged Steam Dumps",
        cost=2_100_000,
        description=(
            "Doubles condenser dump capacity so a turbine trip no longer has to "
            "become a reactor trip."
        ),
        effects={"dump_capacity": 1.9},
        install_days=4.0,
    ),
    Upgrade(
        key="passive_cooling",
        category="Thermal",
        name="Passive Residual Heat Removal",
        cost=11_000_000,
        description=(
            "An elevated tank and a natural circulation loop that removes decay "
            "heat with no pumps, no power and no operator. The single best "
            "insurance policy against a station blackout that money can buy."
        ),
        effects={"passive_cooling": 1.0},
        install_days=18.0,
    ),

    # -- Electrical --------------------------------------------------------
    Upgrade(
        key="diesels",
        category="Electrical",
        name="Third Emergency Diesel",
        cost=3_300_000,
        description=(
            "A third independent standby generator. Raises the probability that "
            "something starts when the grid disappears from 92% to 99.5%."
        ),
        effects={"diesel_reliability": 0.075},
        install_days=5.0,
    ),
    Upgrade(
        key="battery_expansion",
        category="Electrical",
        name="Storage Expansion",
        cost=9_000_000,
        description=(
            "Another 300 MWh and 120 MW of inverters. More arbitrage, more "
            "frequency response, more cover when the reactor is not there."
        ),
        effects={"battery_capacity": 300.0, "battery_power": 120.0},
        install_days=8.0,
    ),
    Upgrade(
        key="grid_ramp",
        category="Electrical",
        name="Grid Code Exemption",
        cost=2_800_000,
        description=(
            "Instrumentation and a case to the system operator that lets this "
            "plant ramp at 110 MW per minute instead of 55."
        ),
        effects={"ramp_limit": 2.0},
        requires=("auto_rod_control",),
        install_days=1.0,
    ),

    # -- Enrichment --------------------------------------------------------
    Upgrade(
        key="cascade_stages",
        category="Enrichment",
        name="Additional Cascade Stages",
        cost=3_600_000,
        description=(
            "More centrifuges in series. Cuts the separative work needed per "
            "kilogram of product by 15%."
        ),
        effects={"swu_efficiency": 0.85},
        install_days=6.0,
    ),
    Upgrade(
        key="carbon_rotors",
        category="Enrichment",
        name="Carbon Fibre Rotors",
        cost=5_200_000,
        description=(
            "Higher peripheral speed raises separation per machine sharply -- "
            "separative power goes as the fourth power of rotor velocity. "
            "Enrichment runs 60% faster."
        ),
        effects={"enrichment_speed": 1.6},
        requires=("cascade_stages",),
        install_days=10.0,
    ),
    Upgrade(
        key="tails_reprocessing",
        category="Enrichment",
        name="Tails Re-enrichment",
        cost=4_400_000,
        description=(
            "Runs depleted tails back through the cascade, letting you operate "
            "at a 0.15% tails assay economically and cutting feed uranium by a "
            "quarter."
        ),
        effects={"tails_floor": -0.10},
        requires=("cascade_stages",),
        install_days=7.0,
    ),

    # -- Organisation ------------------------------------------------------
    Upgrade(
        key="simulator",
        category="Organisation",
        name="Full-Scope Training Simulator",
        cost=4_800_000,
        description=(
            "A replica control room. Crews who have already seen the transient "
            "handle it better: reduces the chance of an equipment fault "
            "escalating and softens the regulator's view of the ones that do."
        ),
        effects={"crew_skill": 0.35},
        install_days=14.0,
    ),
    Upgrade(
        key="maintenance",
        category="Organisation",
        name="Condition-Based Maintenance",
        cost=3_900_000,
        description=(
            "Vibration and oil analysis on every rotating machine. Components "
            "wear 35% more slowly and warn you before they fail."
        ),
        effects={"wear_rate": 0.65, "fault_warning": 1.0},
        install_days=6.0,
    ),
    Upgrade(
        key="fuel_contract",
        category="Organisation",
        name="Long-Term Uranium Contract",
        cost=2_400_000,
        description=(
            "Locks the feed uranium price against the spot market. Removes the "
            "worst of the volatility from the fuel bill."
        ),
        effects={"uranium_hedge": 1.0},
        install_days=0.0,
    ),
    Upgrade(
        key="control_room",
        category="Organisation",
        name="Control Room Modernisation",
        cost=5_100_000,
        description=(
            "Computerised procedures and a safety parameter display. Adds a "
            "predicted-trip warning before the protection system acts, and "
            "improves the regulator's assessment of the plant."
        ),
        effects={"trip_warning": 1.0, "safety_bonus": 8.0},
        install_days=11.0,
    ),
)


@dataclass
class FuelMarket:
    """Prices for natural uranium and separative work, which move on their own."""

    uranium_price: float = 128.0     # GBP per kg of natural U
    swu_price: float = 92.0          # GBP per SWU
    conversion_price: float = 14.0   # GBP per kg U, UF6 conversion
    fabrication_price: float = 240.0 # GBP per kg of finished fuel
    hedged: bool = False
    _phase: float = 0.0

    def step(self, dt: float, rng: random.Random) -> None:
        self._phase += dt
        drift = math.sin(self._phase / (11.0 * 86400.0)) * 0.16
        shock = rng.gauss(0.0, 0.0006) * math.sqrt(max(dt, 1.0))
        if not self.hedged:
            self.uranium_price *= 1.0 + shock + drift * dt / 86400.0 * 0.02
            self.uranium_price = max(70.0, min(self.uranium_price, 320.0))
        self.swu_price *= 1.0 + rng.gauss(0.0, 0.0004) * math.sqrt(max(dt, 1.0))
        self.swu_price = max(55.0, min(self.swu_price, 210.0))

    def quote(
        self,
        product_kg: float,
        product_assay: float,
        tails_assay: float,
        swu_efficiency: float = 1.0,
    ) -> dict:
        feed_kg, swu = enrichment_requirements(
            product_kg, product_assay, tails_assay=tails_assay
        )
        swu *= swu_efficiency
        uranium_cost = feed_kg * self.uranium_price
        conversion_cost = feed_kg * self.conversion_price
        swu_cost = swu * self.swu_price
        fabrication_cost = product_kg * self.fabrication_price
        return {
            "feed_kg": feed_kg,
            "swu": swu,
            "uranium_cost": uranium_cost,
            "conversion_cost": conversion_cost,
            "swu_cost": swu_cost,
            "fabrication_cost": fabrication_cost,
            "total": uranium_cost + conversion_cost + swu_cost + fabrication_cost,
            "cost_per_kg": (uranium_cost + conversion_cost + swu_cost + fabrication_cost)
            / max(product_kg, 1e-6),
        }


@dataclass
class ResearchProgramme:
    """Purchased upgrades and the modifier dictionary they produce."""

    upgrades: dict[str, Upgrade] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.upgrades:
            self.upgrades = {
                upgrade.key: Upgrade(**{**upgrade.__dict__})
                for upgrade in UPGRADE_CATALOGUE
            }

    def available(self) -> list[Upgrade]:
        return [
            upgrade
            for upgrade in self.upgrades.values()
            if not upgrade.purchased
            and all(self.upgrades[key].installed for key in upgrade.requires)
        ]

    def purchase(self, key: str, now: float) -> Upgrade | None:
        upgrade = self.upgrades.get(key)
        if upgrade is None or upgrade.purchased:
            return None
        if not all(self.upgrades[dep].installed for dep in upgrade.requires):
            return None
        upgrade.purchased = True
        if upgrade.install_days > 0:
            upgrade.installing_until = now + upgrade.install_days * 86400.0
        return upgrade

    def step(self, now: float) -> list[Upgrade]:
        """Complete any installations that are due.  Returns the finished ones."""
        finished = []
        for upgrade in self.upgrades.values():
            if upgrade.installing_until is not None and now >= upgrade.installing_until:
                upgrade.installing_until = None
                finished.append(upgrade)
        return finished

    @property
    def modifiers(self) -> dict[str, float]:
        """Combined effect of everything installed.

        Multiplicative effects (those whose default is 1.0) multiply; additive
        effects sum.  The distinction is by key, and the defaults live in
        ``DEFAULT_MODIFIERS``.
        """
        result = dict(DEFAULT_MODIFIERS)
        for upgrade in self.upgrades.values():
            if not upgrade.installed:
                continue
            for key, value in upgrade.effects.items():
                if key in MULTIPLICATIVE:
                    result[key] = result.get(key, 1.0) * value
                else:
                    result[key] = result.get(key, 0.0) + value
        return result


MULTIPLICATIVE = {
    "rod_speed", "sg_htc", "cycle_efficiency", "dump_capacity",
    "swu_efficiency", "enrichment_speed", "wear_rate", "ramp_limit",
    "rod_worth_fine",
}

DEFAULT_MODIFIERS: dict[str, float] = {
    "rod_speed": 1.0,
    "sg_htc": 1.0,
    "cycle_efficiency": 1.0,
    "dump_capacity": 1.0,
    "swu_efficiency": 1.0,
    "enrichment_speed": 1.0,
    "wear_rate": 1.0,
    "ramp_limit": 1.0,
    "rod_worth_fine": 1.0,
    "auto_rod_control": 0.0,
    "xenon_forecast": 0.0,
    "boron_offset": 0.0,
    "passive_cooling": 0.0,
    "diesel_reliability": 0.0,
    "battery_capacity": 0.0,
    "battery_power": 0.0,
    "crew_skill": 0.0,
    "fault_warning": 0.0,
    "trip_warning": 0.0,
    "safety_bonus": 0.0,
    "tails_floor": 0.0,
    "uranium_hedge": 0.0,
    "sg_repair": 0.0,
}
