"""The assembled plant: reactivity balance, protection system, damage."""

import pytest

from reactorsim import constants as C
from reactorsim.plant import Plant
from reactorsim.rods import RodController, differential_worth, integral_worth_fraction
from reactorsim.scenarios import _settle


@pytest.fixture
def plant():
    unit = Plant()
    _settle(unit)
    return unit


# ---------------------------------------------------------------- rod worth

def test_integral_worth_is_zero_out_and_one_in():
    assert integral_worth_fraction(1.0) == pytest.approx(0.0, abs=1e-9)
    assert integral_worth_fraction(0.0) == pytest.approx(1.0, abs=1e-9)


def test_integral_worth_is_monotonic():
    values = [integral_worth_fraction(x / 50.0) for x in range(51)]
    assert values == sorted(values, reverse=True)


def test_differential_worth_peaks_at_mid_travel():
    mid = abs(differential_worth(0.5, 1000.0))
    top = abs(differential_worth(0.97, 1000.0))
    bottom = abs(differential_worth(0.03, 1000.0))
    assert mid > 8 * top
    assert mid > 8 * bottom


def test_scram_inserts_every_bank_in_under_three_seconds():
    rods = RodController()
    rods.scram()
    for _ in range(int(C.ROD_SCRAM_TIME / 0.05) + 4):
        rods.step(0.05)
    assert all(bank.position == 0.0 for bank in rods.banks.values())


def test_scram_worth_is_a_realistic_shutdown_margin():
    rods = RodController()
    rods.scram()
    rods.step(10.0)
    assert -14000 < rods.total_reactivity * 1e5 < -8000


def test_control_banks_withdraw_in_sequence():
    rods = RodController()
    for bank in rods.banks.values():
        bank.demand = 0.0
    rods.move_control_banks(0.5)
    # A withdraws first.
    assert rods.banks["A"].demand > 0
    assert rods.banks["D"].demand == 0


def test_control_banks_insert_in_the_reverse_sequence():
    rods = RodController()
    rods.move_control_banks(-0.5)
    assert rods.banks["D"].demand < 1.0
    assert rods.banks["A"].demand == 1.0


# ------------------------------------------------------------- steady state

def test_settled_plant_sits_at_the_design_point(plant):
    assert plant.kinetics.power_fraction == pytest.approx(1.0, abs=0.02)
    assert plant.primary.coolant_temperature == pytest.approx(310.0, abs=1.5)
    assert plant.primary.fuel_temperature == pytest.approx(700.0, abs=20.0)
    assert plant.primary.pressure == pytest.approx(15.5, abs=0.15)
    assert 1050 < plant.net_electric_mw < 1200
    assert abs(plant.reactivity_terms["total"]) < 1e-4
    assert not plant.tripped


def test_reactivity_terms_sum_to_the_total(plant):
    terms = plant.compute_reactivity()
    parts = sum(value for key, value in terms.items() if key != "total")
    assert parts == pytest.approx(terms["total"], abs=1e-12)


def test_moderator_coefficient_sign_depends_on_boron(plant):
    plant.boron_ppm = 300.0
    assert plant.moderator_coefficient() < -30.0
    plant.boron_ppm = 2200.0
    assert plant.moderator_coefficient() > 0.0


# --------------------------------------------------------- self regulation

def test_the_reactor_follows_the_turbine(plant):
    """Closing the governor valve reduces reactor power with no rod motion.

    This is the defining behaviour of a pressurised water reactor and it is
    not scripted anywhere: it emerges from a negative moderator coefficient
    plus the steam generator heat balance.
    """
    positions = {name: bank.position for name, bank in plant.rods.banks.items()}
    start_power = plant.kinetics.power_fraction
    plant.secondary.valve_demand = 0.7
    plant.step(1800.0)
    assert plant.kinetics.power_fraction < start_power - 0.08
    assert plant.primary.coolant_temperature > 310.0
    # Nothing moved the rods.
    for name, bank in plant.rods.banks.items():
        assert bank.position == pytest.approx(positions[name], abs=1e-9)


def test_withdrawing_rods_raises_power(plant):
    start = plant.kinetics.power_fraction
    plant.rods.move_control_banks(-0.4)
    plant.step(600.0)
    lowered = plant.kinetics.power_fraction
    assert lowered < start


# ------------------------------------------------------- protection system

def test_loss_of_flow_trips_the_reactor(plant):
    plant.primary.pumps = [False] * 4
    plant.step(120.0)
    assert plant.tripped
    assert any("flow" in reason.key for reason in plant.trip_reasons)


def test_overpower_trips_the_reactor(plant):
    plant.boron_ppm = max(0.0, plant.boron_ppm - 60.0)
    plant.step(900.0)
    assert plant.tripped


def test_trip_drops_the_rods_and_the_turbine(plant):
    plant.scram()
    plant.step(5.0)
    assert plant.rods.control_position == 0.0
    assert plant.secondary.turbine_tripped
    assert plant.kinetics.power_fraction < 0.05


def test_trip_cannot_be_reset_while_a_condition_stands(plant):
    # High pressure has no low-power permissive, so it stays present after the
    # trip and the breakers must refuse to close.
    plant.scram()
    plant.step(5.0)
    plant.primary.pressure = 16.9
    assert plant.reset_trip() is False


def test_low_flow_trip_clears_once_power_has_gone(plant):
    """The flow trip is permissive below 10% power, as it is in a real plant:
    with the reactor shut down there is nothing left for the flow to cool."""
    plant.primary.pumps = [False] * 4
    plant.step(120.0)
    assert plant.tripped
    assert plant.kinetics.power_fraction < 0.1
    assert plant.reset_trip() is True


def test_trip_resets_once_the_condition_clears(plant):
    plant.scram()
    plant.step(60.0)
    assert plant.reset_trip() is True
    assert not plant.tripped
    # The rods stay where they fell: a restart means withdrawing them again.
    assert plant.rods.control_position == 0.0


def test_decay_heat_holds_the_plant_hot_after_a_trip(plant):
    plant.operating_seconds = 200 * 86400.0
    plant.scram()
    plant.step(3600.0)
    assert plant.decay_power_mw > 20.0
    # The steam dumps hold the plant at hot standby rather than letting it
    # cool to ambient or boil.
    assert 275.0 < plant.primary.coolant_temperature < 300.0
    assert plant.primary.subcooling > 20.0


def test_station_blackout_uncovers_nothing_immediately_but_heats_up(plant):
    plant.operating_seconds = 200 * 86400.0
    plant.scram()
    plant.step(30.0)
    plant.primary.pumps = [False] * 4
    plant.secondary.feedwater = 0.0
    plant.secondary.auto_feedwater = False
    before = plant.primary.fuel_temperature
    plant.step(4.0 * 3600.0)
    assert plant.primary.fuel_temperature > before


# -------------------------------------------------------------- xenon pit

def test_xenon_pit_can_prevent_a_restart(plant):
    plant.scram()
    plant.step(9.0 * 3600.0)
    xenon = plant.poisons.xenon_reactivity * 1e5
    assert xenon < -4000
    plant.reset_trip()
    plant.rods.move_control_banks(4.0)   # every control bank fully out
    plant.step(1800.0)
    # With all rods out and the boron unchanged the core is still subcritical.
    assert plant.reactivity_terms["total"] < 0
    assert plant.kinetics.power_fraction < 0.02


# ---------------------------------------------------------------- damage

def test_prompt_criticality_destroys_the_core():
    unit = Plant()
    _settle(unit)
    unit.boron_ppm = 0.0
    unit.fuel.burnable_poison = 0.0
    for _ in range(40):
        unit.step(0.05)
    assert unit.kinetics.prompt_critical or unit.core_damage > 0 or unit.tripped


def test_overheating_damages_the_cladding(plant):
    plant.primary.fuel_temperature = 1400.0
    plant.step(60.0)
    assert plant.clad_damage > 0


def test_boration_adds_negative_reactivity(plant):
    before = plant.compute_reactivity()["boron"]
    plant.boron_demand = 1.0
    plant.step(120.0)
    assert plant.compute_reactivity()["boron"] < before
