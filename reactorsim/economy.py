"""Contracts, the market, and the books.

Electricity is sold, not merely generated.  Every megawatt-hour this plant
produces is settled against one of six kinds of arrangement, each of which
asks something different of the reactor:

``baseload``
    A flat block of power for days on end at a fixed strike price.  Easy on
    the reactor, dull, and priced accordingly.

``load_following``
    Output tracks a published schedule that follows national demand.  Pays
    well because very few nuclear plants can do it -- and the reason they
    can't is xenon: every power reduction buys a poison transient that limits
    how fast you may come back up.

``peaking``
    Deliver only during the evening peak.  Enormous prices for a few hours,
    and a reactor that has to be at full power on time, having spent the
    afternoon somewhere else.

``capacity``
    A retainer for being *available*.  Paid daily whether or not you generate,
    audited by unannounced tests: reach the contracted output within the
    response window or forfeit far more than the retainer was worth.

``frequency_response``
    Paid for reacting to grid frequency within seconds.  A reactor cannot do
    this; a battery can.  This is what the storage building is for.

``merchant``
    No contract at all -- everything spare is sold at the spot price, which is
    sometimes 400 pounds a megawatt-hour and sometimes negative.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

HOUR = 3600.0
DAY = 86400.0


@dataclass
class LedgerEntry:
    time: float
    category: str
    description: str
    amount: float          # positive is income, negative is cost


@dataclass
class Contract:
    key: str
    kind: str
    title: str
    description: str
    #: Contracted power in MW (peak, for shaped products).
    capacity_mw: float
    #: Strike price, GBP per MWh delivered.
    strike_price: float
    #: Length of the contract in days.
    duration_days: float
    #: Penalty per MWh not delivered when it was required.
    shortfall_penalty: float
    #: Paid on successful completion.
    completion_bonus: float = 0.0
    #: Forfeited if the contract is failed or abandoned.
    collateral: float = 0.0
    #: Reputation gained on completion / lost on failure.
    reputation: float = 4.0
    #: Minimum reputation required to be offered this contract.
    required_reputation: float = 0.0
    #: For capacity products: seconds allowed to reach contracted output.
    response_window: float = 1800.0

    # -- live state -------------------------------------------------------
    active: bool = False
    accepted_at: float = 0.0
    delivered_mwh: float = 0.0
    required_mwh: float = 0.0
    shortfall_mwh: float = 0.0
    earned: float = 0.0
    penalties: float = 0.0
    completed: bool = False
    failed: bool = False
    #: Capacity tests: (time, passed) records.
    tests_passed: int = 0
    tests_failed: int = 0
    _test_due: float = 0.0
    _test_active_until: float = 0.0
    _test_best: float = 0.0

    @property
    def ends_at(self) -> float:
        return self.accepted_at + self.duration_days * DAY

    def time_remaining(self, now: float) -> float:
        return max(0.0, self.ends_at - now)

    def progress(self, now: float) -> float:
        if self.duration_days <= 0:
            return 1.0
        return min(1.0, (now - self.accepted_at) / (self.duration_days * DAY))

    # -- the schedule -----------------------------------------------------

    def required_mw(self, now: float, grid) -> float:
        """Power this contract requires at this instant."""
        if not self.active:
            return 0.0
        hour = (now % DAY) / HOUR
        if self.kind == "baseload":
            return self.capacity_mw
        if self.kind == "load_following":
            # Track national demand between 55% and 100% of contracted power.
            reference = grid.demand_profile(now)
            low, high = 26000.0, 42000.0
            fraction = (reference - low) / (high - low)
            fraction = max(0.0, min(1.0, fraction))
            return self.capacity_mw * (0.55 + 0.45 * fraction)
        if self.kind == "peaking":
            return self.capacity_mw if 16.0 <= hour < 20.5 else 0.0
        if self.kind == "capacity":
            return self.capacity_mw if now < self._test_active_until else 0.0
        return 0.0

    # -- settlement -------------------------------------------------------

    def settle(self, now: float, available_mw: float, dt: float, grid) -> tuple[float, float, float]:
        """Take what this contract is owed out of ``available_mw``.

        Returns ``(taken_mw, income, penalty)``.
        """
        if not self.active:
            return 0.0, 0.0, 0.0
        hours = dt / HOUR
        required = self.required_mw(now, grid)

        if self.kind == "capacity":
            income = self.capacity_mw * self.strike_price * (dt / DAY)
            self.earned += income
            taken = 0.0
            penalty = 0.0
            if now >= self._test_due and self._test_active_until < now:
                self._test_active_until = now + self.response_window
                self._test_due = now + random.uniform(0.8, 2.6) * DAY
                self._test_best = 0.0
            if now < self._test_active_until:
                self._test_best = max(self._test_best, available_mw)
                taken = min(available_mw, self.capacity_mw)
                if self._test_best >= self.capacity_mw * 0.97:
                    self.tests_passed += 1
                    self._test_active_until = 0.0
            elif self._test_active_until and now >= self._test_active_until:
                self.tests_failed += 1
                penalty = self.shortfall_penalty
                self.penalties += penalty
                self._test_active_until = 0.0
            return taken, income, penalty

        if required <= 0:
            return 0.0, 0.0, 0.0

        self.required_mwh += required * hours
        taken = min(available_mw, required)
        self.delivered_mwh += taken * hours
        short = max(0.0, required - taken)
        self.shortfall_mwh += short * hours
        income = taken * hours * self.strike_price
        penalty = short * hours * self.shortfall_penalty
        self.earned += income
        self.penalties += penalty
        return taken, income, penalty

    @property
    def delivery_rate(self) -> float:
        if self.required_mwh <= 0:
            return 1.0
        return min(1.0, self.delivered_mwh / self.required_mwh)


def contract_catalogue(rng: random.Random, day: int) -> list[Contract]:
    """Generate the offers currently on the table.

    Offers scale with the day so a campaign escalates, and each carries a
    random price so no two runs are identical.
    """
    def jitter(value: float, spread: float = 0.12) -> float:
        return value * rng.uniform(1.0 - spread, 1.0 + spread)

    escalation = 1.0 + min(day, 120) * 0.004
    offers = [
        Contract(
            key=f"base-{day}-1",
            kind="baseload",
            title="National Grid Baseload Block",
            description=(
                "900 MW, flat, around the clock, for a fortnight. The safest money "
                "in the business and the least of it."
            ),
            capacity_mw=900.0,
            strike_price=jitter(58.0) * escalation,
            duration_days=14.0,
            shortfall_penalty=jitter(96.0),
            completion_bonus=jitter(180_000),
            collateral=250_000,
            reputation=4.0,
        ),
        Contract(
            key=f"base-{day}-2",
            kind="baseload",
            title="Aluminium Smelter Supply",
            description=(
                "1050 MW flat to a smelter. Interrupt the supply and the pot line "
                "freezes solid, which they will bill you for."
            ),
            capacity_mw=1050.0,
            strike_price=jitter(66.0) * escalation,
            duration_days=10.0,
            shortfall_penalty=jitter(310.0),
            completion_bonus=jitter(420_000),
            collateral=600_000,
            reputation=7.0,
            required_reputation=25.0,
        ),
        Contract(
            key=f"follow-{day}-1",
            kind="load_following",
            title="System Load Following Service",
            description=(
                "Track the published national demand curve between 55% and 100% of "
                "1000 MW. Every ramp down buys you a xenon transient; plan the way "
                "back up before you start down."
            ),
            capacity_mw=1000.0,
            strike_price=jitter(92.0) * escalation,
            duration_days=7.0,
            shortfall_penalty=jitter(190.0),
            completion_bonus=jitter(500_000),
            collateral=500_000,
            reputation=11.0,
            required_reputation=35.0,
        ),
        Contract(
            key=f"peak-{day}-1",
            kind="peaking",
            title="Evening Peak Cover",
            description=(
                "1100 MW between 16:00 and 20:30 only. Nothing is required of you "
                "for the other nineteen and a half hours -- which is the trap, "
                "because you must be back at full power by four."
            ),
            capacity_mw=1100.0,
            strike_price=jitter(214.0) * escalation,
            duration_days=6.0,
            shortfall_penalty=jitter(430.0),
            completion_bonus=jitter(340_000),
            collateral=450_000,
            reputation=9.0,
            required_reputation=45.0,
        ),
        Contract(
            key=f"cap-{day}-1",
            kind="capacity",
            title="Strategic Reserve Retainer",
            description=(
                "Paid every day for being able to put 850 MW on the bars within "
                "thirty minutes of a phone call that comes without warning. They "
                "will call. They enjoy calling at four in the morning."
            ),
            capacity_mw=850.0,
            strike_price=jitter(430.0),        # per MW per day
            duration_days=21.0,
            shortfall_penalty=jitter(900_000), # per failed test
            completion_bonus=jitter(250_000),
            collateral=400_000,
            reputation=8.0,
            required_reputation=15.0,
            response_window=1800.0,
        ),
        Contract(
            key=f"freq-{day}-1",
            kind="frequency_response",
            title="Dynamic Frequency Response",
            description=(
                "Hold storage in reserve and answer grid frequency within seconds. "
                "A reactor is far too slow for this. The battery is not."
            ),
            capacity_mw=180.0,
            strike_price=jitter(1250.0),       # per MW per day of availability
            duration_days=14.0,
            shortfall_penalty=jitter(60_000),
            completion_bonus=jitter(200_000),
            collateral=200_000,
            reputation=6.0,
            required_reputation=20.0,
        ),
    ]
    rng.shuffle(offers)
    return offers


@dataclass
class Finance:
    """Cash, the ledger, and everything that quietly drains the account."""

    cash: float = 12_000_000.0
    reputation: float = 20.0
    ledger: list[LedgerEntry] = field(default_factory=list)
    lifetime_income: float = 0.0
    lifetime_costs: float = 0.0
    fines: float = 0.0
    #: The decommissioning fund is a legal obligation, not a savings account.
    decommissioning_fund: float = 0.0
    #: Rolling totals for the dashboard.
    revenue_today: float = 0.0
    costs_today: float = 0.0
    _day: int = 0

    STAFF_COST_PER_DAY = 148_000.0
    REGULATORY_FEE_PER_DAY = 26_000.0
    DECOMMISSIONING_LEVY_PER_MWH = 2.4

    def record(self, time: float, category: str, description: str, amount: float) -> None:
        if abs(amount) < 1e-9:
            return
        self.cash += amount
        if amount > 0:
            self.lifetime_income += amount
            self.revenue_today += amount
        else:
            self.lifetime_costs -= amount
            self.costs_today -= amount
        self.ledger.append(LedgerEntry(time, category, description, amount))
        if len(self.ledger) > 400:
            del self.ledger[:-400]

    def daily_costs(self, time: float, dt: float, staff_multiplier: float = 1.0) -> None:
        share = dt / DAY
        self.record(time, "staff", "Operations and maintenance staff",
                    -self.STAFF_COST_PER_DAY * staff_multiplier * share)
        self.record(time, "regulator", "Regulatory oversight fee",
                    -self.REGULATORY_FEE_PER_DAY * share)
        day = int(time // DAY)
        if day != self._day:
            self._day = day
            self.revenue_today = 0.0
            self.costs_today = 0.0

    def levy(self, time: float, mwh: float) -> None:
        amount = mwh * self.DECOMMISSIONING_LEVY_PER_MWH
        if amount <= 0:
            return
        self.decommissioning_fund += amount
        self.record(time, "decommissioning", "Decommissioning fund levy", -amount)

    def fine(self, time: float, description: str, amount: float) -> None:
        self.fines += amount
        self.reputation = max(0.0, self.reputation - amount / 250_000.0)
        self.record(time, "fine", description, -amount)

    @property
    def bankrupt(self) -> bool:
        return self.cash < -5_000_000.0
