"""Thermal hydraulics: fuel, primary circuit, steam generators, turbine.

The plant is modelled as four coupled lumped-capacity nodes.

    fuel  --(film)-->  primary coolant  --(SG)-->  secondary  --(turbine)--> grid

Each link is a heat flow driven by a temperature or pressure difference, and
each node has a heat capacity that gives it a time constant.  The result is a
plant with the same characteristic behaviour as a real pressurised water
reactor, including the property that most surprises people the first time they
see it: **the reactor follows the turbine.**

Open the turbine governor valve and more heat leaves the secondary side.  The
steam generators cool, so they pull more heat out of the primary circuit, so
the coolant average temperature falls.  A negative moderator temperature
coefficient turns that fall into positive reactivity, and reactor power rises
on its own to meet the new load, settling when the temperature is back where
it started.  Nobody moved a control rod.  Close the valve and the reverse
happens.  A PWR is a self-regulating machine, and learning to work with that
rather than against it is most of the skill in operating one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import constants as C

# ---------------------------------------------------------------------------
# Water saturation curve
# ---------------------------------------------------------------------------
#
# Steam tables, tabulated and log-interpolated. Accurate to better than 0.5 K
# across the whole range the plant operates in, which is far tighter than
# anything else in this model.

_SATURATION = (
    (0.0010, 7.0), (0.0025, 21.1), (0.0050, 32.9), (0.0100, 45.8),
    (0.0250, 65.0), (0.0500, 81.3), (0.1000, 99.6), (0.2000, 120.2),
    (0.3000, 133.5), (0.5000, 151.8), (0.7000, 165.0), (1.0000, 179.9),
    (1.5000, 198.3), (2.0000, 212.4), (3.0000, 233.9), (4.0000, 250.4),
    (5.0000, 263.9), (6.0000, 275.6), (7.0000, 285.8), (8.0000, 295.0),
    (9.0000, 303.3), (10.000, 311.0), (11.000, 318.1), (12.000, 324.7),
    (13.000, 330.9), (14.000, 336.7), (15.000, 342.2), (16.000, 347.4),
    (17.000, 352.3), (18.000, 357.0), (19.000, 361.5), (20.000, 365.7),
    (21.000, 369.8), (22.064, 373.95),
)


def saturation_temperature(pressure_mpa: float) -> float:
    """Saturation temperature of water in degC at the given pressure in MPa."""
    pressure = max(pressure_mpa, _SATURATION[0][0])
    if pressure >= _SATURATION[-1][0]:
        return _SATURATION[-1][1]
    for (p_low, t_low), (p_high, t_high) in zip(_SATURATION, _SATURATION[1:]):
        if pressure <= p_high:
            span = math.log(p_high / p_low)
            fraction = math.log(pressure / p_low) / span
            return t_low + fraction * (t_high - t_low)
    return _SATURATION[-1][1]


def saturation_pressure(temperature_c: float) -> float:
    """Saturation pressure of water in MPa at the given temperature in degC."""
    temperature = max(temperature_c, _SATURATION[0][1])
    if temperature >= _SATURATION[-1][1]:
        return _SATURATION[-1][0]
    for (p_low, t_low), (p_high, t_high) in zip(_SATURATION, _SATURATION[1:]):
        if temperature <= t_high:
            fraction = (temperature - t_low) / (t_high - t_low)
            return p_low * math.exp(fraction * math.log(p_high / p_low))
    return _SATURATION[-1][0]


def decay_heat_fraction(seconds_since_shutdown: float, operating_seconds: float) -> float:
    """Fraction of pre-shutdown thermal power still being produced by decay.

    The Wigner-Way correlation.  A reactor that has been at full power for a
    year is still making 6-7% of rated power the instant the rods drop, 1%
    after an hour, and a few tenths of a percent a day later.  For this plant
    that is 220 MW at second zero -- more than enough to melt the core if it
    is not removed, which is what makes a station blackout lethal and why the
    residual heat removal chain is worth as much attention as the reactor.
    """
    if operating_seconds <= 0:
        return 0.0
    t = max(seconds_since_shutdown, 1.0)
    fraction = 0.066 * (t ** -0.2 - (t + operating_seconds) ** -0.2)
    return max(0.0, min(fraction, 0.07))


@dataclass
class PrimaryCircuit:
    """Fuel, coolant, pressuriser and the four reactor coolant pumps.

    The fuel and coolant nodes are advanced with an exponential (semi-implicit)
    update rather than a forward Euler step.  Their time constants are 4 and 8
    seconds respectively, so an explicit integrator would go unstable the
    moment the simulation was run faster than about twice real time -- and this
    game very much wants to be run at sixty times real time, because xenon
    takes nine hours to do anything interesting.  The exponential form is
    exact for a constant driving temperature and unconditionally stable for
    any step size.
    """

    fuel_temperature: float = C.NOMINAL_FUEL_TEMP
    coolant_temperature: float = C.NOMINAL_COOLANT_TEMP
    pressure: float = C.NOMINAL_PRIMARY_PRESSURE
    #: One entry per reactor coolant pump: True if commanded running.
    pumps: list[bool] | None = None
    #: Actual flow as a fraction of rated, which lags the pump commands.
    flow_fraction: float = 1.0
    #: Steam void fraction in the core, 0-1.
    void_fraction: float = 0.0
    #: Fraction of the coolant inventory remaining.
    inventory: float = 1.0
    #: Leak rate as a fraction of inventory per second (a small break LOCA).
    leak_rate: float = 0.0
    pressuriser_heaters: float = 0.0
    relief_open: bool = False
    safety_injection: bool = False
    #: Cumulative escape of radioactivity, arbitrary units.
    release: float = 0.0
    #: Cumulative thermal fatigue of the reactor vessel, 0-1.
    vessel_stress: float = 0.0
    _delta_t: float = 33.0
    _last_temperature: float = C.NOMINAL_COOLANT_TEMP

    def __post_init__(self) -> None:
        if self.pumps is None:
            self.pumps = [True, True, True, True]

    @property
    def running_pumps(self) -> int:
        return sum(1 for pump in self.pumps if pump)

    @property
    def hot_leg(self) -> float:
        return self.coolant_temperature + 0.5 * self._delta_t

    @property
    def cold_leg(self) -> float:
        return self.coolant_temperature - 0.5 * self._delta_t

    @property
    def subcooling(self) -> float:
        """Margin to boiling in the hot leg, K.  Zero means the core is boiling."""
        return saturation_temperature(self.pressure) - self.hot_leg

    def sync(self) -> None:
        """Re-baseline the pressuriser after the state is set externally.

        The pressure model works on the *change* in coolant temperature each
        step, so anything that teleports the plant to a new temperature (a
        scenario setup, a save file being loaded) must say so, or the next step
        sees a 270 K surge that never happened.
        """
        self._last_temperature = self.coolant_temperature

    def target_flow(self) -> float:
        pumped = self.running_pumps / 4.0
        if pumped <= 0:
            return C.NATURAL_CIRCULATION_FRACTION * self.inventory
        return max(pumped, C.NATURAL_CIRCULATION_FRACTION) * self.inventory

    def step_flow(self, dt: float) -> None:
        target = self.target_flow()
        # Pumps spin up quickly and coast down slowly against their flywheels.
        tau = 3.0 if target > self.flow_fraction else C.PUMP_COASTDOWN_TAU
        self.flow_fraction += (target - self.flow_fraction) * (1.0 - math.exp(-dt / tau))
        self.flow_fraction = max(0.0, min(self.flow_fraction, 1.05))

    def heat_transfer_coefficient(self) -> float:
        """Fuel-to-coolant heat transfer, degraded by low flow and by voiding.

        Turbulent forced convection scales roughly with flow^0.8; steam is a
        far worse coolant than water, so voiding collapses the coefficient and
        the fuel temperature runs away even though the void has simultaneously
        reduced reactor power.  Uncovering the core -- inventory below about
        half -- removes the coolant from the equation altogether.
        """
        flow_term = max(self.flow_fraction, 0.015) ** 0.8
        void_penalty = 1.0 - 0.85 * self.void_fraction
        uncovered = 1.0 if self.inventory > 0.55 else max(0.06, (self.inventory / 0.55) ** 2)
        return max(C.FUEL_COOLANT_HTC * flow_term * void_penalty * uncovered, 0.02)

    def step(
        self,
        core_power_mw: float,
        sg_conductance: float,
        steam_temperature: float,
        dt: float,
    ) -> tuple[float, float]:
        """Advance the primary circuit.

        ``sg_conductance`` is the steam generator heat transfer in MW/K and
        ``steam_temperature`` the secondary saturation temperature, so that
        the coolant node can be solved against both of its couplings at once.

        Returns ``(film_heat, sg_heat)`` in MW.
        """
        self.step_flow(dt)
        self._step_inventory(dt)

        htc = self.heat_transfer_coefficient()

        # Zirconium-steam reaction: above 1200 degC the cladding oxidises
        # exothermically, and the reaction accelerates itself. This is what
        # turned three damaged cores into hydrogen explosions at Fukushima.
        chemical_heat = 0.0
        if self.fuel_temperature > C.ZIRC_OXIDATION_TEMP:
            excess = self.fuel_temperature - C.ZIRC_OXIDATION_TEMP
            chemical_heat = C.ZIRC_REACTION_GAIN * excess * excess * 0.01
            self.release += chemical_heat * dt * 1e-3

        # Fuel node: exponential relaxation towards the temperature at which
        # the film carries away exactly the heat being produced.
        fuel_equilibrium = self.coolant_temperature + (core_power_mw + chemical_heat) / htc
        tau_fuel = C.FUEL_HEAT_CAPACITY / htc
        self.fuel_temperature += (fuel_equilibrium - self.fuel_temperature) * (
            1.0 - math.exp(-dt / tau_fuel)
        )
        self.fuel_temperature = max(self.fuel_temperature, C.AMBIENT_TEMP)
        film_heat = htc * (self.fuel_temperature - self.coolant_temperature)

        # Coolant node: relaxes towards the conductance-weighted mean of the
        # fuel and the secondary side, plus the pump heat. Four reactor coolant
        # pumps put about 18 MW of shaft work into the water, which is not a
        # rounding error: it is how a cold plant is warmed to operating
        # temperature before the reactor is ever taken critical.
        capacity = C.COOLANT_HEAT_CAPACITY * max(self.inventory, 0.05)
        conductance = htc + max(sg_conductance, 0.0)
        pump_heat = self.running_pumps * C.PUMP_HEAT_MW
        equilibrium = (
            htc * self.fuel_temperature + sg_conductance * steam_temperature + pump_heat
        ) / conductance
        tau_coolant = capacity / conductance
        previous = self.coolant_temperature
        self.coolant_temperature += (equilibrium - self.coolant_temperature) * (
            1.0 - math.exp(-dt / tau_coolant)
        )
        self.coolant_temperature = max(self.coolant_temperature, C.AMBIENT_TEMP)
        sg_heat = max(sg_conductance, 0.0) * (self.coolant_temperature - steam_temperature)

        # Core temperature rise, used for the hot and cold leg readings.
        flow = max(self.flow_fraction, 0.008) * C.FULL_PRIMARY_FLOW
        self._delta_t = max(0.0, min(film_heat / (flow * C.COOLANT_CP), 140.0))

        self._step_thermal_stress(previous, dt)
        self._step_pressure(dt)
        self._step_void(dt)
        return film_heat, sg_heat

    def _step_inventory(self, dt: float) -> None:
        if self.leak_rate > 0:
            self.inventory = max(0.0, self.inventory - self.leak_rate * dt)
        if self.safety_injection and self.inventory < 1.0:
            # High pressure injection only works once pressure has fallen
            # below the pumps' shutoff head -- the reason Three Mile Island
            # took hours to recover and not minutes.
            if self.pressure < 11.0:
                self.inventory = min(1.0, self.inventory + 0.0022 * dt)
            elif self.pressure < 15.5:
                self.inventory = min(1.0, self.inventory + 0.0004 * dt)

    def _step_thermal_stress(self, previous: float, dt: float) -> None:
        if dt <= 0:
            return
        rate_per_hour = abs(self.coolant_temperature - previous) / dt * 3600.0
        # Technical specifications limit heat-up and cool-down to 55 K/h to
        # keep the pressure vessel out of its brittle fracture region.
        if rate_per_hour > 55.0:
            self.vessel_stress = min(
                1.0, self.vessel_stress + (rate_per_hour - 55.0) * dt * 5.0e-8
            )

    def _step_pressure(self, dt: float) -> None:
        """Pressuriser pressure.

        The pressuriser is a steam bubble on a standpipe off the hot leg. When
        the coolant expands it surges in and compresses the bubble; when the
        coolant shrinks it surges out and the bubble expands.  Heaters and
        sprays then restore the setpoint, but only at a finite rate, so what
        the operator sees is a pressure *transient* on every temperature
        change followed by a recovery -- not a permanent offset.

        Lose coolant inventory and the bubble can no longer be maintained at
        all, and pressure falls to whatever the water will support.  That is
        the low-pressure trip, and it is the first hard evidence of a leak.
        """
        surge = C.PRESSURISER_STIFFNESS * (self.coolant_temperature - self._last_temperature)
        self._last_temperature = self.coolant_temperature
        self.pressure += surge

        # With inventory lost the pressuriser cannot hold the setpoint. Note
        # the asymmetry: the steam bubble collapses as fast as physics allows,
        # while the heaters can only push pressure back up at a limited rate.
        # A leak therefore shows up on the pressure gauge long before it shows
        # up anywhere else, which is exactly how it works in a real plant.
        ceiling = C.NOMINAL_PRIMARY_PRESSURE * max(self.inventory, 0.03) ** 0.9
        if self.pressure > ceiling:
            self.pressure += (ceiling - self.pressure) * (1.0 - math.exp(-dt / 10.0))
        setpoint = min(C.NOMINAL_PRIMARY_PRESSURE, ceiling)
        error = setpoint - self.pressure
        self.pressuriser_heaters = max(-1.0, min(1.0, error * 4.0))
        authority = C.PRESSURISER_CONTROL_RATE * dt
        self.pressure += max(-authority, min(authority, error))

        self.relief_open = False
        if self.pressure > C.PORV_SETPOINT:
            self.relief_open = True
            relief = min(C.PORV_CAPACITY, (self.pressure - C.PORV_SETPOINT) * 0.8)
            self.pressure -= relief * dt
            self.inventory = max(0.0, self.inventory - relief * dt * 0.0016)
            self.release += relief * dt * 0.02
        if self.pressure > C.SAFETY_VALVE_SETPOINT:
            self.pressure -= (self.pressure - C.SAFETY_VALVE_SETPOINT) * min(1.0, dt * 2.0)
        self.pressure = max(self.pressure, 0.08)

    def _step_void(self, dt: float) -> None:
        superheat = self.hot_leg - saturation_temperature(self.pressure)
        target = 0.0 if superheat < 0 else min(1.0, superheat / 25.0)
        if self.inventory < 0.85:
            target = max(target, min(1.0, (0.85 - self.inventory) * 2.2))
        self.void_fraction += (target - self.void_fraction) * (1.0 - math.exp(-dt / 4.0))
        self.void_fraction = max(0.0, min(self.void_fraction, 1.0))


@dataclass
class SecondaryCircuit:
    """Steam generators, turbine governor valve, steam dumps and generator.

    The steam dump system is the unsung hero of a nuclear plant.  When the
    turbine trips, the reactor is still making 3400 MW and has nowhere to put
    it; the dumps pass steam straight past the turbine into the condenser and
    hold secondary pressure at the no-load setpoint, which holds the primary
    circuit at a stable hot standby instead of letting it boil.  Lose the
    condenser as well and the atmospheric relief valves do the same job, more
    loudly and at the cost of the plant's clean water inventory.
    """

    steam_pressure: float = C.NOMINAL_STEAM_PRESSURE
    sg_inventory: float = 1.0
    turbine_valve: float = 1.0
    valve_demand: float = 1.0
    feedwater: float = 1.0
    auto_feedwater: bool = True
    turbine_tripped: bool = False
    generator_online: bool = True
    condenser_available: bool = True
    #: Secondary pressure the dump system holds when the turbine is not taking
    #: the steam.  Lowering it is how the plant is deliberately cooled down.
    dump_setpoint: float = 7.5
    dump_valve: float = 0.0
    #: Fraction of rated steam flow the dump valves can pass to the condenser.
    #: 45% is typical; the enlarged dumps upgrade nearly doubles it, which is
    #: the difference between riding out a turbine trip and tripping with it.
    dump_capacity: float = 0.45
    gross_electric_mw: float = 0.0
    steam_flow_mw: float = 0.0

    @property
    def steam_temperature(self) -> float:
        return saturation_temperature(self.steam_pressure)

    def conductance(self, flow_fraction: float) -> float:
        """Steam generator heat transfer in MW/K at the given primary flow."""
        if self.sg_inventory <= 0.03:
            return 0.05
        return (
            C.SG_HTC
            * (max(flow_fraction, 0.015) ** 0.6)
            * min(self.sg_inventory, 1.0)
        )

    #: Largest internal step for the secondary energy balance, seconds. The
    #: steam side is the one genuinely explicit integration left in the model
    #: -- steam pressure depends on saturation temperature through a table,
    #: which cannot be inverted analytically -- so it guards itself.
    MAX_SUBSTEP = 0.5

    def step(self, sg_heat_mw: float, dt: float) -> float:
        """Advance the secondary side.  Returns gross electrical output, MW."""
        remaining = dt
        output = self.gross_electric_mw
        while remaining > 1e-9:
            piece = min(self.MAX_SUBSTEP, remaining)
            remaining -= piece
            output = self._advance(sg_heat_mw, piece)
        return output

    def _advance(self, sg_heat_mw: float, dt: float) -> float:
        if self.turbine_tripped or not self.condenser_available:
            self.turbine_valve = max(0.0, self.turbine_valve - dt * 1.5)
        else:
            slew = C.TURBINE_VALVE_SLEW * dt
            self.turbine_valve += max(-slew, min(slew, self.valve_demand - self.turbine_valve))
            self.turbine_valve = max(0.0, min(1.0, self.turbine_valve))

        condenser_pressure = C.CONDENSER_PRESSURE if self.condenser_available else 0.101
        available = max(self.steam_pressure - condenser_pressure, 0.0)
        self.steam_flow_mw = self.turbine_valve * C.TURBINE_FLOW_COEFF * available

        # Steam dumps / atmospheric reliefs hold the no-load pressure.
        error = self.steam_pressure - self.dump_setpoint
        self.dump_valve = max(0.0, min(1.0, error * 1.6))
        dump_capacity = self.dump_capacity if self.condenser_available else 0.16
        dump = self.dump_valve * dump_capacity * C.TURBINE_FLOW_COEFF * available
        if not self.condenser_available and self.dump_valve > 0:
            # Atmospheric dump throws the working fluid away.
            self.sg_inventory = max(0.0, self.sg_inventory - self.dump_valve * 0.004 * dt)

        temperature = self.steam_temperature
        temperature += (sg_heat_mw - self.steam_flow_mw - dump) * dt / C.SECONDARY_HEAT_CAPACITY
        temperature = max(C.AMBIENT_TEMP, min(temperature, 372.0))
        self.steam_pressure = saturation_pressure(temperature)

        self._step_inventory(sg_heat_mw, dt)

        if self.steam_pressure > 8.6:
            self.steam_pressure -= (self.steam_pressure - 8.6) * min(1.0, dt)
            self.sg_inventory = max(0.0, self.sg_inventory - 0.004 * dt)

        # Rankine efficiency falls with steam pressure: a heat engine is only
        # as good as the temperatures it works between.
        if self.generator_online and not self.turbine_tripped:
            efficiency = C.BASE_CYCLE_EFFICIENCY * (
                0.55 + 0.45 * min(self.steam_pressure / C.NOMINAL_STEAM_PRESSURE, 1.15)
            )
            self.gross_electric_mw = self.steam_flow_mw * efficiency
        else:
            self.gross_electric_mw = 0.0
        return self.gross_electric_mw

    def _step_inventory(self, sg_heat_mw: float, dt: float) -> None:
        boil_off = (max(sg_heat_mw, 0.0) / C.NOMINAL_THERMAL_MW) * 0.0055
        if self.auto_feedwater:
            level_error = 1.0 - self.sg_inventory
            self.feedwater = max(0.0, min(1.3, boil_off / 0.0055 + level_error * 3.0))
        make_up = self.feedwater * 0.0055
        self.sg_inventory += (make_up - boil_off) * dt
        self.sg_inventory = max(0.0, min(self.sg_inventory, 1.3))

    def trip_turbine(self) -> None:
        self.turbine_tripped = True
        self.generator_online = False

    def reset_turbine(self) -> None:
        self.turbine_tripped = False
        self.generator_online = True
