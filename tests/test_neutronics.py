"""Neutron kinetics and fission product poisons, checked against textbook values.

These are not regression tests against whatever the code happened to produce.
Every expected value here comes from published reactor physics, and if the
model stops reproducing them the model is wrong, not the test.
"""

import math

import pytest

from reactorsim import constants as C
from reactorsim.neutronics import (
    FissionProducts,
    FuelState,
    PointKinetics,
    inhour_period,
)


def test_delayed_fraction_matches_u235():
    # Beta for thermal fission of U-235 is 0.0065; one dollar of reactivity.
    assert C.BETA_TOTAL == pytest.approx(0.0065, abs=2e-4)


def test_stable_period_for_small_positive_reactivity():
    # A +100 pcm step gives a stable period of about 55 seconds. This is the
    # single most quoted number in reactor operator training.
    assert inhour_period(0.001) == pytest.approx(55.0, rel=0.08)


def test_period_approaches_prompt_at_one_dollar():
    # Approaching prompt critical the period collapses towards milliseconds.
    assert inhour_period(0.005) < 2.0
    assert inhour_period(0.0064) < 0.5


def test_negative_period_asymptote():
    # However much negative reactivity is inserted, power cannot fall faster
    # than the longest-lived precursor allows: about -80 seconds.
    for rho in (-0.01, -0.05, -0.2):
        assert inhour_period(rho) == pytest.approx(-80.0, rel=0.12)


def test_equilibrium_holds_at_zero_reactivity():
    kinetics = PointKinetics()
    for _ in range(2000):
        kinetics.step(0.0, 0.5)
    assert kinetics.power_fraction == pytest.approx(1.0, rel=1e-3)


def test_prompt_jump_on_reactivity_step():
    # An instantaneous step to rho produces an immediate jump of beta/(beta-rho)
    # before the delayed neutrons have had time to respond.
    kinetics = PointKinetics()
    kinetics.step(0.002, 0.02)
    expected = C.BETA_TOTAL / (C.BETA_TOTAL - 0.002)
    assert kinetics.power_fraction == pytest.approx(expected, rel=0.05)


def test_asymptotic_period_matches_the_inhour_equation():
    """Once the short-lived precursor groups have settled, growth is exponential
    with exactly the period the inhour equation predicts."""
    kinetics = PointKinetics()
    rho = 0.001
    # Let the transient die away first: the early rise is faster than the
    # asymptotic period because the short-lived groups dominate at first.
    for _ in range(600):
        kinetics.step(rho, 0.5)
    start = kinetics.power_fraction
    for _ in range(200):
        kinetics.step(rho, 0.5)
    measured = 100.0 / math.log(kinetics.power_fraction / start)
    assert measured == pytest.approx(inhour_period(rho), rel=0.05)


def test_prompt_jump_precedes_the_delayed_rise():
    """The jump is immediate; the ramp that follows is slower than the jump."""
    kinetics = PointKinetics()
    kinetics.step(0.002, 0.02)
    jump = kinetics.power_fraction
    assert jump == pytest.approx(C.BETA_TOTAL / (C.BETA_TOTAL - 0.002), rel=0.05)
    for _ in range(20):
        kinetics.step(0.002, 0.5)
    assert kinetics.power_fraction > jump


def test_prompt_criticality_is_explosive():
    kinetics = PointKinetics()
    kinetics.step(C.BETA_TOTAL + 0.001, 0.05)
    assert kinetics.prompt_critical
    assert kinetics.power_fraction > 5.0


def test_subcritical_multiplication_is_finite_and_falls_with_depth():
    shallow = PointKinetics()
    deep = PointKinetics()
    shallow.set_equilibrium(0.0)
    deep.set_equilibrium(0.0)
    for _ in range(400):
        shallow.step(-0.01, 1.0)
        deep.step(-0.06, 1.0)
    assert shallow.power_fraction > deep.power_fraction > 0.0


def test_equilibrium_xenon_worth():
    # Equilibrium xenon at full power is about -2700 pcm in a large PWR.
    poisons = FissionProducts()
    poisons.set_equilibrium(1.0)
    assert poisons.xenon_reactivity * 1e5 == pytest.approx(-2700, rel=0.1)


def test_xenon_peaks_about_nine_hours_after_a_trip():
    poisons = FissionProducts()
    poisons.set_equilibrium(1.0)
    equilibrium = poisons.xenon_reactivity
    worst, worst_time = 0.0, 0.0
    for step in range(int(30 * 3600 / 20)):
        poisons.step(0.0, 20.0)
        if poisons.xenon_reactivity < worst:
            worst, worst_time = poisons.xenon_reactivity, (step + 1) * 20.0
    hours = worst_time / 3600.0
    assert 7.5 < hours < 11.5, f"peak at {hours:.1f} h"
    # The peak is well over the equilibrium value: this is the pit.
    assert 1.5 < worst / equilibrium < 2.6


def test_xenon_decays_away_eventually():
    poisons = FissionProducts()
    poisons.set_equilibrium(1.0)
    for _ in range(int(96 * 3600 / 60)):
        poisons.step(0.0, 60.0)
    assert abs(poisons.xenon_reactivity * 1e5) < 300


def test_xenon_burns_out_at_power():
    """Starting from a cold core, xenon builds to equilibrium and stops."""
    poisons = FissionProducts()
    for _ in range(int(60 * 3600 / 60)):
        poisons.step(1.0, 60.0)
    reference = FissionProducts()
    reference.set_equilibrium(1.0)
    assert poisons.xenon_reactivity == pytest.approx(reference.xenon_reactivity, rel=0.03)


def test_samarium_is_smaller_and_permanent():
    poisons = FissionProducts()
    poisons.set_equilibrium(1.0)
    before = poisons.samarium_reactivity
    assert -1200 < before * 1e5 < -300
    for _ in range(int(48 * 3600 / 60)):
        poisons.step(0.0, 60.0)
    # Samarium-149 is stable, so shutting down does not remove it.
    assert poisons.samarium_reactivity <= before


def test_fuel_excess_falls_with_burnup():
    fuel = FuelState(enrichment=4.5)
    fuel.burnable_poison = 0.0
    start = fuel.excess_reactivity
    fuel.burnup = 20.0
    middle = fuel.excess_reactivity
    fuel.burnup = 45.0
    end = fuel.excess_reactivity
    assert start > middle > end
    assert fuel.cycle_fraction == pytest.approx(45.0 / (start / (C.BURNUP_REACTIVITY_SLOPE * 1e-5)), rel=0.05)


def test_higher_enrichment_buys_more_cycle():
    low = FuelState(enrichment=3.0)
    high = FuelState(enrichment=4.8)
    assert high.fresh_excess > low.fresh_excess


def test_burnup_accumulates_at_the_right_rate():
    fuel = FuelState()
    # A full year at 3400 MW on 104 tU is about 11.9 GWd/tU.
    fuel.step(3400.0, 365 * 86400.0)
    assert fuel.burnup == pytest.approx(3400 / 1000 * 365 / 104.0, rel=1e-6)
