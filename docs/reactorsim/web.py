"""A front-end-agnostic session: one game, its trend history, and a JSON API.

This exists so that the Flask server and the browser build share exactly the
same code path.  Everything the interface can ask for goes through the methods
here, and neither front end knows anything about the simulation beyond the
JSON they hand back.

``app.py`` wraps a Session in a lock and a background thread.  The GitHub Pages
build runs the identical class inside Pyodide and shims ``fetch`` so the same
``static/app.js`` talks to it without modification.
"""

from __future__ import annotations

import json
import time

from .game import SPEEDS, Game
from .scenarios import SCENARIOS


class Session:
    """One game plus the rolling trend buffer the charts are drawn from."""

    #: Seconds of plant time between trend samples.
    HISTORY_INTERVAL = 4.0
    #: Samples retained.
    HISTORY_LENGTH = 900
    #: Samples sent to the interface with each state snapshot.
    HISTORY_WINDOW = 260

    def __init__(self, scenario: str = "full_power", seed: int | None = None) -> None:
        self.game = Game(seed=seed, scenario=scenario)
        self.history: list[dict] = []
        self._next_sample = 0.0
        self._last_real_time = time.monotonic()

    # -- clock ------------------------------------------------------------

    def tick(self, real_dt: float | None = None) -> None:
        """Advance by one frame of wall-clock time, scaled by the game speed."""
        now = time.monotonic()
        if real_dt is None:
            real_dt = min(now - self._last_real_time, 0.5)
        self._last_real_time = now
        self.game.tick(real_dt)
        self.sample()

    def advance(self, seconds: float) -> None:
        """Advance by a fixed amount of plant time, regardless of speed."""
        self.game.advance(seconds)
        self.sample()

    def sample(self) -> None:
        game = self.game
        if game.grid.time < self._next_sample:
            return
        self._next_sample = game.grid.time + self.HISTORY_INTERVAL
        plant = game.plant
        self.history.append({
            "t": round(game.grid.time, 1),
            "power": round(plant.kinetics.power_fraction * 100, 3),
            "fuel": round(plant.primary.fuel_temperature, 1),
            "coolant": round(plant.primary.coolant_temperature, 2),
            "pressure": round(plant.primary.pressure, 3),
            "mwe": round(max(0.0, plant.net_electric_mw) + game.battery.power_mw, 1),
            "rho": round(plant.reactivity_terms.get("total", 0.0) * 1e5, 1),
            "xenon": round(plant.poisons.xenon_reactivity * 1e5, 1),
            "frequency": round(game.grid.frequency, 4),
            "price": round(game.grid.spot_price, 2),
            "demand": round(game.grid.demand_mw, 0),
            "soc": round(game.battery.state_of_charge * 100, 2),
        })
        if len(self.history) > self.HISTORY_LENGTH:
            del self.history[:-self.HISTORY_LENGTH]

    # -- API --------------------------------------------------------------

    def state(self) -> dict:
        state = self.game.state()
        state["history"] = self.history[-self.HISTORY_WINDOW:]
        return state

    def act(self, action: str, payload: dict | None = None) -> dict:
        result = self.game.act(action, payload or {})
        result["state"] = self.state()
        return result

    def reset(self, scenario: str, seed: int | None = None) -> dict:
        if scenario not in SCENARIOS:
            return {"ok": False, "message": "Unknown scenario"}
        self.game = Game(seed=seed, scenario=scenario)
        self.history.clear()
        self._next_sample = 0.0
        return {"ok": True, "state": self.state()}

    @staticmethod
    def scenarios() -> list[dict]:
        return [
            {
                "key": key,
                "name": value["name"],
                "difficulty": value["difficulty"],
                "briefing": value["briefing"],
            }
            for key, value in SCENARIOS.items()
        ]

    @staticmethod
    def speeds() -> list[int]:
        return list(SPEEDS)

    # -- JSON wrappers, used by the in-browser build ----------------------

    def state_json(self) -> str:
        return json.dumps(self.state())

    def history_json(self) -> str:
        return json.dumps(self.history)

    def act_json(self, body: str) -> str:
        payload = json.loads(body) if body else {}
        return json.dumps(self.act(str(payload.get("action", "")),
                                   payload.get("payload") or {}))

    def new_json(self, body: str) -> str:
        payload = json.loads(body) if body else {}
        seed = payload.get("seed")
        return json.dumps(self.reset(
            str(payload.get("scenario", "full_power")),
            int(seed) if seed not in (None, "") else None,
        ))

    def scenarios_json(self) -> str:
        return json.dumps(self.scenarios())

    def save_json(self) -> str:
        return self.game.save()
