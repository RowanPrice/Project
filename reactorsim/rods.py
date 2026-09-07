"""Control rod banks, their worth curves and the trip mechanism.

A control rod is not a dimmer switch.  Two details matter enormously and both
are modelled here.

**S-curve worth.**  A rod's differential worth -- the reactivity it adds per
centimetre of movement -- depends on where it already is.  Near the top or the
bottom of the core the neutron flux is low, so moving the rod there does very
little; through the middle, where the flux peaks, the same movement is worth
several times as much.  The differential worth follows sin^2(pi x), which
integrates to the familiar S-shaped integral worth curve.  In practice this
means the operator's controls change sensitivity by a factor of four or more
over the rod's travel, and a step that was safe at 90% withdrawn is not safe
at 50%.

**Drive speed.**  Rods move at a couple of percent of travel per second under
their drive motors, so reactivity cannot be added instantly -- but on a trip
the electromagnets release and the whole bank falls into the core under
gravity in under three seconds.  That asymmetry is the entire safety case: it
takes a minute to make the reactor more reactive and three seconds to make it
safe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import constants as C


def integral_worth_fraction(withdrawn: float) -> float:
    """Fraction of a bank's total worth *inserted* at the given withdrawal.

    ``withdrawn`` runs 0 (fully in) to 1 (fully out).  Returns 1 when fully
    inserted and 0 when fully withdrawn, following the integral of a
    sin^2 differential worth profile.
    """
    x = max(0.0, min(1.0, withdrawn))
    # Integral of sin^2(pi x) dx normalised to 1 over [0, 1].
    inserted = 1.0 - (x - math.sin(2.0 * math.pi * x) / (2.0 * math.pi))
    return max(0.0, min(1.0, inserted))


def differential_worth(withdrawn: float, total_worth_pcm: float) -> float:
    """Reactivity per unit fractional withdrawal, pcm, at this position."""
    x = max(0.0, min(1.0, withdrawn))
    return -total_worth_pcm * (1.0 - math.cos(2.0 * math.pi * x))


@dataclass
class RodBank:
    name: str
    total_worth_pcm: float
    #: 0.0 fully inserted, 1.0 fully withdrawn.
    position: float = 1.0
    demand: float = 1.0
    scrammed: bool = False
    #: Multiplier on the drive motor speed, raised by the rod drive upgrade.
    speed_multiplier: float = 1.0

    def step(self, dt: float) -> None:
        if self.scrammed:
            fall = dt / C.ROD_SCRAM_TIME
            self.position = max(0.0, self.position - fall)
            return
        speed = C.ROD_DRIVE_SPEED * self.speed_multiplier / 100.0 * dt
        error = self.demand - self.position
        self.position += max(-speed, min(speed, error))
        self.position = max(0.0, min(1.0, self.position))

    @property
    def inserted_worth(self) -> float:
        """Negative reactivity this bank is currently holding, in dk/k."""
        return -self.total_worth_pcm * integral_worth_fraction(self.position) * 1e-5

    @property
    def differential(self) -> float:
        """pcm per percent withdrawal at the current position."""
        return differential_worth(self.position, self.total_worth_pcm) / 100.0


@dataclass
class RodController:
    """The full set of banks plus the group-motion logic the operator uses."""

    banks: dict[str, RodBank] = field(default_factory=dict)
    scrammed: bool = False
    #: Automatic rod control keeps average coolant temperature on programme.
    automatic: bool = False

    def __post_init__(self) -> None:
        if not self.banks:
            self.banks = {
                name: RodBank(name=name, total_worth_pcm=C.ROD_BANK_WORTH[name])
                for name in C.ROD_BANKS
            }
            for name in C.SHUTDOWN_BANKS:
                self.banks[name].position = 1.0
                self.banks[name].demand = 1.0

    # -- queries ----------------------------------------------------------

    @property
    def total_reactivity(self) -> float:
        return sum(bank.inserted_worth for bank in self.banks.values())

    @property
    def control_position(self) -> float:
        """Average withdrawal of the four control banks, 0-1."""
        return sum(self.banks[name].position for name in C.CONTROL_BANKS) / len(C.CONTROL_BANKS)

    @property
    def shutdown_margin(self) -> float:
        """Reactivity that would be added by tripping from where we are now."""
        after = sum(
            -bank.total_worth_pcm * 1e-5 for bank in self.banks.values()
        )
        return self.total_reactivity - after

    def differential_worth_now(self) -> float:
        """pcm per percent of bank motion for whichever bank moves next."""
        bank = self._active_bank()
        return bank.differential if bank else 0.0

    # -- commands ---------------------------------------------------------

    def _active_bank(self) -> RodBank | None:
        """Control banks move in sequence with overlap: D out first, in last."""
        order = [self.banks[name] for name in C.CONTROL_BANKS]
        for bank in order:
            if 0.0 < bank.demand < 1.0:
                return bank
        for bank in reversed(order):
            if bank.demand < 1.0:
                return bank
        return order[0]

    def move_control_banks(self, delta: float) -> None:
        """Move the control bank group by ``delta`` (positive withdraws).

        Banks are withdrawn in sequence D, C, B, A with a 20% overlap, the way
        a real rod control system sequences its groups, so the group behaves
        like one very long rod with a smooth worth curve.
        """
        if self.scrammed:
            return
        order = [self.banks[name] for name in C.CONTROL_BANKS]
        remaining = delta
        if delta > 0:
            # Withdrawal sequence: A comes out first, D last.
            for bank in order:
                if remaining <= 0:
                    break
                room = 1.0 - bank.demand
                step = min(room, remaining)
                bank.demand += step
                remaining -= step
        else:
            # Insertion is the mirror image: D goes in first, A last.
            for bank in reversed(order):
                if remaining >= 0:
                    break
                room = bank.demand
                step = min(room, -remaining)
                bank.demand -= step
                remaining += step

    def set_bank_demand(self, name: str, value: float) -> bool:
        bank = self.banks.get(name)
        if bank is None or self.scrammed:
            return False
        bank.demand = max(0.0, min(1.0, value))
        return True

    def scram(self) -> None:
        self.scrammed = True
        for bank in self.banks.values():
            bank.scrammed = True
            bank.demand = 0.0

    def reset(self) -> None:
        """Reset the trip breakers.  Rods stay where they fell; the operator
        must withdraw them again, which is exactly how a restart works."""
        self.scrammed = False
        for bank in self.banks.values():
            bank.scrammed = False
            bank.demand = bank.position

    def set_speed_multiplier(self, value: float) -> None:
        for bank in self.banks.values():
            bank.speed_multiplier = value

    def step(self, dt: float) -> None:
        for bank in self.banks.values():
            bank.step(dt)
