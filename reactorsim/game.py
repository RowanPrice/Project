"""The game: everything above wired together, plus the rules of play.

``Game`` owns one :class:`~reactorsim.plant.Plant`, one grid, one set of books
and one maintenance record, advances them all on a common clock, and exposes a
single ``act()`` entry point for the interface.  It is deliberately the only
module that knows about all the others.

Time is compressed.  One second of wall clock can be up to 240 seconds of plant
time, because the interesting reactor physics -- xenon, burnup, decay heat --
happens over hours and days while the dangerous physics happens in seconds. The
simulation sub-steps internally so the fast physics stays correct however fast
the clock is running, and the speed control is locked to 1x whenever the plant
is in an abnormal condition, so nobody fast-forwards through an accident.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field

from . import constants as C
from .economy import Contract, Finance, contract_catalogue
from .events import Maintenance
from .grid import GridModel
from .plant import Plant
from .research import FuelMarket, ResearchProgramme, enrichment_requirements
from .storage import Battery
from .thermal import saturation_temperature

DAY = 86400.0
HOUR = 3600.0

SPEEDS = (0, 1, 5, 30, 120, 240)


@dataclass
class LogEntry:
    time: float
    severity: str          # info, warning, alarm, critical
    message: str


@dataclass
class Alarm:
    key: str
    severity: str
    message: str
    acknowledged: bool = False


class Game:
    """One campaign."""

    def __init__(self, seed: int | None = None, scenario: str = "commissioning") -> None:
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed)

        self.plant = Plant()
        self.grid = GridModel()
        self.grid._rng = random.Random(self.seed ^ 0x5EED)
        self.finance = Finance()
        self.battery = Battery()
        self.research = ResearchProgramme()
        self.market = FuelMarket()
        self.maintenance = Maintenance(rng=random.Random(self.seed ^ 0xBEEF))

        self.speed = 1
        self.paused = False
        self.log: list[LogEntry] = []
        self.alarms: dict[str, Alarm] = {}

        self.contracts: list[Contract] = []
        self.offers: list[Contract] = []
        self._offers_refreshed_day = -1

        #: Enriched fuel in store, kg, and its assay.
        self.fuel_store_kg = 0.0
        self.fuel_store_assay = 4.5
        self.tails_assay = 0.25
        self.enrichment_job: dict | None = None

        #: Refuelling outage state.
        self.outage_until: float | None = None
        self.outage_reason = ""

        #: Cumulative statistics.
        self.energy_delivered_mwh = 0.0
        self.spot_energy_mwh = 0.0
        self.uptime_seconds = 0.0
        self.total_seconds = 0.0
        self.game_over = False
        self.game_over_reason = ""

        self._last_real_time = time.monotonic()
        self._diesel_running = False
        self._offsite_power = True
        self._pending_scram_warning = False
        self._peak_output = 0.0

        self.scenario = scenario
        self.apply_scenario(scenario)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def apply_scenario(self, name: str) -> None:
        from .scenarios import SCENARIOS

        setup = SCENARIOS.get(name) or SCENARIOS["commissioning"]
        setup["setup"](self)
        self.scenario = name
        self.note("info", setup["briefing"])

    def note(self, severity: str, message: str) -> None:
        self.log.append(LogEntry(self.grid.time, severity, message))
        if len(self.log) > 300:
            del self.log[:-300]

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------

    @property
    def effective_speed(self) -> int:
        if self.paused or self.game_over:
            return 0
        if self.abnormal and self.speed > 5:
            return 5
        return self.speed

    @property
    def abnormal(self) -> bool:
        """True when the plant is in a condition nobody should skip through."""
        plant = self.plant
        return (
            plant.tripped
            or plant.primary.subcooling < 8.0
            or plant.primary.void_fraction > 0.001
            or plant.core_damage > 0
            or not self._offsite_power
            or plant.kinetics.power_fraction > 1.05
            or abs(self.grid.frequency - 50.0) > 0.35
        )

    def tick(self, real_dt: float | None = None) -> None:
        """Advance the game by one frame of wall-clock time."""
        now = time.monotonic()
        if real_dt is None:
            real_dt = min(now - self._last_real_time, 1.0)
        self._last_real_time = now
        speed = self.effective_speed
        if speed <= 0 or real_dt <= 0:
            return
        # Cap one frame so a stalled browser tab cannot jump the plant an hour.
        self.advance(min(real_dt * speed, 600.0))

    def advance(self, dt: float) -> None:
        """Advance the simulation by ``dt`` seconds of plant time."""
        if self.game_over or dt <= 0:
            return
        remaining = dt
        while remaining > 1e-6:
            step = min(30.0, remaining)
            remaining -= step
            self._advance_once(step)

    # ------------------------------------------------------------------
    # The main loop
    # ------------------------------------------------------------------

    def _advance_once(self, dt: float) -> None:
        modifiers = self.research.modifiers
        self._apply_modifiers(modifiers)

        trips_before = len(self.plant.trip_reasons)
        self.plant.step(dt)
        if len(self.plant.trip_reasons) > trips_before:
            self._on_trip()

        output = self._dispatch(dt, modifiers)
        self.grid.step(output, dt)

        self._step_support_systems(dt, modifiers)
        self._step_business(dt, modifiers)
        self._step_alarms(modifiers)
        self._check_endgame()

        self.total_seconds += dt
        if self.plant.kinetics.power_fraction > 0.5 and not self.plant.tripped:
            self.uptime_seconds += dt

    def _apply_modifiers(self, modifiers: dict[str, float]) -> None:
        """Push research effects into the physics objects."""
        self.plant.rods.set_speed_multiplier(modifiers["rod_speed"])
        self.plant.secondary.dump_capacity = 0.45 * modifiers["dump_capacity"]
        self.plant.rods.automatic = bool(modifiers["auto_rod_control"]) and self.rods_auto
        capacity = 400.0 + modifiers["battery_capacity"]
        if abs(self.battery.nominal_capacity_mwh - capacity) > 1e-6:
            self.battery.nominal_capacity_mwh = capacity
            self.battery.max_power_mw = 200.0 + modifiers["battery_power"]

    rods_auto = False

    def _dispatch(self, dt: float, modifiers: dict[str, float]) -> float:
        """Decide what leaves the site, settle it against contracts."""
        plant_mw = max(0.0, self.plant.net_electric_mw)
        if not self._offsite_power:
            plant_mw = 0.0

        battery_mw = self.battery.step(dt, self.grid.frequency)
        output = max(0.0, plant_mw + battery_mw)
        self._peak_output = max(self._peak_output, output)

        available = output
        hours = dt / HOUR
        now = self.grid.time

        for contract in list(self.contracts):
            if not contract.active:
                continue
            taken, income, penalty = contract.settle(now, available, dt, self.grid)
            available -= taken
            if income:
                self.finance.record(now, "energy", f"{contract.title}", income)
            if penalty:
                self.finance.record(now, "penalty", f"Shortfall: {contract.title}", -penalty)
            if contract.kind == "frequency_response":
                self._settle_frequency_response(contract, dt)
            self.energy_delivered_mwh += taken * hours
            self._check_contract_end(contract, now)

        # Anything left goes to the spot market, at whatever it is worth.
        if available > 0.01:
            revenue = available * hours * self.grid.spot_price
            self.spot_energy_mwh += available * hours
            self.energy_delivered_mwh += available * hours
            self.finance.record(now, "spot", "Spot market sales", revenue)
        self.finance.levy(now, output * hours)
        return output

    def _settle_frequency_response(self, contract: Contract, dt: float) -> None:
        """Availability payment, conditional on the battery actually being ready."""
        ready = (
            self.battery.installed
            and self.battery.frequency_response
            and 0.25 <= self.battery.state_of_charge <= 0.85
            and self.battery.available_discharge_mw() >= contract.capacity_mw
        )
        now = self.grid.time
        if ready:
            income = contract.capacity_mw * contract.strike_price * (dt / DAY)
            contract.earned += income
            self.finance.record(now, "energy", contract.title, income)
        else:
            penalty = contract.shortfall_penalty * (dt / DAY)
            contract.penalties += penalty
            contract.shortfall_mwh += dt / HOUR
            self.finance.record(now, "penalty", f"Unavailable: {contract.title}", -penalty)

    def _check_contract_end(self, contract: Contract, now: float) -> None:
        if now < contract.ends_at or contract.completed or contract.failed:
            return
        contract.active = False
        rate = contract.delivery_rate
        if contract.kind == "capacity":
            rate = 1.0 if contract.tests_failed == 0 else 0.4
        if rate >= 0.97:
            contract.completed = True
            self.finance.record(now, "bonus", f"Completed: {contract.title}",
                                contract.completion_bonus + contract.collateral)
            self.finance.reputation += contract.reputation
            self.note("info", f"Contract completed: {contract.title}. "
                              f"Bonus paid, reputation up {contract.reputation:.0f}.")
        else:
            contract.failed = True
            self.finance.reputation = max(0.0, self.finance.reputation - contract.reputation * 1.5)
            self.note("warning",
                      f"Contract failed: {contract.title} -- delivered "
                      f"{rate * 100:.0f}% of the obligation. Collateral forfeited.")

    # ------------------------------------------------------------------
    # Support systems, wear, regulator
    # ------------------------------------------------------------------

    def _step_support_systems(self, dt: float, modifiers: dict[str, float]) -> None:
        plant = self.plant

        # Grid disconnection on a severe frequency excursion.
        if self.grid.disconnect_required and plant.secondary.generator_online:
            plant.secondary.trip_turbine()
            self.maintenance.record_challenge("Grid disconnection on frequency", 4.0)
            self.note("alarm", f"Grid frequency {self.grid.frequency:.2f} Hz -- "
                               "generator disconnected by the system operator.")

        # Offsite power and the emergency diesels.
        offsite = self.maintenance.components["offsite"]
        self._offsite_power = not offsite.failed
        if not self._offsite_power:
            if not self._diesel_running:
                reliability = 0.92 + modifiers["diesel_reliability"]
                if self.rng.random() < reliability:
                    self._diesel_running = True
                    self.note("warning", "Loss of offsite power. Emergency diesel "
                                         "generators started; coolant pumps on standby power.")
                else:
                    self.note("critical", "Loss of offsite power and the diesels have "
                                          "failed to start. Station blackout.")
            if not self._diesel_running:
                # Station blackout: pumps stop, and only passive cooling helps.
                plant.primary.pumps = [False] * 4
                if modifiers["passive_cooling"]:
                    plant.secondary.dump_setpoint = min(plant.secondary.dump_setpoint, 7.2)
                    plant.secondary.auto_feedwater = True
                else:
                    plant.secondary.feedwater = 0.0
                    plant.secondary.auto_feedwater = False
            else:
                # Diesels carry two of the four pumps.
                plant.primary.pumps = [True, True, False, False]
        else:
            if self._diesel_running:
                self._diesel_running = False
                plant.secondary.auto_feedwater = True
                self.note("info", "Offsite power restored.")

        # Failed components take their systems with them.
        for index in range(4):
            if self.maintenance.components[f"rcp{index + 1}"].failed:
                plant.primary.pumps[index] = False
        if self.maintenance.components["condenser"].failed:
            plant.secondary.condenser_available = False
        elif self._offsite_power:
            plant.secondary.condenser_available = True
        if self.maintenance.components["turbine"].failed or self.maintenance.components["generator"].failed:
            if plant.secondary.generator_online:
                plant.secondary.trip_turbine()
        if self.maintenance.components["feedwater"].failed:
            plant.secondary.auto_feedwater = False
            plant.secondary.feedwater = 0.0

        # Steam generator tube degradation leaks primary water to the secondary.
        tubes = self.maintenance.components["sg_tubes"]
        if tubes.failed:
            plant.primary.leak_rate = max(plant.primary.leak_rate, 6.5e-6)
            plant.release += 0.00004 * dt
        elif tubes.health < 0.25:
            plant.primary.leak_rate = max(plant.primary.leak_rate, 3.0e-7)

        # Wear and random faults.
        duty = plant.kinetics.power_fraction
        for message in self.maintenance.step_wear(
            duty, dt, modifiers["wear_rate"], self.grid.time,
            warn=bool(modifiers["fault_warning"]),
        ):
            self.note("info", message)
        for component in self.maintenance.roll_failures(dt, modifiers["crew_skill"]):
            self._on_component_failure(component)

    def _on_component_failure(self, component) -> None:
        self.note("alarm", f"Equipment failure: {component.name}.")
        if component.key.startswith("rcp"):
            self.maintenance.record_challenge("Reactor coolant pump trip", 3.0)
        elif component.key == "offsite":
            self.maintenance.record_challenge("Loss of offsite power", 5.0)

    def _step_business(self, dt: float, modifiers: dict[str, float]) -> None:
        now = self.grid.time
        self.market.step(dt, self.rng)
        self.market.hedged = bool(modifiers["uranium_hedge"])
        self.finance.daily_costs(now, dt)

        for upgrade in self.research.step(now):
            self.note("info", f"{upgrade.name} installed and in service.")
            if upgrade.effects.get("sg_repair"):
                self.maintenance.components["sg_tubes"].health = 1.0
                self.maintenance.components["sg_tubes"].failed = False

        # Enrichment campaign progress.
        if self.enrichment_job is not None:
            self.enrichment_job["elapsed"] += dt * modifiers["enrichment_speed"]
            if self.enrichment_job["elapsed"] >= self.enrichment_job["duration"]:
                job = self.enrichment_job
                self.enrichment_job = None
                self.fuel_store_kg += job["product_kg"]
                self.fuel_store_assay = job["assay"]
                self.note("info",
                          f"Enrichment campaign complete: {job['product_kg']:,.0f} kg "
                          f"at {job['assay']:.2f}% U-235 delivered to the fuel store.")

        # Refuelling outage.
        if self.outage_until is not None and now >= self.outage_until:
            self._finish_outage()

        # Frequency excursions are the regulator's business.
        if not self.grid.frequency_healthy and self.plant.secondary.generator_online:
            self.finance.fine(now, "Frequency deviation charge", 900.0 * dt / HOUR)

        # Radiological release.
        if self.plant.release > 0.05 and not getattr(self, "_release_reported", False):
            self._release_reported = True
            self.maintenance.record_challenge("Radiological release to the environment", 25.0)
            self.finance.fine(now, "Unplanned radiological release", 4_500_000.0)
            self.note("critical", "Radioactivity has been released beyond the site "
                                  "boundary. The regulator has been notified. This "
                                  "will be remembered.")

        self.maintenance.recover(dt, modifiers["safety_bonus"])
        if now >= self.maintenance.next_inspection:
            grade, fine, narrative = self.maintenance.inspect(now)
            if fine:
                self.finance.fine(now, f"Regulatory penalty ({grade})", fine)
            severity = {"Green": "info", "White": "info", "Yellow": "warning"}.get(grade, "critical")
            self.note(severity, f"Regulatory inspection -- {grade}. {narrative}")

        # New contract offers once a day.
        if self.grid.day != self._offers_refreshed_day:
            self._offers_refreshed_day = self.grid.day
            self.offers = [
                offer
                for offer in contract_catalogue(self.rng, self.grid.day)
                if offer.required_reputation <= self.finance.reputation
            ][:4]

    # ------------------------------------------------------------------
    # Alarms
    # ------------------------------------------------------------------

    def _raise(self, key: str, severity: str, message: str) -> None:
        existing = self.alarms.get(key)
        if existing is None:
            self.alarms[key] = Alarm(key, severity, message)
            self.note(severity, message)
        else:
            existing.message = message
            existing.severity = severity

    def _clear(self, key: str) -> None:
        self.alarms.pop(key, None)

    def _step_alarms(self, modifiers: dict[str, float]) -> None:
        plant = self.plant
        checks = [
            ("subcooling", plant.primary.subcooling < 12.0, "critical",
             f"Low subcooling margin: {plant.primary.subcooling:.1f} K to saturation"),
            ("void", plant.primary.void_fraction > 0.005, "critical",
             f"Steam void in the core: {plant.primary.void_fraction * 100:.1f}%"),
            ("high_power", plant.kinetics.power_fraction > 1.05, "alarm",
             f"Reactor power {plant.kinetics.power_fraction * 100:.0f}% of rated"),
            ("flow", plant.primary.flow_fraction < 0.92, "alarm",
             f"Reactor coolant flow {plant.primary.flow_fraction * 100:.0f}%"),
            ("pressure_high", plant.primary.pressure > 16.0, "alarm",
             f"Pressuriser pressure high: {plant.primary.pressure:.2f} MPa"),
            ("pressure_low", plant.primary.pressure < 13.6, "alarm",
             f"Pressuriser pressure low: {plant.primary.pressure:.2f} MPa"),
            ("sg_level", plant.secondary.sg_inventory < 0.45, "alarm",
             f"Steam generator level {plant.secondary.sg_inventory * 100:.0f}%"),
            ("fuel_temp", plant.primary.fuel_temperature > 1000.0, "critical",
             f"Fuel temperature {plant.primary.fuel_temperature:.0f} degC"),
            ("clad", plant.clad_damage > 0.001, "critical",
             f"Fuel cladding damage: {plant.clad_damage * 100:.1f}%"),
            ("mtc", plant.moderator_coefficient() > 0.0 and plant.kinetics.power_fraction > 0.1,
             "alarm", "Moderator temperature coefficient is positive -- reduce boron"),
            ("shutdown_margin",
             plant.rods.control_position > 0.995 and plant.boron_ppm < 60.0
             and not plant.tripped and plant.kinetics.power_fraction > 0.05,
             "warning",
             "Banks fully withdrawn and boron exhausted: no reactivity left to add"),
            ("xenon", plant.poisons.xenon_reactivity < -0.038, "warning",
             f"Xenon worth {plant.poisons.xenon_reactivity * 1e5:.0f} pcm -- "
             "restart may not be possible"),
            ("frequency", not self.grid.frequency_healthy, "alarm",
             f"Grid frequency {self.grid.frequency:.2f} Hz"),
            ("leak", plant.primary.inventory < 0.97, "critical",
             f"Primary inventory {plant.primary.inventory * 100:.0f}% -- coolant is being lost"),
            ("cash", self.finance.cash < 0, "warning",
             "The account is overdrawn"),
        ]
        for key, triggered, severity, message in checks:
            if triggered:
                self._raise(key, severity, message)
            else:
                self._clear(key)

        # Predicted trip warning, if the control room has been modernised.
        if modifiers["trip_warning"] and not plant.tripped:
            pending = plant._pending_trip
            if pending is not None:
                self._raise("pending_trip", "critical",
                            f"Protection setpoint reached: {pending.label}. "
                            "Trip in under a second.")
            else:
                self._clear("pending_trip")

    def _on_trip(self) -> None:
        reason = self.plant.trip_reasons[-1].label if self.plant.trip_reasons else "Reactor trip"
        self.maintenance.record_trip(reason)
        self.note("alarm", f"REACTOR TRIP -- {reason}")
        self.finance.record(self.grid.time, "penalty", "Unplanned outage costs", -180_000.0)

    def _check_endgame(self) -> None:
        if self.game_over:
            return
        if self.plant.destroyed:
            self.game_over = True
            self.game_over_reason = (
                "The core has been destroyed. Fission products are outside "
                "containment and the site is being evacuated. There is no "
                "version of this that ends well."
            )
        elif self.maintenance.licence_revoked:
            self.game_over = True
            self.game_over_reason = (
                "The nuclear site licence has been revoked. The reactor is "
                "ordered to cold shutdown permanently."
            )
        elif self.finance.bankrupt:
            self.game_over = True
            self.game_over_reason = (
                "The company is insolvent. Administrators have been appointed "
                "and the station is being sold."
            )
        if self.game_over:
            self.note("critical", self.game_over_reason)

    # ------------------------------------------------------------------
    # Refuelling
    # ------------------------------------------------------------------

    def start_outage(self) -> tuple[bool, str]:
        plant = self.plant
        if self.outage_until is not None:
            return False, "An outage is already in progress."
        if not plant.tripped and plant.kinetics.power_fraction > 0.001:
            return False, "The reactor must be shut down before refuelling."
        if plant.primary.coolant_temperature > 95.0:
            return False, (
                "The primary circuit must be in cold shutdown, below 95 degC. "
                "Lower the steam dump setpoint and cool down -- slowly, or you "
                "will damage the vessel."
            )
        required = 26_000.0
        if self.fuel_store_kg < required:
            return False, (
                f"A reload needs {required:,.0f} kg of enriched fuel; the store "
                f"holds {self.fuel_store_kg:,.0f} kg."
            )
        self.fuel_store_kg -= required
        days = 22.0
        self.outage_until = self.grid.time + days * DAY
        self.outage_reason = "Refuelling outage"
        self.finance.record(self.grid.time, "outage", "Refuelling outage mobilisation", -3_200_000.0)
        self._reload_assay = self.fuel_store_assay
        self.note("info", f"Refuelling outage started. {days:.0f} days to reload the "
                          "core, inspect the vessel and return to service.")
        return True, "Refuelling outage started."

    def _finish_outage(self) -> None:
        plant = self.plant
        plant.fuel.burnup = 0.0
        plant.fuel.enrichment = getattr(self, "_reload_assay", plant.fuel.enrichment)
        plant.fuel.burnable_poison = 1.0
        plant.poisons.iodine = 0.0
        plant.poisons.xenon = 0.0
        plant.poisons.samarium *= 0.35
        plant.core_damage = 0.0
        plant.clad_damage = 0.0
        plant.primary.inventory = 1.0
        plant.primary.leak_rate = 0.0
        plant.primary.vessel_stress = max(0.0, plant.primary.vessel_stress - 0.05)
        plant.boron_ppm = C.INITIAL_BORON_PPM + self.research.modifiers["boron_offset"]
        for component in self.maintenance.components.values():
            component.health = min(1.0, component.health + 0.45)
            component.failed = False
            component.warned = False
        self.outage_until = None
        self.maintenance.safety_score = min(100.0, self.maintenance.safety_score + 6.0)
        self.note("info", "Refuelling complete. Fresh core, clean plant, and a "
                          "shutdown margin you can spend. Restart when ready.")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def act(self, action: str, payload: dict | None = None) -> dict:
        """Perform one operator action.  Returns ``{ok, message}``."""
        payload = payload or {}
        handler = getattr(self, f"_do_{action}", None)
        if handler is None:
            return {"ok": False, "message": f"Unknown action: {action}"}
        if self.game_over and action not in ("set_speed", "restart"):
            return {"ok": False, "message": "The run is over."}
        try:
            return handler(payload)
        except (ValueError, KeyError, TypeError) as error:
            return {"ok": False, "message": str(error)}

    # -- clock ------------------------------------------------------------

    def _do_set_speed(self, payload: dict) -> dict:
        speed = int(payload.get("speed", 1))
        if speed not in SPEEDS:
            return {"ok": False, "message": "Unsupported speed."}
        self.speed = speed
        self.paused = speed == 0
        return {"ok": True, "message": f"Clock at {speed}x."}

    def _do_restart(self, payload: dict) -> dict:
        self.__init__(seed=None, scenario=payload.get("scenario", self.scenario))
        return {"ok": True, "message": "New run started."}

    # -- reactor ----------------------------------------------------------

    def _do_move_rods(self, payload: dict) -> dict:
        if self.plant.tripped:
            return {"ok": False, "message": "Rods are on the bottom. Reset the trip first."}
        # The payload is a percentage of control bank travel, so a request for
        # 5 moves the four-bank group average by 5%.
        delta = float(payload.get("delta", 0.0)) / 100.0 * len(C.CONTROL_BANKS)
        self.plant.rods.move_control_banks(delta)
        return {"ok": True, "message": f"Control bank demand {self.plant.rods.control_position * 100:.1f}%"}

    def _do_set_bank(self, payload: dict) -> dict:
        name = str(payload.get("bank", ""))
        value = float(payload.get("value", 0.0)) / 100.0
        if not self.plant.rods.set_bank_demand(name, value):
            return {"ok": False, "message": "Cannot move that bank."}
        return {"ok": True, "message": f"Bank {name} demanded to {value * 100:.0f}%"}

    def _do_scram(self, payload: dict) -> dict:
        already = self.plant.tripped
        self.plant.scram("Manual scram")
        if not already:
            # A manual trip counts against the plant exactly like an automatic
            # one. The regulator does not grade trips on intent.
            self._on_trip()
        return {"ok": True, "message": "Reactor tripped."}

    def _do_reset_trip(self, payload: dict) -> dict:
        if self.plant.reset_trip():
            self.plant.secondary.reset_turbine()
            return {"ok": True, "message": "Protection system reset. Rods are on the bottom."}
        standing = self.plant._standing_trip()
        detail = f" ({standing.label})" if standing else ""
        return {"ok": False, "message": f"A trip condition is still present{detail}."}

    def _do_auto_rods(self, payload: dict) -> dict:
        if not self.research.modifiers["auto_rod_control"]:
            return {"ok": False, "message": "Automatic rod control has not been installed."}
        self.rods_auto = bool(payload.get("on", not self.rods_auto))
        return {"ok": True, "message": f"Automatic rod control {'on' if self.rods_auto else 'off'}."}

    # -- chemistry --------------------------------------------------------

    def _do_boron(self, payload: dict) -> dict:
        demand = float(payload.get("demand", 0.0))
        self.plant.boron_demand = max(-1.0, min(1.0, demand))
        self.plant.auto_boron = False
        word = "Borating" if demand > 0 else ("Diluting" if demand < 0 else "Boron hold")
        return {"ok": True, "message": word}

    def _do_auto_boron(self, payload: dict) -> dict:
        self.plant.auto_boron = bool(payload.get("on", not self.plant.auto_boron))
        return {"ok": True, "message": f"Automatic boron control {'on' if self.plant.auto_boron else 'off'}."}

    # -- coolant and steam ------------------------------------------------

    def _do_pump(self, payload: dict) -> dict:
        index = int(payload.get("index", 0))
        if not 0 <= index < 4:
            return {"ok": False, "message": "No such pump."}
        component = self.maintenance.components[f"rcp{index + 1}"]
        if component.failed or component.under_repair:
            return {"ok": False, "message": f"{component.name} is out of service."}
        state = bool(payload.get("on", not self.plant.primary.pumps[index]))
        self.plant.primary.pumps[index] = state
        return {"ok": True, "message": f"Coolant pump {index + 1} {'started' if state else 'stopped'}."}

    def _do_turbine(self, payload: dict) -> dict:
        demand = float(payload.get("demand", 1.0))
        self.plant.secondary.valve_demand = max(0.0, min(1.0, demand))
        return {"ok": True, "message": f"Turbine demand {demand * 100:.0f}%"}

    def _do_reset_turbine(self, payload: dict) -> dict:
        if self.maintenance.components["turbine"].failed:
            return {"ok": False, "message": "The turbine is failed and must be repaired."}
        if self.plant.tripped:
            return {"ok": False, "message": "Reset the reactor trip first."}
        self.plant.secondary.reset_turbine()
        return {"ok": True, "message": "Turbine reset and ready to load."}

    def _do_dump_setpoint(self, payload: dict) -> dict:
        value = float(payload.get("value", 7.5))
        self.plant.secondary.dump_setpoint = max(0.2, min(9.0, value))
        temperature = saturation_temperature(self.plant.secondary.dump_setpoint)
        return {"ok": True,
                "message": f"Steam dump setpoint {value:.2f} MPa "
                           f"(holds the primary near {temperature:.0f} degC)"}

    def _do_feedwater(self, payload: dict) -> dict:
        if "auto" in payload:
            self.plant.secondary.auto_feedwater = bool(payload["auto"])
            return {"ok": True, "message": "Feedwater control set."}
        self.plant.secondary.auto_feedwater = False
        self.plant.secondary.feedwater = max(0.0, min(1.3, float(payload.get("value", 1.0))))
        return {"ok": True, "message": "Feedwater set."}

    def _do_safety_injection(self, payload: dict) -> dict:
        state = bool(payload.get("on", not self.plant.primary.safety_injection))
        self.plant.primary.safety_injection = state
        return {"ok": True, "message": f"Safety injection {'armed' if state else 'secured'}."}

    # -- battery ----------------------------------------------------------

    def _do_battery(self, payload: dict) -> dict:
        if "power" in payload:
            self.battery.power_demand_mw = float(payload["power"])
        if "frequency_response" in payload:
            self.battery.frequency_response = bool(payload["frequency_response"])
        return {"ok": True, "message": f"Battery demand {self.battery.power_demand_mw:+.0f} MW"}

    def _do_replace_battery(self, payload: dict) -> dict:
        cost = self.battery.replacement_cost()
        if cost < 1000:
            return {"ok": False, "message": "The pack is effectively new."}
        if self.finance.cash < cost:
            return {"ok": False, "message": f"Replacement costs £{cost:,.0f}."}
        self.finance.record(self.grid.time, "capital", "Battery cell replacement", -cost)
        self.battery.health = 1.0
        self.battery.cycles = 0.0
        return {"ok": True, "message": "Battery cells replaced."}

    # -- fuel -------------------------------------------------------------

    def _do_order_enrichment(self, payload: dict) -> dict:
        if self.enrichment_job is not None:
            return {"ok": False, "message": "A campaign is already running."}
        product_kg = float(payload.get("kg", 0.0))
        assay = float(payload.get("assay", 4.5))
        tails = float(payload.get("tails", self.tails_assay))
        floor = 0.25 + self.research.modifiers["tails_floor"]
        if product_kg <= 0:
            return {"ok": False, "message": "Order a positive quantity."}
        if not 1.0 <= assay <= 5.0:
            return {"ok": False, "message": "Commercial fuel is enriched between 1% and 5% U-235."}
        if tails < floor:
            return {"ok": False,
                    "message": f"The cascade cannot economically run below {floor:.2f}% tails."}
        quote = self.market.quote(product_kg, assay, tails,
                                  self.research.modifiers["swu_efficiency"])
        if self.finance.cash < quote["total"]:
            return {"ok": False, "message": f"That order costs £{quote['total']:,.0f}."}
        self.finance.record(self.grid.time, "fuel",
                            f"Enrichment: {product_kg:,.0f} kg at {assay:.2f}%",
                            -quote["total"])
        duration = (4.0 + product_kg / 2600.0) * DAY
        self.enrichment_job = {
            "product_kg": product_kg,
            "assay": assay,
            "tails": tails,
            "elapsed": 0.0,
            "duration": duration,
            "quote": quote,
        }
        self.tails_assay = tails
        return {"ok": True,
                "message": f"Ordered {product_kg:,.0f} kg at {assay:.2f}% for "
                           f"£{quote['total']:,.0f} ({quote['swu']:,.0f} SWU, "
                           f"{quote['feed_kg']:,.0f} kg natural uranium)."}

    def _do_quote_enrichment(self, payload: dict) -> dict:
        quote = self.market.quote(
            float(payload.get("kg", 26000)),
            float(payload.get("assay", 4.5)),
            float(payload.get("tails", self.tails_assay)),
            self.research.modifiers["swu_efficiency"],
        )
        return {"ok": True, "message": "Quote", "quote": quote}

    def _do_refuel(self, payload: dict) -> dict:
        ok, message = self.start_outage()
        return {"ok": ok, "message": message}

    # -- plant business ---------------------------------------------------

    def _do_purchase_upgrade(self, payload: dict) -> dict:
        key = str(payload.get("key", ""))
        upgrade = self.research.upgrades.get(key)
        if upgrade is None:
            return {"ok": False, "message": "No such upgrade."}
        if upgrade.purchased:
            return {"ok": False, "message": "Already purchased."}
        if not all(self.research.upgrades[dep].installed for dep in upgrade.requires):
            return {"ok": False, "message": "Prerequisites not installed."}
        if self.finance.cash < upgrade.cost:
            return {"ok": False, "message": f"That costs £{upgrade.cost:,.0f}."}
        self.research.purchase(key, self.grid.time)
        self.finance.record(self.grid.time, "capital", upgrade.name, -upgrade.cost)
        if upgrade.install_days:
            return {"ok": True, "message": f"{upgrade.name} ordered. "
                                           f"{upgrade.install_days:.0f} days to install."}
        return {"ok": True, "message": f"{upgrade.name} in service."}

    def _do_repair(self, payload: dict) -> dict:
        key = str(payload.get("key", ""))
        component = self.maintenance.components.get(key)
        if component is None:
            return {"ok": False, "message": "No such component."}
        if component.under_repair:
            return {"ok": False, "message": "Already being worked on."}
        cost = component.repair_cost * (1.0 if component.failed else 0.55)
        if self.finance.cash < cost:
            return {"ok": False, "message": f"That repair costs £{cost:,.0f}."}
        self.finance.record(self.grid.time, "maintenance", f"Repair: {component.name}", -cost)
        self.maintenance.begin_repair(key, self.grid.time)
        return {"ok": True,
                "message": f"{component.name} taken out of service for "
                           f"{component.repair_days:.1f} days."}

    def _do_accept_contract(self, payload: dict) -> dict:
        key = str(payload.get("key", ""))
        offer = next((o for o in self.offers if o.key == key), None)
        if offer is None:
            return {"ok": False, "message": "That offer is no longer on the table."}
        if self.finance.cash < offer.collateral:
            return {"ok": False, "message": f"Collateral of £{offer.collateral:,.0f} is required."}
        active = [c for c in self.contracts if c.active]
        committed = sum(c.capacity_mw for c in active if c.kind != "frequency_response")
        if committed + offer.capacity_mw > 1400 and offer.kind != "frequency_response":
            return {"ok": False,
                    "message": "Total contracted capacity would exceed what this "
                               "station can physically deliver."}
        offer.active = True
        offer.accepted_at = self.grid.time
        offer._test_due = self.grid.time + self.rng.uniform(0.5, 2.0) * DAY
        self.contracts.append(offer)
        self.offers = [o for o in self.offers if o.key != key]
        self.finance.record(self.grid.time, "collateral", f"Collateral: {offer.title}",
                            -offer.collateral)
        return {"ok": True, "message": f"Signed: {offer.title}."}

    def _do_abandon_contract(self, payload: dict) -> dict:
        key = str(payload.get("key", ""))
        contract = next((c for c in self.contracts if c.key == key and c.active), None)
        if contract is None:
            return {"ok": False, "message": "No such active contract."}
        contract.active = False
        contract.failed = True
        self.finance.reputation = max(0.0, self.finance.reputation - contract.reputation * 2.0)
        self.note("warning", f"Contract abandoned: {contract.title}. Collateral forfeited.")
        return {"ok": True, "message": "Contract abandoned."}

    def _do_acknowledge(self, payload: dict) -> dict:
        key = payload.get("key")
        if key:
            alarm = self.alarms.get(str(key))
            if alarm:
                alarm.acknowledged = True
        else:
            for alarm in self.alarms.values():
                alarm.acknowledged = True
        return {"ok": True, "message": "Acknowledged."}

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def xenon_forecast(self, hours: float = 12.0, points: int = 25) -> list[dict]:
        """Project xenon reactivity forward at the current power.

        Only meaningful once incore flux mapping has been installed; the
        interface hides it otherwise.  This is a genuine integration of the
        iodine-xenon chain, run on a copy of the current concentrations.
        """
        from .neutronics import FissionProducts

        copy = FissionProducts(
            iodine=self.plant.poisons.iodine,
            xenon=self.plant.poisons.xenon,
            promethium=self.plant.poisons.promethium,
            samarium=self.plant.poisons.samarium,
        )
        power = self.plant.kinetics.power_fraction
        step = hours * HOUR / points
        out = []
        for index in range(points + 1):
            out.append({
                "hours": index * step / HOUR,
                "pcm": copy.xenon_reactivity * 1e5,
            })
            copy.step(power, step)
        return out

    def score(self) -> dict:
        """The end-of-run assessment."""
        capacity_factor = (
            self.energy_delivered_mwh / max(self.total_seconds / HOUR * 1120.0, 1e-6)
        )
        return {
            "days": self.grid.time / DAY,
            "energy_delivered_mwh": self.energy_delivered_mwh,
            "capacity_factor": capacity_factor,
            "cash": self.finance.cash,
            "profit": self.finance.lifetime_income - self.finance.lifetime_costs,
            "reputation": self.finance.reputation,
            "safety_score": self.maintenance.safety_score,
            "trips": self.maintenance.trips,
            "burnup": self.plant.fuel.burnup,
            "release": self.plant.release,
            "core_damage": self.plant.core_damage,
        }

    def state(self) -> dict:
        """Everything the interface needs, in one JSON-serialisable dict."""
        plant = self.plant
        modifiers = self.research.modifiers
        terms = plant.reactivity_terms or plant.compute_reactivity()
        period = plant.reactor_period
        return {
            "clock": {
                "time": self.grid.time,
                "day": self.grid.day,
                "hour": self.grid.hour_of_day,
                "speed": self.speed,
                "effective_speed": self.effective_speed,
                "abnormal": self.abnormal,
                "paused": self.paused,
            },
            "reactor": {
                "power_fraction": plant.kinetics.power_fraction,
                "thermal_mw": plant.thermal_power_mw,
                "decay_mw": plant.decay_power_mw,
                # A period longer than a day is indistinguishable from
                # critical, and reads better as the infinity it is trying to be.
                "period": None if (not math.isfinite(period) or abs(period) > 1e5) else period,
                "prompt_critical": plant.kinetics.prompt_critical,
                "tripped": plant.tripped,
                "trip_reasons": [t.label for t in plant.trip_reasons],
                "reactivity": {key: value * 1e5 for key, value in terms.items()},
                "mtc": plant.moderator_coefficient(),
                "boron_ppm": plant.boron_ppm,
                "boron_demand": plant.boron_demand,
                "auto_boron": plant.auto_boron,
                "auto_rods": self.rods_auto,
                "differential_worth": plant.rods.differential_worth_now(),
                "shutdown_margin": plant.rods.shutdown_margin * 1e5,
                "banks": [
                    {
                        "name": name,
                        "position": plant.rods.banks[name].position * 100.0,
                        "demand": plant.rods.banks[name].demand * 100.0,
                        "worth": plant.rods.banks[name].total_worth_pcm,
                        "shutdown": name in C.SHUTDOWN_BANKS,
                    }
                    for name in C.ROD_BANKS
                ],
                "control_position": plant.rods.control_position * 100.0,
                "burnup": plant.fuel.burnup,
                "enrichment": plant.fuel.enrichment,
                "cycle_fraction": plant.fuel.cycle_fraction,
                "xenon_pcm": plant.poisons.xenon_reactivity * 1e5,
                "samarium_pcm": plant.poisons.samarium_reactivity * 1e5,
                "core_damage": plant.core_damage,
                "clad_damage": plant.clad_damage,
                "release": plant.release,
            },
            "thermal": {
                "fuel_temperature": plant.primary.fuel_temperature,
                "coolant_temperature": plant.primary.coolant_temperature,
                "hot_leg": plant.primary.hot_leg,
                "cold_leg": plant.primary.cold_leg,
                "pressure": plant.primary.pressure,
                "saturation": saturation_temperature(plant.primary.pressure),
                "subcooling": plant.primary.subcooling,
                "flow": plant.primary.flow_fraction,
                "pumps": list(plant.primary.pumps),
                "void": plant.primary.void_fraction,
                "inventory": plant.primary.inventory,
                "relief_open": plant.primary.relief_open,
                "safety_injection": plant.primary.safety_injection,
                "vessel_stress": plant.primary.vessel_stress,
                "steam_pressure": plant.secondary.steam_pressure,
                "steam_temperature": plant.secondary.steam_temperature,
                "sg_inventory": plant.secondary.sg_inventory,
                "turbine_valve": plant.secondary.turbine_valve,
                "turbine_demand": plant.secondary.valve_demand,
                "turbine_tripped": plant.secondary.turbine_tripped,
                "dump_valve": plant.secondary.dump_valve,
                "dump_setpoint": plant.secondary.dump_setpoint,
                "feedwater": plant.secondary.feedwater,
                "auto_feedwater": plant.secondary.auto_feedwater,
                "condenser": plant.secondary.condenser_available,
            },
            "electrical": {
                "gross_mw": plant.secondary.gross_electric_mw,
                "net_mw": plant.net_electric_mw,
                "site_output_mw": max(0.0, plant.net_electric_mw) + self.battery.power_mw,
                "offsite_power": self._offsite_power,
                "diesels": self._diesel_running,
                "battery": {
                    "charge_mwh": self.battery.charge_mwh,
                    "capacity_mwh": self.battery.capacity_mwh,
                    "soc": self.battery.state_of_charge,
                    "power_mw": self.battery.power_mw,
                    "demand_mw": self.battery.power_demand_mw,
                    "health": self.battery.health,
                    "cycles": self.battery.cycles,
                    "frequency_response": self.battery.frequency_response,
                    "max_power_mw": self.battery.max_power_mw,
                    "replacement_cost": self.battery.replacement_cost(),
                },
            },
            "grid": self.grid.snapshot(),
            "finance": {
                "cash": self.finance.cash,
                "reputation": self.finance.reputation,
                "revenue_today": self.finance.revenue_today,
                "costs_today": self.finance.costs_today,
                "lifetime_income": self.finance.lifetime_income,
                "lifetime_costs": self.finance.lifetime_costs,
                "fines": self.finance.fines,
                "decommissioning_fund": self.finance.decommissioning_fund,
                "ledger": [
                    {"time": e.time, "category": e.category,
                     "description": e.description, "amount": e.amount}
                    for e in self.finance.ledger[-24:]
                ],
            },
            "contracts": {
                "active": [self._contract_state(c) for c in self.contracts if c.active],
                "history": [self._contract_state(c) for c in self.contracts if not c.active][-6:],
                "offers": [self._contract_state(c) for c in self.offers],
            },
            "fuel": {
                "store_kg": self.fuel_store_kg,
                "store_assay": self.fuel_store_assay,
                "tails_assay": self.tails_assay,
                "tails_floor": 0.25 + modifiers["tails_floor"],
                "uranium_price": self.market.uranium_price,
                "swu_price": self.market.swu_price,
                "job": (
                    None if self.enrichment_job is None else {
                        "product_kg": self.enrichment_job["product_kg"],
                        "assay": self.enrichment_job["assay"],
                        "progress": self.enrichment_job["elapsed"] / self.enrichment_job["duration"],
                        "days_left": (self.enrichment_job["duration"]
                                      - self.enrichment_job["elapsed"]) / DAY,
                    }
                ),
                "outage_days_left": (
                    None if self.outage_until is None
                    else (self.outage_until - self.grid.time) / DAY
                ),
            },
            "maintenance": {
                "safety_score": self.maintenance.safety_score,
                "trips": self.maintenance.trips,
                "next_inspection_days": max(
                    0.0, (self.maintenance.next_inspection - self.grid.time) / DAY),
                "components": [
                    {
                        "key": c.key, "name": c.name, "health": c.health,
                        "failed": c.failed, "repairing": c.under_repair,
                        "repair_cost": c.repair_cost * (1.0 if c.failed else 0.55),
                        "repair_days": c.repair_days,
                        "days_left": (
                            None if c.repairing_until is None
                            else (c.repairing_until - self.grid.time) / DAY
                        ),
                    }
                    for c in self.maintenance.components.values()
                ],
            },
            "research": {
                "modifiers": modifiers,
                "upgrades": [
                    {
                        "key": u.key, "category": u.category, "name": u.name,
                        "cost": u.cost, "description": u.description,
                        "purchased": u.purchased, "installed": u.installed,
                        "requires": list(u.requires),
                        "days_left": (
                            None if u.installing_until is None
                            else (u.installing_until - self.grid.time) / DAY
                        ),
                        "locked": not all(
                            self.research.upgrades[dep].installed for dep in u.requires),
                    }
                    for u in self.research.upgrades.values()
                ],
            },
            "alarms": [
                {"key": a.key, "severity": a.severity, "message": a.message,
                 "acknowledged": a.acknowledged}
                for a in self.alarms.values()
            ],
            "log": [
                {"time": e.time, "severity": e.severity, "message": e.message}
                for e in self.log[-40:]
            ],
            "xenon_forecast": (
                self.xenon_forecast() if modifiers["xenon_forecast"] else []
            ),
            "score": self.score(),
            "game_over": self.game_over,
            "game_over_reason": self.game_over_reason,
            "scenario": self.scenario,
        }

    def _contract_state(self, contract: Contract) -> dict:
        now = self.grid.time
        return {
            "key": contract.key,
            "kind": contract.kind,
            "title": contract.title,
            "description": contract.description,
            "capacity_mw": contract.capacity_mw,
            "strike_price": contract.strike_price,
            "duration_days": contract.duration_days,
            "shortfall_penalty": contract.shortfall_penalty,
            "completion_bonus": contract.completion_bonus,
            "collateral": contract.collateral,
            "required_reputation": contract.required_reputation,
            "active": contract.active,
            "completed": contract.completed,
            "failed": contract.failed,
            "required_now": contract.required_mw(now, self.grid),
            "delivered_mwh": contract.delivered_mwh,
            "required_mwh": contract.required_mwh,
            "delivery_rate": contract.delivery_rate,
            "earned": contract.earned,
            "penalties": contract.penalties,
            "days_left": contract.time_remaining(now) / DAY if contract.active else 0.0,
            "progress": contract.progress(now) if contract.active else 1.0,
            "tests_passed": contract.tests_passed,
            "tests_failed": contract.tests_failed,
            "test_active": now < contract._test_active_until,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> str:
        """Serialise the run to JSON."""
        def encode(value):
            if hasattr(value, "__dict__"):
                return {k: encode(v) for k, v in vars(value).items()
                        if not k.startswith("_rng")}
            if isinstance(value, dict):
                return {k: encode(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [encode(v) for v in value]
            if isinstance(value, random.Random):
                return None
            return value

        payload = {
            "version": 2,
            "seed": self.seed,
            "scenario": self.scenario,
            "grid_time": self.grid.time,
            "plant": encode(self.plant),
            "grid": encode(self.grid),
            "finance": encode(self.finance),
            "battery": encode(self.battery),
            "research": encode(self.research),
            "market": encode(self.market),
            "maintenance": encode(self.maintenance),
            "contracts": [encode(c) for c in self.contracts],
            "offers": [encode(c) for c in self.offers],
            "fuel_store_kg": self.fuel_store_kg,
            "fuel_store_assay": self.fuel_store_assay,
            "tails_assay": self.tails_assay,
            "enrichment_job": self.enrichment_job,
            "outage_until": self.outage_until,
            "energy_delivered_mwh": self.energy_delivered_mwh,
            "uptime_seconds": self.uptime_seconds,
            "total_seconds": self.total_seconds,
            "log": [vars(e) for e in self.log[-60:]],
        }
        return json.dumps(payload, default=str)
