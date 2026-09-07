"""The reactor plant: physics, chemistry, protection system and damage model.

This module wires the neutronics, thermal hydraulics and rod drives together
into one machine, adds the reactivity balance that couples them, and puts a
reactor protection system on top that will trip the plant whether or not the
operator agrees.

The reactivity balance is the heart of it::

    rho_total = rho_fuel        excess reactivity of the fuel, falling with burnup
              + rho_rods        control and shutdown banks, S-curve worth
              + rho_boron       soluble boron in the coolant
              + rho_doppler     fuel temperature, always negative, instantaneous
              + rho_moderator   coolant temperature, sign depends on boron
              + rho_void        steam in the core, strongly negative
              + rho_xenon       Xe-135, up to -2700 pcm and slow
              + rho_samarium    Sm-149, small and permanent

Every one of those terms fights the operator in a different timescale, from
microseconds (Doppler) to days (samarium), and the game is in the interaction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import constants as C
from .neutronics import FissionProducts, FuelState, PointKinetics, inhour_period
from .rods import RodController
from .thermal import (
    PrimaryCircuit,
    SecondaryCircuit,
    decay_heat_fraction,
    saturation_temperature,
)


@dataclass
class Trip:
    key: str
    label: str
    detail: str = ""


#: A record of one reactivity contribution, for the operator's display.
ReactivityTerm = tuple[str, float]


@dataclass
class Plant:
    kinetics: PointKinetics = field(default_factory=PointKinetics)
    poisons: FissionProducts = field(default_factory=FissionProducts)
    fuel: FuelState = field(default_factory=FuelState)
    rods: RodController = field(default_factory=RodController)
    primary: PrimaryCircuit = field(default_factory=PrimaryCircuit)
    secondary: SecondaryCircuit = field(default_factory=SecondaryCircuit)

    boron_ppm: float = C.INITIAL_BORON_PPM
    boron_demand: float = 0.0       # -1 dilute, +1 borate
    auto_boron: bool = False

    tripped: bool = False
    trip_reasons: list[Trip] = field(default_factory=list)
    _pending_trip: Trip | None = None
    _trip_timer: float = 0.0

    #: Seconds of operation at power, used by the decay heat correlation.
    operating_seconds: float = 0.0
    seconds_since_trip: float = 1e6
    #: Thermal power at the moment of the trip, for decay heat.
    power_at_trip: float = 0.0

    #: 0 = pristine, 1 = molten core.
    core_damage: float = 0.0
    clad_damage: float = 0.0
    destroyed: bool = False
    #: Radioactive release, arbitrary units. Anything above 1 is a news story.
    release: float = 0.0

    #: Grid connection state, owned by the plant because a grid trip trips the
    #: turbine which very often trips the reactor.
    grid_connected: bool = True

    reactivity_terms: dict[str, float] = field(default_factory=dict)
    last_trip_check: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.poisons.set_equilibrium(1.0)

    # -- derived state ----------------------------------------------------

    @property
    def thermal_power_mw(self) -> float:
        return self.kinetics.power_fraction * C.NOMINAL_THERMAL_MW

    @property
    def decay_power_mw(self) -> float:
        if self.operating_seconds <= 0:
            return 0.0
        return self.power_at_trip * decay_heat_fraction(
            self.seconds_since_trip, self.operating_seconds
        )

    @property
    def core_power_mw(self) -> float:
        """Total heat produced in the core: fission plus decay."""
        return self.thermal_power_mw + self.decay_power_mw

    @property
    def net_electric_mw(self) -> float:
        pumps = self.primary.running_pumps * C.PUMP_LOAD_MW
        gross = self.secondary.gross_electric_mw
        return max(0.0, gross - pumps - C.HOUSE_LOAD_MW) if gross > 0 else -(pumps + C.HOUSE_LOAD_MW)

    @property
    def reactor_period(self) -> float:
        return inhour_period(self.reactivity_terms.get("total", 0.0))

    # -- reactivity -------------------------------------------------------

    def moderator_coefficient(self) -> float:
        """pcm/K, boron dependent.  Can go positive at high boron."""
        return C.MTC_BASE + C.MTC_BORON_SLOPE * self.boron_ppm

    def compute_reactivity(self) -> dict[str, float]:
        fuel_temperature_k = self.primary.fuel_temperature + C.KELVIN_OFFSET
        doppler = C.DOPPLER_K * (
            math.sqrt(max(fuel_temperature_k, 1.0)) - math.sqrt(C.DOPPLER_REF_K)
        )
        moderator = (
            self.moderator_coefficient()
            * (self.primary.coolant_temperature - C.NOMINAL_COOLANT_TEMP)
            * 1e-5
        )
        void = C.VOID_COEFFICIENT * self.primary.void_fraction * 100.0 * 1e-5
        boron = C.BORON_WORTH * self.boron_ppm * 1e-5

        terms = {
            "fuel": self.fuel.excess_reactivity,
            "rods": self.rods.total_reactivity,
            "boron": boron,
            "doppler": doppler,
            "moderator": moderator,
            "void": void,
            "xenon": self.poisons.xenon_reactivity,
            "samarium": self.poisons.samarium_reactivity,
        }
        terms["total"] = sum(terms.values())
        self.reactivity_terms = terms
        return terms

    # -- commands ---------------------------------------------------------

    def scram(self, reason: str = "Manual scram", key: str = "manual") -> None:
        if self.tripped:
            return
        self.tripped = True
        self.power_at_trip = max(self.thermal_power_mw, self.power_at_trip)
        self.seconds_since_trip = 0.0
        self.rods.scram()
        # A reactor trip trips the turbine: with the reactor shut down there is
        # no steam to drive it, and running it down under load would drag the
        # secondary side into a vacuum.
        self.secondary.trip_turbine()
        self.trip_reasons.append(Trip(key=key, label=reason))

    def reset_trip(self) -> bool:
        """Reset the protection system.  Refused while a trip condition stands."""
        if not self.tripped:
            return False
        if self._standing_trip() is not None:
            return False
        self.tripped = False
        self._pending_trip = None
        self._trip_timer = 0.0
        self.rods.reset()
        self.trip_reasons.clear()
        return True

    # -- protection system ------------------------------------------------

    def _standing_trip(self) -> Trip | None:
        """Return the first protection setpoint currently exceeded, if any."""
        k = self.kinetics
        p = self.primary
        s = self.secondary
        checks: list[tuple[bool, str, str, str]] = [
            (k.power_fraction > C.TRIP_HIGH_FLUX, "high_flux", "High neutron flux",
             f"{k.power_fraction * 100:.0f}% of rated"),
            (k.power_rate > C.TRIP_HIGH_FLUX_RATE and k.power_fraction > 0.05,
             "flux_rate", "High flux rate of change",
             f"{k.power_rate * 100:.1f} %/s"),
            (p.flow_fraction < C.TRIP_LOW_FLOW and k.power_fraction > 0.1,
             "low_flow", "Low reactor coolant flow",
             f"{p.flow_fraction * 100:.0f}% of rated"),
            (p.pressure > C.TRIP_HIGH_PRESSURE, "high_pressure",
             "High pressuriser pressure", f"{p.pressure:.2f} MPa"),
            (p.pressure < C.TRIP_LOW_PRESSURE and k.power_fraction > 0.1,
             "low_pressure", "Low pressuriser pressure", f"{p.pressure:.2f} MPa"),
            (p.hot_leg > C.TRIP_HIGH_OUTLET_TEMP, "high_temp",
             "High core outlet temperature", f"{p.hot_leg:.1f} degC"),
            (p.fuel_temperature > C.TRIP_HIGH_FUEL_TEMP, "high_fuel_temp",
             "High fuel temperature", f"{p.fuel_temperature:.0f} degC"),
            (s.sg_inventory < C.TRIP_LOW_SG_LEVEL, "low_sg_level",
             "Low steam generator level", f"{s.sg_inventory * 100:.0f}%"),
            (p.subcooling < 0 and k.power_fraction > 0.05, "saturation",
             "Loss of subcooling margin", f"{p.subcooling:.1f} K"),
        ]
        for triggered, key, label, detail in checks:
            if triggered:
                return Trip(key=key, label=label, detail=detail)
        return None

    def _check_protection(self, dt: float) -> None:
        if self.tripped:
            return
        standing = self._standing_trip()
        if standing is None:
            self._pending_trip = None
            self._trip_timer = 0.0
            return
        if self._pending_trip is None or self._pending_trip.key != standing.key:
            self._pending_trip = standing
            self._trip_timer = 0.0
        self._trip_timer += dt
        if self._trip_timer >= C.TRIP_DELAY:
            self.scram(f"{standing.label} ({standing.detail})", key=standing.key)

    # -- damage -----------------------------------------------------------

    def _update_damage(self, dt: float) -> None:
        temperature = self.primary.fuel_temperature
        if temperature > C.CLAD_DAMAGE_TEMP:
            rate = (temperature - C.CLAD_DAMAGE_TEMP) / 2000.0
            self.clad_damage = min(1.0, self.clad_damage + rate * dt * 0.02)
        if temperature > C.ZIRC_OXIDATION_TEMP:
            rate = (temperature - C.ZIRC_OXIDATION_TEMP) / 1600.0
            self.core_damage = min(1.0, self.core_damage + rate * dt * 0.01)
        if temperature > C.FUEL_MELT_TEMP:
            self.core_damage = min(1.0, self.core_damage + dt * 0.02)
        if self.kinetics.prompt_critical and self.kinetics.power_fraction > 4.0:
            # A prompt excursion destroys the fuel through sheer energy
            # deposition long before heat conduction has a say.
            self.core_damage = min(1.0, self.core_damage + self.kinetics.power_fraction * dt * 0.02)
        self.release = self.primary.release + self.clad_damage * 0.4 + self.core_damage * 8.0
        if self.core_damage >= 1.0:
            self.destroyed = True

    # -- automatic control ------------------------------------------------

    def _auto_rod_control(self, dt: float) -> None:
        """Hold coolant average temperature on its load-dependent programme.

        Real plants run a temperature programme: T-average is scheduled to
        rise a few kelvin from no load to full load, and the rod control
        system nudges the control banks to keep it there.  It is deliberately
        slow and has a wide deadband, because a rod control system that chases
        every wobble is a rod control system that will eventually chase one
        off a cliff.
        """
        if self.tripped or not self.rods.automatic:
            return
        load = max(0.0, min(1.0, self.secondary.turbine_valve))
        programme = 291.5 + 18.5 * load
        error = self.primary.coolant_temperature - programme
        if abs(error) < 0.6:
            return
        # Too hot means not enough heat is being taken away relative to
        # demand, so power must come up: withdraw. Limited to a slow crawl.
        demand = max(-1.0, min(1.0, error * 0.35))
        self.rods.move_control_banks(demand * 0.0022 * dt * 100.0 / 100.0)

    def _boron_auto(self, dt: float) -> None:
        """Keep the control banks inside their operating band using boron.

        Rods are for minutes, boron is for hours.  If the banks drift too far
        in or out the operator (or this automation) shifts boron to bring them
        back, which is exactly how a real plant compensates xenon and burnup.
        """
        if not self.auto_boron or self.tripped:
            return
        position = self.rods.control_position
        if position < 0.72:
            self.boron_demand = -1.0
        elif position > 0.94:
            self.boron_demand = 1.0
        else:
            self.boron_demand = 0.0

    # -- main step --------------------------------------------------------

    #: Largest internal integration step, seconds.  Everything in the plant
    #: has a time constant of a few seconds, so the physics is advanced in
    #: sub-steps no longer than this however fast the game clock is running.
    MAX_SUBSTEP = 0.5

    def step(self, dt: float) -> None:
        if dt <= 0:
            return
        remaining = dt
        while remaining > 1e-9:
            step = min(self.MAX_SUBSTEP, remaining)
            remaining -= step
            self._substep(step)

    def _substep(self, dt: float) -> None:
        # Chemical and volume control: boration and dilution.
        self._boron_auto(dt)
        if self.boron_demand > 0:
            self.boron_ppm += C.BORATION_RATE * self.boron_demand * dt
        elif self.boron_demand < 0:
            self.boron_ppm += C.DILUTION_RATE * self.boron_demand * dt
        self.boron_ppm = max(0.0, min(self.boron_ppm, 2600.0))

        self._auto_rod_control(dt)
        self.rods.step(dt)
        terms = self.compute_reactivity()

        if self.destroyed:
            self.kinetics.power_fraction *= math.exp(-dt / 30.0)
        else:
            self.kinetics.step(terms["total"], dt)

        if self.kinetics.power_fraction > 0.02:
            self.operating_seconds += dt * self.kinetics.power_fraction
            self.power_at_trip = max(self.power_at_trip, self.thermal_power_mw)
        self.seconds_since_trip += dt

        self.poisons.step(self.kinetics.power_fraction, dt)
        self.fuel.step(self.thermal_power_mw, dt)

        conductance = self.secondary.conductance(self.primary.flow_fraction)
        _, sg_heat = self.primary.step(
            self.core_power_mw, conductance, self.secondary.steam_temperature, dt
        )
        self.secondary.step(sg_heat, dt)

        self._update_damage(dt)
        self._check_protection(dt)

    # -- convenience ------------------------------------------------------

    def stabilise(self, seconds: float = 900.0) -> None:
        """Run the plant to a steady state.  Used when setting up a scenario."""
        self.step(seconds)

    def trim_boron_for_criticality(self) -> None:
        """Adjust soluble boron until the core is exactly critical.

        This is what a real chemistry team does before a startup, and it is
        how a scenario is set up here: everything else is fixed by the plant
        design, so boron is the free variable.
        """
        terms = self.compute_reactivity()
        excess_pcm = terms["total"] * 1e5
        self.boron_ppm = max(0.0, self.boron_ppm + excess_pcm / abs(C.BORON_WORTH))
        self.compute_reactivity()
