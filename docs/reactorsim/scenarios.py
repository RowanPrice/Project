"""Starting conditions.

Each scenario sets the plant up in a particular state and gives the player a
different problem.  They share one simulation -- nothing here is scripted, and
nothing is on rails.  A scenario is a set of initial conditions and a
commercial position, and after that the physics is on its own.
"""

from __future__ import annotations

import random

from . import constants as C
from .economy import Contract, contract_catalogue

DAY = 86400.0


def _settle(plant, target_power: float = 1.0, cycles: int = 10) -> None:
    """Find the boron concentration at which the plant is steady at a power.

    Trimming boron once is not enough.  Boron changes the moderator
    coefficient, which changes the temperature the plant settles at, which
    changes the Doppler term, which changes the reactivity again.  Worse, the
    reactor has no preferred power of its own: it sits wherever total
    reactivity is zero, and that could be 105% as easily as 100%.

    So this alternates two corrections until both are satisfied -- trim boron
    to make the core exactly critical where it stands, then nudge boron by the
    power error to move where "where it stands" is.  Eight or ten passes puts
    the plant within a fraction of a percent of the requested power.
    """
    plant.kinetics.set_equilibrium(target_power)
    plant.primary.fuel_temperature = C.NOMINAL_FUEL_TEMP
    plant.primary.coolant_temperature = C.NOMINAL_COOLANT_TEMP
    plant.primary.pressure = C.NOMINAL_PRIMARY_PRESSURE
    plant.secondary.steam_pressure = C.NOMINAL_STEAM_PRESSURE
    plant.secondary.valve_demand = target_power
    plant.secondary.turbine_valve = target_power
    plant.primary.sync()
    plant.trim_boron_for_criticality()
    for _ in range(cycles):
        plant.stabilise(1200.0)
        error = plant.kinetics.power_fraction - target_power
        if abs(error) < 0.002:
            break
        # Note that the boron is NOT re-trimmed inside the loop: the plant
        # finds zero reactivity by itself through temperature feedback, which
        # is the whole point of a negative moderator coefficient. All this
        # does is choose which power it finds it at.
        plant.boron_ppm = max(0.0, plant.boron_ppm + error * 150.0)
    plant.stabilise(1800.0)
    plant.primary.vessel_stress = 0.0


def _hot_full_power(game) -> None:
    plant = game.plant
    plant.poisons.set_equilibrium(1.0)
    _settle(plant)


def _cold_shutdown(game) -> None:
    plant = game.plant
    plant.kinetics.set_equilibrium(1e-9)
    plant.poisons.iodine = 0.0
    plant.poisons.xenon = 0.0
    plant.poisons.samarium = 0.0
    plant.operating_seconds = 0.0
    plant.power_at_trip = 0.0
    plant.primary.fuel_temperature = 40.0
    plant.primary.coolant_temperature = 40.0
    plant.primary.pressure = 2.6
    # The secondary side is cold too -- if it were not, the steam generators
    # would be heating the primary circuit instead of cooling it.
    plant.secondary.steam_pressure = 0.0074
    plant.secondary.sg_inventory = 1.0
    plant.secondary.dump_setpoint = 1.0
    plant.secondary.valve_demand = 0.0
    plant.secondary.turbine_valve = 0.0
    plant.secondary.trip_turbine()
    plant.rods.scram()
    plant.rods.step(10.0)
    plant.rods.reset()
    plant.boron_ppm = 2100.0
    plant.tripped = False
    plant.primary.sync()


def _ramp_to(game, target: float, seconds: float = 5400.0) -> None:
    """Walk the plant to a new power the way a real downpower is done.

    Turbine load and reactor power come down together, a couple of percent a
    minute.  Doing it in one step does not work and should not: the steam
    dumps can only take about 45% of rated flow, so dropping the turbine from
    100% to 20% instantly leaves 55% of 3400 MW with nowhere to go, and the
    core outlet temperature reaches the trip setpoint in under three minutes.
    That is not a modelling artefact -- it is why plants have runback logic.
    """
    plant = game.plant
    steps = max(1, int(seconds // 30))
    start = plant.secondary.valve_demand
    ramp_steps = max(1, int(steps * 0.8))
    for index in range(steps):
        fraction = min(1.0, (index + 1) / ramp_steps)
        plant.secondary.valve_demand = start + (target - start) * fraction
        error = plant.secondary.valve_demand - plant.kinetics.power_fraction
        delta = max(-0.004, min(0.004, error * 0.05))
        plant.rods.move_control_banks(delta)
        plant.step(30.0)


def _hold_at(game, target: float, seconds: float) -> None:
    """Hold a power level, trimming boron the way the chemistry team would.

    Holding a reduced power after a downpower is not passive: xenon keeps
    building for hours and the reactivity has to come from somewhere. Here it
    comes from dilution, which is exactly what it costs the player later --
    boron spent now is boron unavailable for the recovery.
    """
    plant = game.plant
    chunks = max(1, int(seconds // 300))
    for _ in range(chunks):
        plant.step(300.0)
        error = target - plant.kinetics.power_fraction
        plant.boron_ppm = max(0.0, plant.boron_ppm - error * 55.0)


def setup_commissioning(game) -> None:
    """Fresh core, cold plant, empty order book.  Start it up yourself."""
    _cold_shutdown(game)
    game.finance.cash = 9_000_000.0
    game.finance.reputation = 12.0
    game.fuel_store_kg = 4_000.0
    game.speed = 5


def setup_full_power(game) -> None:
    """The normal way to play: a running plant and a book to fill."""
    _hot_full_power(game)
    game.finance.cash = 14_000_000.0
    game.finance.reputation = 30.0
    game.fuel_store_kg = 8_000.0
    offer = next(
        c for c in contract_catalogue(random.Random(11), 0) if c.kind == "baseload"
    )
    offer.active = True
    offer.accepted_at = 0.0
    game.contracts.append(offer)


def setup_xenon_pit(game) -> None:
    """The transient that has killed people.

    The plant has spent a week at full power and has just been dropped to 20%
    for a grid instruction that has now been cancelled.  Iodine-135 laid down
    at full power is still decaying into xenon-135, but the flux that was
    burning the xenon out has gone.  Xenon worth is climbing towards -5000 pcm
    and will not peak for another eight hours.

    There is a peaking contract that needs 1100 MW at four this afternoon.
    Getting there means winning a race against a poison you cannot see, using
    reactivity you may not have.  The one thing you must not do is chase it by
    pulling rods until the core is bare -- that is precisely the configuration
    Chernobyl-4 was in when it was destroyed.
    """
    plant = game.plant
    plant.poisons.set_equilibrium(1.0)
    plant.fuel.burnup = 9.5
    plant.fuel.burnable_poison = 0.31
    _settle(plant)
    # Drop to 20% and let the poison start to build.
    _ramp_to(game, 0.20, 3600.0)
    _hold_at(game, 0.20, 3.0 * 3600.0)
    game.grid.time = 8.0 * 3600.0
    game.finance.cash = 16_000_000.0
    game.finance.reputation = 55.0
    game.fuel_store_kg = 8_000.0

    peak = Contract(
        key="scenario-peak",
        kind="peaking",
        title="Evening Peak Cover (contracted)",
        description=(
            "1100 MW from 16:00 to 20:30, today and for the next five days. "
            "The penalty for not being there is 430 pounds a megawatt-hour."
        ),
        capacity_mw=1100.0,
        strike_price=228.0,
        duration_days=5.0,
        shortfall_penalty=430.0,
        completion_bonus=600_000.0,
        collateral=450_000.0,
        reputation=12.0,
    )
    peak.active = True
    peak.accepted_at = game.grid.time
    game.contracts.append(peak)


def setup_blackout(game) -> None:
    """Full power, and in a few minutes the grid disappears.

    Offsite power is about to be lost.  The diesels may or may not start.  The
    reactor will trip, but tripping it is the easy part: 220 MW of decay heat
    has to go somewhere for the next several hours, and if it does not, the
    core is uncovered in about ninety minutes.
    """
    _hot_full_power(game)
    game.finance.cash = 20_000_000.0
    game.finance.reputation = 60.0
    game.fuel_store_kg = 8_000.0
    offsite = game.maintenance.components["offsite"]
    offsite.health = 0.02
    offsite.hazard_per_day = 260.0
    game.note("warning",
              "Grid operator reports severe weather on the transmission "
              "corridor. Offsite power may be lost at any moment.")


def setup_load_follow(game) -> None:
    """A week of following national demand with a reactor that hates it."""
    _hot_full_power(game)
    game.finance.cash = 15_000_000.0
    game.finance.reputation = 45.0
    game.fuel_store_kg = 8_000.0
    offer = next(
        c for c in contract_catalogue(random.Random(7), 0)
        if c.kind == "load_following"
    )
    offer.active = True
    offer.accepted_at = 0.0
    game.contracts.append(offer)
    game.grid.time = 22.0 * 3600.0


def setup_endurance(game) -> None:
    """A full fuel cycle. Refuel before the core runs out of reactivity."""
    _hot_full_power(game)
    game.plant.fuel.burnup = 34.0
    game.plant.fuel.burnable_poison = 0.014
    _settle(game.plant)
    game.finance.cash = 22_000_000.0
    game.finance.reputation = 60.0
    game.fuel_store_kg = 0.0
    game.note("warning",
              "The core is 34 GWd/tU through a 50 GWd/tU cycle. Boron is nearly "
              "exhausted as a control mechanism and the control banks are the "
              "only reactivity left. Order fuel and plan the outage before the "
              "core coasts down on its own.")


def setup_sandbox(game) -> None:
    """No contracts, no regulator, unlimited money. Break things on purpose."""
    _hot_full_power(game)
    game.finance.cash = 500_000_000.0
    game.finance.reputation = 100.0
    game.fuel_store_kg = 200_000.0
    game.maintenance.next_inspection = 1e12
    for component in game.maintenance.components.values():
        component.wear_per_day = 0.0
        component.hazard_per_day = 0.0
    game.note("info",
              "Sandbox. Nothing here is watching you. Try withdrawing every "
              "bank at once and see how much reactivity it takes to go prompt "
              "critical -- the answer is 650 pcm, and the core will not survive "
              "the demonstration.")


SCENARIOS: dict[str, dict] = {
    "commissioning": {
        "name": "Commissioning",
        "difficulty": "Tutorial",
        "setup": setup_commissioning,
        "briefing": (
            "Cold plant, fresh core, nothing sold. Start the coolant pumps, warm "
            "the primary circuit with pump heat, dilute boron and pull rods to "
            "criticality, then take the turbine up. Watch the reactor period: "
            "anything shorter than about thirty seconds means you are adding "
            "reactivity faster than you can take it back."
        ),
    },
    "full_power": {
        "name": "Baseload Operation",
        "difficulty": "Standard",
        "setup": setup_full_power,
        "briefing": (
            "The plant is at full power with a baseload block already signed. "
            "Keep it there, keep the plant maintained, and sign what else you "
            "can carry. The money is in the contracts you take on top."
        ),
    },
    "load_follow": {
        "name": "Load Following",
        "difficulty": "Hard",
        "setup": setup_load_follow,
        "briefing": (
            "A week of tracking national demand between 55% and 100% of 1000 MW. "
            "Every reduction builds xenon that limits how fast you can come back "
            "up. Plan the recovery before you start down, and use boron for the "
            "slow half of the job."
        ),
    },
    "xenon_pit": {
        "name": "The Xenon Pit",
        "difficulty": "Hard",
        "setup": setup_xenon_pit,
        "briefing": (
            "You came down to 20% three hours ago and xenon is climbing. Peak "
            "cover is contracted for 16:00 at 1100 MW. Work out whether you can "
            "get there on the reactivity you have -- and if you cannot, say so "
            "early rather than pulling every rod out to find out."
        ),
    },
    "blackout": {
        "name": "Station Blackout",
        "difficulty": "Brutal",
        "setup": setup_blackout,
        "briefing": (
            "Full power, and the transmission line is about to go. Once offsite "
            "power is lost you will have whatever the diesels give you and the "
            "decay heat will not wait. Everything you do in the first ten "
            "minutes decides how the next six hours go."
        ),
    },
    "endurance": {
        "name": "End of Cycle",
        "difficulty": "Hard",
        "setup": setup_endurance,
        "briefing": (
            "Two thirds through the fuel cycle with no fuel on order. Enrichment "
            "takes weeks and an outage takes twenty-two days. Run the numbers "
            "before the core runs out of reactivity and makes the decision for "
            "you."
        ),
    },
    "sandbox": {
        "name": "Sandbox",
        "difficulty": "None",
        "setup": setup_sandbox,
        "briefing": (
            "No contracts, no regulator, no consequences except physical ones. "
            "The physics is exactly the same as every other scenario."
        ),
    },
}
