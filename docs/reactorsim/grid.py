"""The electricity grid: demand, frequency, price, and the contracts you sign.

A power station does not simply "make electricity".  It sells a specific
quantity of power, at specific times, to counterparties who have paid for it,
on a network whose frequency is a shared physical accounting of whether
generation matches demand at every instant.

Three things follow, and all three are modelled here.

* **Demand moves and does not care about you.**  British demand has a deep
  overnight trough, a sharp morning ramp, an evening peak, and a seasonal
  swing.  A nuclear plant that cannot follow it is worth less than one that
  can, and the plant's ability to follow is limited by xenon, not by the
  turbine.

* **Frequency is the scoreboard.**  Generation above demand pushes 50 Hz up;
  below, down.  Deviation beyond the statutory band earns fines, and beyond
  0.9 Hz the plant is disconnected to protect the network -- which trips the
  turbine, which usually trips the reactor.

* **Price is not a constant.**  The spot price tracks scarcity.  On a windy
  Sunday night with everything running, prices go negative and you are paying
  to generate.  During a cold, still winter evening peak they go to ten times
  normal, and that is when being at full power is worth a fortune.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


DAY = 86400.0


def _bump(hour: float, centre: float, width: float) -> float:
    """A Gaussian bump on a 24 hour circle."""
    distance = abs(hour - centre)
    distance = min(distance, 24.0 - distance)
    return math.exp(-(distance ** 2) / width)


@dataclass
class GridModel:
    """The network the plant is connected to."""

    #: Simulation clock, seconds since the start of the game.
    time: float = 0.0
    #: Total system demand in MW (this is a small national grid, ~45 GW peak).
    demand_mw: float = 30000.0
    #: Generation from everything that is not this plant.
    other_supply_mw: float = 29000.0
    #: Dispatchable (non-wind) generation from the rest of the system.
    dispatchable_mw: float = 22000.0
    frequency: float = 50.0
    spot_price: float = 62.0            # GBP per MWh
    #: Renewable output as a fraction of its capacity; drives price volatility.
    wind_factor: float = 0.5
    #: Multiplies demand -- cold snaps, heatwaves, holidays.
    weather_factor: float = 1.0
    weather_label: str = "Settled"
    weather_target: float = 1.0
    wind_target: float = 0.5
    seconds_of_weather: float = 0.0

    _initialised: bool = field(default=False, repr=False)
    _noise_phase: float = field(default=0.0, repr=False)
    _rng: random.Random = field(default_factory=random.Random, repr=False)

    #: Rolling record of frequency excursions for the regulator.
    seconds_outside_band: float = 0.0

    BASE_DEMAND = 30000.0
    PEAK_SWING = 12000.0
    OTHER_CAPACITY = 41000.0
    WIND_CAPACITY = 14000.0

    # -- profile ----------------------------------------------------------

    @property
    def day(self) -> int:
        return int(self.time // DAY)

    @property
    def hour_of_day(self) -> float:
        return (self.time % DAY) / 3600.0

    def demand_profile(self, when: float | None = None) -> float:
        """Total system demand in MW at the given simulation time."""
        t = self.time if when is None else when
        hour = (t % DAY) / 3600.0
        # Two-peak daily shape: morning ramp at 07:00, evening peak at 18:00,
        # overnight trough at 03:30. The bumps use a wrapped distance, so the
        # trough is continuous across midnight -- a plain Gaussian in "hour"
        # steps by 1700 MW at 00:00 and the frequency model, quite correctly,
        # reports that as a grid event.
        morning = _bump(hour, 7.8, 6.0)
        evening = _bump(hour, 18.2, 5.0)
        overnight = -0.55 * _bump(hour, 3.5, 9.0)
        shape = 0.42 * morning + 0.62 * evening + overnight
        # Seasonal swing on a 90-day year so a campaign sees winter.
        season = 0.10 * math.cos(2.0 * math.pi * (t / (90.0 * DAY)))
        weekday = self._weekday_factor(t)
        return (
            (self.BASE_DEMAND + self.PEAK_SWING * shape)
            * (1.0 + season)
            * weekday
            * self.weather_factor
        )

    @staticmethod
    def _weekday_factor(t: float) -> float:
        """Weekday / weekend demand, blended across midnight.

        Industrial demand falls about 10% at the weekend, but it does not fall
        by three and a half gigawatts in one simulation step: stepping the
        factor at midnight puts a discontinuity into the supply-demand balance
        that the frequency model faithfully reports as a 1.8 Hz excursion the
        player did not cause. Blending over the last three hours of the day removes
        the artefact without removing the effect.
        """
        day = t / DAY
        index = int(day) % 7
        following = (int(day) + 1) % 7
        level = lambda i: 1.0 if i < 5 else 0.90  # noqa: E731
        fraction = day - int(day)
        blend = 0.0 if fraction < 21.0 / 24.0 else (fraction - 21.0 / 24.0) * 8.0
        return level(index) * (1.0 - blend) + level(following) * blend

    # -- stepping ---------------------------------------------------------

    def step(self, plant_output_mw: float, dt: float) -> None:
        self.time += dt
        self._step_weather(dt)

        self.demand_mw = self.demand_profile()

        # Everything else on the system: wind, plus dispatchable plant that
        # chases the residual demand imperfectly and with a lag.  The lag is
        # what gives this plant something to sell: for the first minute after
        # any change, the network needs somebody to be quick.
        self._noise_phase += dt
        wind = self.WIND_CAPACITY * self.wind_factor
        target = max(0.0, self.demand_mw - wind - plant_output_mw)
        if not self._initialised:
            # Snap the rest of the system into balance on the first step, so a
            # new game does not open with a frequency excursion nobody caused.
            self._initialised = True
            self.dispatchable_mw = target
        lag = 1.0 - math.exp(-dt / 90.0)
        self.dispatchable_mw += (target - self.dispatchable_mw) * lag
        jitter = math.sin(self._noise_phase / 210.0) * 140.0
        self.other_supply_mw = wind + self.dispatchable_mw + jitter

        self._step_frequency(plant_output_mw, dt)
        self._step_price(plant_output_mw, dt)

    def _step_weather(self, dt: float) -> None:
        """Pick a new weather regime occasionally, and drift towards it.

        Weather is chosen in blocks of hours but *applied* gradually: a cold
        snap that appeared instantly would move national demand by five
        gigawatts in one step and throw the frequency across the room, which
        is a modelling artefact rather than anything real. Twenty minutes of
        time constant is about right for a front moving over the country.
        """
        self.seconds_of_weather -= dt
        if self.seconds_of_weather <= 0:
            self.seconds_of_weather = self._rng.uniform(6.0, 30.0) * 3600.0
            roll = self._rng.random()
            if roll < 0.12:
                self.weather_target, self.weather_label = 1.17, "Cold snap"
                self.wind_target = self._rng.uniform(0.05, 0.25)
            elif roll < 0.24:
                self.weather_target, self.weather_label = 1.08, "Heatwave"
                self.wind_target = self._rng.uniform(0.10, 0.30)
            elif roll < 0.44:
                self.weather_target, self.weather_label = 0.97, "Windy"
                self.wind_target = self._rng.uniform(0.70, 0.98)
            elif roll < 0.54:
                self.weather_target, self.weather_label = 0.90, "Mild and blustery"
                self.wind_target = self._rng.uniform(0.80, 1.00)
            else:
                self.weather_target, self.weather_label = 1.0, "Settled"
                self.wind_target = self._rng.uniform(0.25, 0.65)

        drift = 1.0 - math.exp(-dt / 1200.0)
        self.weather_factor += (self.weather_target - self.weather_factor) * drift
        self.wind_factor += (self.wind_target - self.wind_factor) * drift

    def _step_frequency(self, plant_output_mw: float, dt: float) -> None:
        supply = self.other_supply_mw + plant_output_mw
        imbalance = (supply - self.demand_mw) / max(self.demand_mw, 1.0)
        target = 50.0 + imbalance * 100.0 * 0.14
        # The rest of the system's governors pull frequency back to nominal.
        pull = 1.0 - math.exp(-dt * 0.16)
        self.frequency += (target - self.frequency) * pull
        self.frequency = max(46.0, min(54.0, self.frequency))
        if abs(self.frequency - 50.0) > 0.5:
            self.seconds_outside_band += dt

    def _step_price(self, plant_output_mw: float, dt: float) -> None:
        # Spare capacity actually available to the system right now: spinning
        # reserve, plus whatever the wind is doing, less the squeeze that high
        # demand puts on the merit order.
        headroom = 2500.0 + 11000.0 * self.wind_factor + (30000.0 - self.demand_mw) * 0.45
        margin = (headroom + plant_output_mw * 0.5) / max(self.demand_mw, 1.0)
        # A hockey-stick merit order: comfortable margin is cheap, tight
        # margin is very expensive, surplus goes negative.
        if margin > 0.35:
            target = 18.0 - (margin - 0.35) * 260.0
        elif margin > 0.12:
            target = 18.0 + (0.35 - margin) * 190.0
        else:
            target = 62.0 + (0.12 - margin) * 2400.0
        target = max(-70.0, min(target, 900.0))
        # Prices move in half-hourly settlement periods, not continuously.
        self.spot_price += (target - self.spot_price) * (1.0 - math.exp(-dt / 420.0))

    # -- reporting --------------------------------------------------------

    @property
    def frequency_healthy(self) -> bool:
        return abs(self.frequency - 50.0) <= 0.5

    @property
    def disconnect_required(self) -> bool:
        return abs(self.frequency - 50.0) > 0.9

    def snapshot(self) -> dict:
        return {
            "time": self.time,
            "day": self.day,
            "hour": self.hour_of_day,
            "demand_mw": self.demand_mw,
            "other_supply_mw": self.other_supply_mw,
            "frequency": self.frequency,
            "spot_price": self.spot_price,
            "wind_factor": self.wind_factor,
            "weather": self.weather_label,
            "healthy": self.frequency_healthy,
        }
