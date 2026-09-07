"""Enrichment economics, contracts, the grid market, and the books."""

import random

import pytest

from reactorsim.economy import Contract, Finance, contract_catalogue
from reactorsim.grid import GridModel
from reactorsim.research import (
    FuelMarket,
    ResearchProgramme,
    enrichment_requirements,
    swu_value,
)
from reactorsim.storage import Battery

# Separative work for 1 kg of product from natural uranium at 0.711%:
# (product assay, tails assay) -> (feed kg, SWU). The 4.5% / 0.25% pair is the
# industry benchmark quoted everywhere -- 9.22 kg of natural uranium and 6.87
# SWU per kilogram of fuel -- and the rest follow from the same definition.
SWU_TABLE = [
    (2.0, 0.25, 3.80, 1.92),
    (3.0, 0.25, 5.97, 3.81),
    (4.5, 0.25, 9.22, 6.87),
    (5.0, 0.25, 10.30, 7.92),
    (4.5, 0.30, 10.22, 6.23),
    (4.5, 0.15, 7.75, 8.80),
]


@pytest.mark.parametrize("assay,tails,feed,swu", SWU_TABLE)
def test_separative_work_matches_published_tables(assay, tails, feed, swu):
    got_feed, got_swu = enrichment_requirements(1.0, assay, tails_assay=tails)
    assert got_feed == pytest.approx(feed, rel=0.02)
    assert got_swu == pytest.approx(swu, rel=0.02)


def test_swu_value_function_is_symmetric_about_a_half():
    assert swu_value(0.3) == pytest.approx(swu_value(0.7), rel=1e-9)


def test_lower_tails_assay_trades_uranium_for_separative_work():
    lean_feed, lean_swu = enrichment_requirements(1.0, 4.5, tails_assay=0.15)
    rich_feed, rich_swu = enrichment_requirements(1.0, 4.5, tails_assay=0.35)
    assert lean_feed < rich_feed      # less natural uranium needed
    assert lean_swu > rich_swu        # but more work to get it


def test_enrichment_requires_a_sensible_assay_ordering():
    with pytest.raises(ValueError):
        enrichment_requirements(1.0, 0.5)          # product below feed
    with pytest.raises(ValueError):
        enrichment_requirements(1.0, 4.5, tails_assay=0.9)


def test_quote_adds_up():
    market = FuelMarket()
    quote = market.quote(1000.0, 4.5, 0.25)
    total = (quote["uranium_cost"] + quote["conversion_cost"]
             + quote["swu_cost"] + quote["fabrication_cost"])
    assert quote["total"] == pytest.approx(total)
    assert quote["cost_per_kg"] == pytest.approx(total / 1000.0)


def test_cascade_upgrade_reduces_separative_work_cost():
    market = FuelMarket()
    plain = market.quote(1000.0, 4.5, 0.25, swu_efficiency=1.0)
    better = market.quote(1000.0, 4.5, 0.25, swu_efficiency=0.85)
    assert better["swu_cost"] < plain["swu_cost"]
    assert better["uranium_cost"] == pytest.approx(plain["uranium_cost"])


# ------------------------------------------------------------------ upgrades

def test_upgrade_prerequisites_are_enforced():
    programme = ResearchProgramme()
    assert programme.purchase("grey_rods", 0.0) is None
    assert programme.purchase("auto_rod_control", 0.0) is not None


def test_modifiers_apply_only_once_installed():
    programme = ResearchProgramme()
    assert programme.modifiers["swu_efficiency"] == 1.0
    programme.purchase("cascade_stages", 0.0)
    assert programme.modifiers["swu_efficiency"] == 1.0   # still installing
    programme.step(60.0 * 86400.0)
    assert programme.modifiers["swu_efficiency"] == pytest.approx(0.85)


def test_multiplicative_and_additive_effects_combine_correctly():
    programme = ResearchProgramme()
    programme.purchase("cascade_stages", 0.0)
    programme.purchase("battery_expansion", 0.0)
    programme.step(60.0 * 86400.0)
    modifiers = programme.modifiers
    assert modifiers["swu_efficiency"] == pytest.approx(0.85)      # multiplied
    assert modifiers["battery_capacity"] == pytest.approx(300.0)   # added


# ----------------------------------------------------------------- contracts

def test_baseload_contract_requires_a_flat_block():
    grid = GridModel()
    contract = Contract(
        key="t", kind="baseload", title="t", description="",
        capacity_mw=900.0, strike_price=60.0, duration_days=1.0,
        shortfall_penalty=100.0)
    contract.active = True
    for hour in range(24):
        assert contract.required_mw(hour * 3600.0, grid) == 900.0


def test_peaking_contract_only_wants_the_evening():
    grid = GridModel()
    contract = Contract(
        key="t", kind="peaking", title="t", description="",
        capacity_mw=1000.0, strike_price=200.0, duration_days=1.0,
        shortfall_penalty=400.0)
    contract.active = True
    assert contract.required_mw(10 * 3600.0, grid) == 0.0
    assert contract.required_mw(18 * 3600.0, grid) == 1000.0


def test_load_following_tracks_national_demand():
    grid = GridModel()
    contract = Contract(
        key="t", kind="load_following", title="t", description="",
        capacity_mw=1000.0, strike_price=90.0, duration_days=1.0,
        shortfall_penalty=190.0)
    contract.active = True
    overnight = contract.required_mw(3.5 * 3600.0, grid)
    evening = contract.required_mw(18.2 * 3600.0, grid)
    assert 550.0 <= overnight < evening <= 1000.0


def test_settlement_pays_for_delivery_and_penalises_shortfall():
    grid = GridModel()
    contract = Contract(
        key="t", kind="baseload", title="t", description="",
        capacity_mw=900.0, strike_price=60.0, duration_days=1.0,
        shortfall_penalty=100.0)
    contract.active = True
    taken, income, penalty = contract.settle(0.0, 900.0, 3600.0, grid)
    assert taken == 900.0
    assert income == pytest.approx(900 * 60.0)
    assert penalty == 0.0

    taken, income, penalty = contract.settle(3600.0, 400.0, 3600.0, grid)
    assert taken == 400.0
    assert income == pytest.approx(400 * 60.0)
    assert penalty == pytest.approx(500 * 100.0)
    assert contract.delivery_rate == pytest.approx(1300.0 / 1800.0, rel=1e-6)


def test_catalogue_offers_are_distinct_and_priced():
    offers = contract_catalogue(random.Random(3), 0)
    assert len({offer.kind for offer in offers}) >= 4
    assert all(offer.strike_price > 0 for offer in offers)
    assert all(offer.shortfall_penalty > 0 for offer in offers)


# --------------------------------------------------------------------- grid

def test_demand_curve_is_continuous_across_midnight():
    grid = GridModel()
    before = grid.demand_profile(4 * 86400.0 - 1.0)
    after = grid.demand_profile(4 * 86400.0 + 1.0)
    assert abs(after - before) < 20.0


def test_demand_peaks_in_the_evening_and_troughs_overnight():
    grid = GridModel()
    trough = grid.demand_profile(3.5 * 3600.0)
    peak = grid.demand_profile(18.2 * 3600.0)
    assert peak > trough * 1.25


def test_frequency_stays_near_nominal_when_supply_matches():
    grid = GridModel()
    for _ in range(4000):
        grid.step(1100.0, 5.0)
    assert abs(grid.frequency - 50.0) < 0.35


def test_losing_the_plant_drops_frequency():
    grid = GridModel()
    for _ in range(600):
        grid.step(1100.0, 1.0)
    for _ in range(20):
        grid.step(0.0, 1.0)
    assert grid.frequency < 49.8


def test_prices_go_negative_when_the_system_is_long():
    """A windy night: plenty of generation, nobody awake to use it."""
    grid = GridModel()
    grid.wind_factor = 1.0
    grid.demand_mw = 26_000.0
    for _ in range(600):
        grid._step_price(1100.0, 30.0)
    assert grid.spot_price < 0.0


def test_prices_spike_when_the_system_is_short():
    """A still winter evening: everything is running and it is still tight."""
    grid = GridModel()
    grid.wind_factor = 0.05
    grid.demand_mw = 42_000.0
    for _ in range(600):
        grid._step_price(1100.0, 30.0)
    assert grid.spot_price > 180.0


# ------------------------------------------------------------------ battery

def test_battery_round_trip_efficiency_is_the_square_of_the_one_way():
    """Charge a block of energy in, take the same block back out, compare."""
    battery = Battery(charge_mwh=100.0)
    start = battery.charge_mwh
    battery.power_demand_mw = -100.0
    taken_in = 0.0
    for _ in range(3600):
        taken_in -= battery.step(1.0) / 3600.0
    battery.power_demand_mw = 100.0
    given_back = 0.0
    while battery.charge_mwh > start + 1e-6:
        given_back += battery.step(1.0) / 3600.0
    assert given_back < taken_in
    assert given_back / taken_in == pytest.approx(0.94 ** 2, rel=0.03)


def test_battery_cannot_discharge_when_empty():
    battery = Battery(charge_mwh=0.0)
    battery.power_demand_mw = 200.0
    for _ in range(10):
        battery.step(1.0)
    assert battery.power_mw == pytest.approx(0.0, abs=1e-6)


def test_battery_degrades_with_cycling():
    battery = Battery()
    start = battery.health
    for _ in range(6):
        battery.power_demand_mw = -200.0
        for _ in range(3600):
            battery.step(1.0)
        battery.power_demand_mw = 200.0
        for _ in range(3600):
            battery.step(1.0)
    assert battery.health < start
    assert battery.replacement_cost() > 0


def test_frequency_response_discharges_on_low_frequency():
    battery = Battery()
    battery.frequency_response = True
    battery.step(1.0, 49.5)
    assert battery.power_mw > 100.0
    battery.step(1.0, 50.5)
    assert battery.power_mw < 0.0


def test_frequency_response_has_a_deadband():
    battery = Battery()
    battery.frequency_response = True
    battery.step(1.0, 50.005)
    assert battery.power_mw == pytest.approx(0.0, abs=1e-6)


# ------------------------------------------------------------------ finance

def test_ledger_tracks_income_and_costs():
    finance = Finance(cash=1_000_000.0)
    finance.record(0.0, "energy", "sales", 250_000.0)
    finance.record(0.0, "fuel", "fuel", -100_000.0)
    assert finance.cash == pytest.approx(1_150_000.0)
    assert finance.lifetime_income == pytest.approx(250_000.0)
    assert finance.lifetime_costs == pytest.approx(100_000.0)


def test_fines_cost_reputation():
    finance = Finance()
    before = finance.reputation
    finance.fine(0.0, "test", 500_000.0)
    assert finance.reputation < before
    assert finance.fines == 500_000.0


def test_decommissioning_levy_is_ring_fenced():
    finance = Finance()
    finance.levy(0.0, 1000.0)
    assert finance.decommissioning_fund == pytest.approx(2400.0)
    assert finance.cash < 12_000_000.0
