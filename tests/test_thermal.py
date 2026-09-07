"""Thermal hydraulics: steam tables, decay heat, and integrator stability."""

import math

import pytest

from reactorsim import constants as C
from reactorsim.thermal import (
    PrimaryCircuit,
    SecondaryCircuit,
    decay_heat_fraction,
    saturation_pressure,
    saturation_temperature,
)

# Reference points straight out of the steam tables.
STEAM_TABLE = [
    (0.1, 99.6), (1.0, 179.9), (3.0, 233.9), (6.9, 285.0),
    (10.0, 311.0), (15.5, 344.8), (20.0, 365.7),
]


@pytest.mark.parametrize("pressure,temperature", STEAM_TABLE)
def test_saturation_temperature(pressure, temperature):
    assert saturation_temperature(pressure) == pytest.approx(temperature, abs=0.6)


@pytest.mark.parametrize("pressure,temperature", STEAM_TABLE)
def test_saturation_pressure_round_trip(pressure, temperature):
    assert saturation_pressure(temperature) == pytest.approx(pressure, rel=0.03)


def test_saturation_is_monotonic():
    previous = -1.0
    for pressure in [0.01 * 1.15 ** n for n in range(54)]:  # up to ~20 MPa
        value = saturation_temperature(pressure)
        assert value > previous
        previous = value


def test_decay_heat_immediately_after_a_long_run():
    # A core that has run for a year is making about 6.5% of rated power the
    # instant the rods drop.
    year = 365 * 86400.0
    assert decay_heat_fraction(1.0, year) == pytest.approx(0.065, abs=0.006)


def test_decay_heat_after_an_hour_and_a_day():
    year = 365 * 86400.0
    assert decay_heat_fraction(3600.0, year) == pytest.approx(0.0110, abs=0.003)
    assert decay_heat_fraction(86400.0, year) == pytest.approx(0.0048, abs=0.002)


def test_decay_heat_falls_monotonically():
    year = 365 * 86400.0
    values = [decay_heat_fraction(t, year) for t in (1, 10, 100, 1000, 10000, 100000)]
    assert values == sorted(values, reverse=True)


def test_decay_heat_of_a_core_that_never_ran_is_zero():
    assert decay_heat_fraction(10.0, 0.0) == 0.0


def test_short_operating_history_gives_little_decay_heat():
    brief = decay_heat_fraction(3600.0, 1200.0)
    long = decay_heat_fraction(3600.0, 365 * 86400.0)
    assert brief < long / 10.0


def test_pump_coastdown_is_slower_than_run_up():
    circuit = PrimaryCircuit()
    circuit.pumps = [False] * 4
    for _ in range(20):
        circuit.step_flow(1.0)
    coasted = circuit.flow_fraction
    circuit.pumps = [True] * 4
    for _ in range(20):
        circuit.step_flow(1.0)
    assert coasted > C.NATURAL_CIRCULATION_FRACTION
    assert circuit.flow_fraction > 0.98


def test_natural_circulation_floor():
    circuit = PrimaryCircuit()
    circuit.pumps = [False] * 4
    for _ in range(400):
        circuit.step_flow(1.0)
    assert circuit.flow_fraction == pytest.approx(C.NATURAL_CIRCULATION_FRACTION, rel=0.05)


def test_heat_transfer_degrades_with_flow_and_void():
    circuit = PrimaryCircuit()
    full = circuit.heat_transfer_coefficient()
    circuit.flow_fraction = 0.2
    assert circuit.heat_transfer_coefficient() < full
    circuit.flow_fraction = 1.0
    circuit.void_fraction = 0.5
    assert circuit.heat_transfer_coefficient() < full


def test_integrator_is_stable_at_large_steps():
    """The exponential update must not ring or diverge at any step size.

    A forward Euler scheme on a 4 second time constant goes unstable above
    about 8 seconds; the game runs 30 second sub-steps at high speed.
    """
    for dt in (0.5, 5.0, 30.0, 120.0):
        primary = PrimaryCircuit()
        secondary = SecondaryCircuit()
        for _ in range(int(4000 / dt)):
            conductance = secondary.conductance(primary.flow_fraction)
            _, sg_heat = primary.step(
                C.NOMINAL_THERMAL_MW, conductance, secondary.steam_temperature, dt)
            secondary.step(sg_heat, dt)
        assert 250.0 < primary.coolant_temperature < 360.0, dt
        assert 400.0 < primary.fuel_temperature < 1000.0, dt
        assert math.isfinite(primary.pressure)


def test_steady_state_matches_the_design_point():
    primary = PrimaryCircuit()
    secondary = SecondaryCircuit()
    for _ in range(4000):
        conductance = secondary.conductance(primary.flow_fraction)
        _, sg_heat = primary.step(
            C.NOMINAL_THERMAL_MW, conductance, secondary.steam_temperature, 0.5)
        secondary.step(sg_heat, 0.5)
    assert primary.coolant_temperature == pytest.approx(C.NOMINAL_COOLANT_TEMP, abs=3.0)
    assert primary.fuel_temperature == pytest.approx(C.NOMINAL_FUEL_TEMP, abs=25.0)
    assert primary.hot_leg == pytest.approx(C.NOMINAL_HOT_LEG, abs=3.0)
    assert primary.cold_leg == pytest.approx(C.NOMINAL_COLD_LEG, abs=3.0)
    assert secondary.steam_pressure == pytest.approx(C.NOMINAL_STEAM_PRESSURE, abs=0.3)
    # A four loop PWR of this size makes about 1150 MW gross.
    assert 1080.0 < secondary.gross_electric_mw < 1250.0


def test_pressuriser_restores_its_setpoint():
    primary = PrimaryCircuit()
    primary.pressure = 13.8
    primary.sync()
    for _ in range(400):
        primary._step_pressure(0.5)
    assert primary.pressure == pytest.approx(C.NOMINAL_PRIMARY_PRESSURE, abs=0.1)


def test_relief_valve_lifts_and_loses_inventory():
    primary = PrimaryCircuit()
    primary.pressure = 16.8
    primary.sync()
    before = primary.inventory
    for _ in range(60):
        primary._step_pressure(0.5)
    assert primary.relief_open or primary.pressure < C.PORV_SETPOINT
    assert primary.inventory < before


def test_losing_inventory_drops_pressure():
    primary = PrimaryCircuit()
    primary.inventory = 0.5
    primary.sync()
    for _ in range(200):
        primary._step_pressure(0.5)
    assert primary.pressure < C.TRIP_LOW_PRESSURE


def test_pump_heat_warms_a_cold_plant_within_the_technical_limit():
    primary = PrimaryCircuit()
    primary.fuel_temperature = 40.0
    primary.coolant_temperature = 40.0
    primary.sync()
    secondary = SecondaryCircuit()
    secondary.steam_pressure = 0.0074
    secondary.dump_setpoint = 1.0
    for _ in range(3600):
        conductance = secondary.conductance(primary.flow_fraction)
        _, sg_heat = primary.step(0.0, conductance, secondary.steam_temperature, 1.0)
        secondary.step(sg_heat, 1.0)
    rise = primary.coolant_temperature - 40.0
    assert 25.0 < rise < 55.0, f"{rise:.1f} K/h"


def test_steam_dumps_hold_the_no_load_pressure():
    secondary = SecondaryCircuit()
    secondary.trip_turbine()
    for _ in range(4000):
        # A trickle of decay heat, as after a trip.
        secondary.step(35.0, 0.5)
    assert secondary.steam_pressure == pytest.approx(secondary.dump_setpoint, abs=0.35)


def test_turbine_trip_stops_generation():
    secondary = SecondaryCircuit()
    secondary.step(C.NOMINAL_THERMAL_MW, 0.5)
    assert secondary.gross_electric_mw > 0
    secondary.trip_turbine()
    for _ in range(20):
        secondary.step(C.NOMINAL_THERMAL_MW, 0.5)
    assert secondary.gross_electric_mw == 0.0
