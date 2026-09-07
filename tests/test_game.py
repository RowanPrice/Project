"""The game as a whole: scenarios, actions, state, and long-run stability."""

import json

import pytest

from reactorsim.game import SPEEDS, Game
from reactorsim.scenarios import SCENARIOS


@pytest.fixture
def game():
    return Game(seed=1234, scenario="full_power")


# ----------------------------------------------------------------- scenarios

@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_scenario_builds(name):
    unit = Game(seed=99, scenario=name)
    state = unit.state()
    assert state["scenario"] == name
    assert not state["game_over"]
    json.dumps(state)          # the interface has to be able to send it


@pytest.mark.parametrize("name", ["full_power", "load_follow", "blackout", "sandbox"])
def test_at_power_scenarios_start_at_full_power(name):
    unit = Game(seed=99, scenario=name)
    assert unit.plant.kinetics.power_fraction == pytest.approx(1.0, abs=0.02)
    assert 1050 < unit.plant.net_electric_mw < 1200
    assert not unit.plant.tripped


def test_commissioning_starts_cold_and_shut_down():
    unit = Game(seed=99, scenario="commissioning")
    assert unit.plant.primary.coolant_temperature < 60.0
    assert unit.plant.kinetics.power_fraction < 1e-4
    assert unit.plant.compute_reactivity()["total"] < -0.05


def test_endurance_starts_late_in_the_cycle():
    unit = Game(seed=99, scenario="endurance")
    assert unit.plant.fuel.burnup > 30.0
    # Boron is nearly exhausted as a control mechanism by end of cycle.
    assert unit.plant.boron_ppm < 700.0


def test_xenon_pit_starts_poisoned():
    unit = Game(seed=99, scenario="xenon_pit")
    assert unit.plant.poisons.xenon_reactivity * 1e5 < -3800


# ------------------------------------------------------------------- actions

def test_unknown_action_is_rejected(game):
    assert game.act("wibble")["ok"] is False


def test_speed_control(game):
    for speed in SPEEDS:
        assert game.act("set_speed", {"speed": speed})["ok"]
    assert game.act("set_speed", {"speed": 7})["ok"] is False


def test_speed_is_capped_while_abnormal(game):
    game.act("set_speed", {"speed": 240})
    assert game.effective_speed == 240
    game.act("scram")
    assert game.effective_speed <= 5


def test_scram_and_reset(game):
    assert game.act("scram")["ok"]
    assert game.plant.tripped
    game.advance(120.0)
    assert game.act("reset_trip")["ok"]
    assert not game.plant.tripped


def test_rod_motion_moves_the_group(game):
    before = game.plant.rods.control_position
    game.act("move_rods", {"delta": -5})
    game.advance(30.0)
    assert game.plant.rods.control_position < before


def test_pump_can_be_stopped_and_started(game):
    assert game.act("pump", {"index": 0, "on": False})["ok"]
    assert game.plant.primary.pumps[0] is False
    assert game.act("pump", {"index": 9, "on": False})["ok"] is False


def test_turbine_demand_is_clamped(game):
    game.act("turbine", {"demand": 5.0})
    assert game.plant.secondary.valve_demand == 1.0
    game.act("turbine", {"demand": -1.0})
    assert game.plant.secondary.valve_demand == 0.0


def test_boron_demand(game):
    game.act("boron", {"demand": 1})
    assert game.plant.boron_demand == 1.0
    before = game.plant.boron_ppm
    game.advance(60.0)
    assert game.plant.boron_ppm > before


def test_battery_commands(game):
    game.act("battery", {"power": -150, "frequency_response": True})
    assert game.battery.power_demand_mw == -150
    assert game.battery.frequency_response is True


def test_enrichment_quote_and_order(game):
    quote = game.act("quote_enrichment", {"kg": 26000, "assay": 4.5, "tails": 0.25})
    assert quote["ok"] and quote["quote"]["swu"] > 0
    # 26 tonnes of fuel costs more than the plant has in petty cash.
    result = game.act("order_enrichment", {"kg": 26000, "assay": 4.5, "tails": 0.25})
    assert result["ok"] is False
    small = game.act("order_enrichment", {"kg": 2000, "assay": 4.5, "tails": 0.25})
    assert small["ok"] is True
    assert game.enrichment_job is not None


def test_enrichment_rejects_weapons_grade_requests(game):
    assert game.act("order_enrichment", {"kg": 100, "assay": 90})["ok"] is False


def test_enrichment_rejects_tails_below_the_cascade_floor(game):
    assert game.act("order_enrichment", {"kg": 100, "assay": 4.5, "tails": 0.05})["ok"] is False


def test_refuelling_needs_cold_shutdown_and_fuel(game):
    result = game.act("refuel")
    assert result["ok"] is False


def test_upgrades_cost_money_and_take_time(game):
    cash = game.finance.cash
    result = game.act("purchase_upgrade", {"key": "steam_dumps"})
    assert result["ok"]
    assert game.finance.cash < cash
    assert game.research.upgrades["steam_dumps"].installed is False
    game.advance(6 * 86400.0)
    assert game.research.upgrades["steam_dumps"].installed is True
    assert game.plant.secondary.dump_capacity > 0.45


def test_upgrade_prerequisites_are_enforced_through_the_action(game):
    assert game.act("purchase_upgrade", {"key": "grey_rods"})["ok"] is False


def test_contracts_can_be_signed_and_abandoned(game):
    game.advance(60.0)
    assert game.offers
    key = game.offers[0].key
    assert game.act("accept_contract", {"key": key})["ok"]
    assert any(c.key == key for c in game.contracts)
    assert game.act("abandon_contract", {"key": key})["ok"]


def test_repairs_take_the_component_out_of_service(game):
    assert game.act("repair", {"key": "condenser"})["ok"]
    assert game.maintenance.components["condenser"].under_repair


# ---------------------------------------------------------------- behaviour

def test_a_day_at_power_makes_money(game):
    cash = game.finance.cash
    game.advance(86400.0)
    assert game.finance.cash > cash
    assert game.energy_delivered_mwh > 20_000


def test_a_week_unattended_stays_stable(game):
    worst = 0.0
    for _ in range(7 * 24 * 12):
        game.advance(300.0)
        worst = max(worst, abs(game.grid.frequency - 50.0))
    assert not game.plant.tripped
    assert not game.game_over
    assert worst < 0.9, f"grid frequency excursion of {worst:.2f} Hz"
    assert game.plant.fuel.burnup > 0.15


def test_tripping_costs_reputation_and_safety_score(game):
    score = game.maintenance.safety_score
    game.act("scram")
    game.advance(10.0)
    assert game.maintenance.trips == 1
    assert game.maintenance.safety_score < score


def test_state_is_json_serialisable_and_complete(game):
    state = game.state()
    for section in ("clock", "reactor", "thermal", "electrical", "grid",
                    "finance", "contracts", "fuel", "maintenance", "research",
                    "alarms", "log", "score"):
        assert section in state
    json.dumps(state)


def test_save_produces_valid_json(game):
    game.advance(600.0)
    payload = json.loads(game.save())
    assert payload["version"] == 2
    assert payload["seed"] == game.seed
    assert "plant" in payload and "finance" in payload


def test_xenon_forecast_integrates_forward(game):
    forecast = game.xenon_forecast(hours=12.0, points=12)
    assert len(forecast) == 13
    assert forecast[0]["pcm"] == pytest.approx(
        game.plant.poisons.xenon_reactivity * 1e5, rel=1e-6)
    # Forecasting must not disturb the real core.
    before = game.plant.poisons.xenon
    game.xenon_forecast()
    assert game.plant.poisons.xenon == before


def test_the_same_seed_gives_the_same_run():
    first = Game(seed=42, scenario="full_power")
    second = Game(seed=42, scenario="full_power")
    for _ in range(200):
        first.advance(60.0)
        second.advance(60.0)
    assert first.finance.cash == pytest.approx(second.finance.cash)
    assert first.grid.spot_price == pytest.approx(second.grid.spot_price)
    assert first.plant.kinetics.power_fraction == pytest.approx(
        second.plant.kinetics.power_fraction)
