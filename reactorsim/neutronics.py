"""Neutron kinetics, fission product poisons and fuel depletion.

The core of the simulation is the point kinetics model: the reactor is treated
as a single lumped region whose power is governed by the balance between
prompt neutrons, six groups of delayed neutron precursors, and the total
reactivity presented to it.

    dn/dt = (rho - beta)/Lambda * n + sum_i lambda_i * C_i + S
    dC_i/dt = beta_i/Lambda * n - lambda_i * C_i

These equations are stiff.  Lambda is 2e-5 s while the slowest precursor group
has a 56 second half life, a spread of seven orders of magnitude, so an
explicit integrator would need microsecond steps to stay stable.  Two things
are done about that:

* Below prompt criticality the *prompt jump approximation* is used.  The
  prompt population equilibrates in microseconds, so dn/dt is set to zero and
  the flux is solved algebraically from the precursors:

      n = Lambda * (sum_i lambda_i C_i + S) / (beta - rho)

  The precursors are then advanced with an exact exponential step.  This is
  unconditionally stable, needs no sub-stepping, and reproduces the correct
  stable reactor period from the inhour equation.

* At or above prompt criticality (rho >= beta) the approximation breaks down --
  which is precisely the interesting case, because the reactor is then on a
  millisecond period and is no longer controllable.  There the model switches
  to explicit integration with a very small internal step, so that a prompt
  excursion behaves like a prompt excursion: power rises by orders of
  magnitude in tens of milliseconds until Doppler feedback in the fuel arrests
  it, having already destroyed the core.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import constants as C


def inhour_period(rho: float) -> float:
    """Return the asymptotic reactor period in seconds for a reactivity step.

    Solves the inhour equation for the stable (largest) root omega, then
    returns 1/omega.  Positive reactivity gives a positive period; negative
    reactivity asymptotes to the -80 s period set by the longest-lived
    precursor group, which is why a reactor can be brought up quickly but can
    never be shut down by rod withdrawal alone.
    """
    if abs(rho) < 1e-12:
        return math.inf

    def inhour(omega: float) -> float:
        total = C.GENERATION_TIME * omega
        for beta_i, lambda_i in C.DELAYED_GROUPS:
            total += beta_i * omega / (omega + lambda_i)
        return total - rho

    if rho > 0:
        lo, hi = 1e-9, 1.0e5
    else:
        # The stable root lies between -lambda_1 and 0.
        lo, hi = -C.DELAYED_GROUPS[0][1] + 1e-9, -1e-9

    flo = inhour(lo)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        fmid = inhour(mid)
        if (fmid < 0) == (flo < 0):
            lo, flo = mid, fmid
        else:
            hi = mid
    omega = 0.5 * (lo + hi)
    if abs(omega) < 1e-12:
        return math.inf
    return 1.0 / omega


@dataclass
class PointKinetics:
    """Neutron population and delayed precursor concentrations.

    ``power_fraction`` is n, normalised so that 1.0 is rated thermal power.
    """

    power_fraction: float = 1.0
    precursors: list[float] = field(default_factory=list)
    #: True while the model is integrating a prompt-critical excursion.
    prompt_critical: bool = False
    #: Rate of change of power, fraction per second -- drives the flux rate trip.
    power_rate: float = 0.0

    def __post_init__(self) -> None:
        if not self.precursors:
            self.set_equilibrium(self.power_fraction)

    def set_equilibrium(self, power_fraction: float) -> None:
        """Put the precursors in equilibrium with a steady power level."""
        self.power_fraction = power_fraction
        self.precursors = [
            beta_i * power_fraction / (C.GENERATION_TIME * lambda_i)
            for beta_i, lambda_i in C.DELAYED_GROUPS
        ]

    @property
    def delayed_source(self) -> float:
        return sum(
            lambda_i * conc
            for conc, (_, lambda_i) in zip(self.precursors, C.DELAYED_GROUPS)
        )

    def step(self, rho: float, dt: float) -> float:
        """Advance the neutron population by ``dt`` seconds at reactivity ``rho``.

        Returns the new power fraction.
        """
        if dt <= 0:
            return self.power_fraction
        previous = self.power_fraction

        # Prompt criticality: beta is 0.65% -- a reactivity insertion of one
        # dollar makes the chain self-sustaining on prompt neutrons alone.
        if rho >= C.BETA_TOTAL - 1e-5:
            self.prompt_critical = True
            self._step_explicit(rho, dt)
        else:
            self.prompt_critical = False
            self._step_prompt_jump(rho, dt)

        if dt > 0:
            self.power_rate = (self.power_fraction - previous) / dt
        return self.power_fraction

    # -- integrators ------------------------------------------------------

    def _step_prompt_jump(self, rho: float, dt: float) -> None:
        # Sub-step so that a fast rod motion during a long frame is still
        # resolved; 0.05 s is far finer than any precursor time constant.
        steps = max(1, min(64, int(dt / 0.05) + 1))
        h = dt / steps
        for _ in range(steps):
            denominator = max(C.BETA_TOTAL - rho, 1e-6)
            n = C.GENERATION_TIME * (self.delayed_source + C.NEUTRON_SOURCE / C.GENERATION_TIME) / denominator
            n = max(n, 0.0)
            self.power_fraction = n
            for index, (beta_i, lambda_i) in enumerate(C.DELAYED_GROUPS):
                decay = math.exp(-lambda_i * h)
                equilibrium = beta_i * n / (C.GENERATION_TIME * lambda_i)
                self.precursors[index] = (
                    self.precursors[index] * decay + equilibrium * (1.0 - decay)
                )

    def _step_explicit(self, rho: float, dt: float) -> None:
        # Prompt period at one dollar above prompt critical is ~Lambda/rho, of
        # the order of milliseconds. Integrate at 20 microseconds.
        remaining = dt
        h = 2.0e-5
        guard = 0
        while remaining > 0 and guard < 200_000:
            guard += 1
            step = min(h, remaining)
            remaining -= step
            n = self.power_fraction
            dn = ((rho - C.BETA_TOTAL) / C.GENERATION_TIME) * n + self.delayed_source + C.NEUTRON_SOURCE / C.GENERATION_TIME
            n = max(0.0, n + dn * step)
            # Runaway is capped so the simulation stays finite; by this point
            # the core is destroyed regardless.
            n = min(n, 5000.0)
            self.power_fraction = n
            for index, (beta_i, lambda_i) in enumerate(C.DELAYED_GROUPS):
                self.precursors[index] += (
                    beta_i * n / C.GENERATION_TIME - lambda_i * self.precursors[index]
                ) * step


@dataclass
class FissionProducts:
    """Iodine-135 / xenon-135 and promethium-149 / samarium-149 chains.

    Concentrations are atoms per cubic centimetre of core.
    """

    iodine: float = 0.0
    xenon: float = 0.0
    promethium: float = 0.0
    samarium: float = 0.0

    def set_equilibrium(self, power_fraction: float) -> None:
        flux = C.NOMINAL_FLUX * power_fraction
        fission_rate = C.SIGMA_F * flux
        if power_fraction <= 0:
            self.iodine = 0.0
            self.xenon = 0.0
            return
        self.iodine = C.IODINE_YIELD * fission_rate / C.IODINE_DECAY
        self.xenon = (
            (C.IODINE_YIELD + C.XENON_YIELD) * fission_rate
            / (C.XENON_DECAY + C.XENON_SIGMA_A * flux)
        )
        self.promethium = C.PROMETHIUM_YIELD * fission_rate / C.PROMETHIUM_DECAY
        self.samarium = C.PROMETHIUM_YIELD * fission_rate / (C.SAMARIUM_SIGMA_A * flux)

    def step(self, power_fraction: float, dt: float) -> None:
        """Advance both decay chains.

        Integrated analytically over the step assuming constant flux, which is
        exact for the flux-independent terms and stable for any step size the
        game will ever use.
        """
        if dt <= 0:
            return
        flux = C.NOMINAL_FLUX * max(power_fraction, 0.0)
        fission_rate = C.SIGMA_F * flux

        # Iodine: pure production and decay.
        i_decay = math.exp(-C.IODINE_DECAY * dt)
        i_equilibrium = C.IODINE_YIELD * fission_rate / C.IODINE_DECAY
        new_iodine = self.iodine * i_decay + i_equilibrium * (1.0 - i_decay)

        # Xenon: produced directly and by iodine decay, removed by its own
        # decay and by burnout in the flux. The iodine source is taken at the
        # step midpoint, which keeps the nine-hour post-trip peak accurate.
        x_removal = C.XENON_DECAY + C.XENON_SIGMA_A * flux
        iodine_mid = 0.5 * (self.iodine + new_iodine)
        x_source = C.XENON_YIELD * fission_rate + C.IODINE_DECAY * iodine_mid
        x_decay = math.exp(-x_removal * dt)
        x_equilibrium = x_source / x_removal if x_removal > 0 else 0.0
        self.xenon = self.xenon * x_decay + x_equilibrium * (1.0 - x_decay)
        self.iodine = new_iodine

        # Promethium / samarium. Samarium is stable, so it only leaves by
        # neutron capture -- it builds to equilibrium over weeks and forms a
        # permanent part of the poison load.
        p_decay = math.exp(-C.PROMETHIUM_DECAY * dt)
        p_equilibrium = C.PROMETHIUM_YIELD * fission_rate / C.PROMETHIUM_DECAY
        new_promethium = self.promethium * p_decay + p_equilibrium * (1.0 - p_decay)
        s_removal = C.SAMARIUM_SIGMA_A * flux
        s_source = C.PROMETHIUM_DECAY * 0.5 * (self.promethium + new_promethium)
        if s_removal > 1e-30:
            s_decay = math.exp(-s_removal * dt)
            self.samarium = self.samarium * s_decay + (s_source / s_removal) * (1.0 - s_decay)
        else:
            self.samarium += s_source * dt
        self.promethium = new_promethium

    @property
    def xenon_reactivity(self) -> float:
        return -C.XENON_SIGMA_A * self.xenon / C.SIGMA_A

    @property
    def samarium_reactivity(self) -> float:
        return -C.SAMARIUM_SIGMA_A * self.samarium / C.SIGMA_A


@dataclass
class FuelState:
    """Enrichment, burnup and the excess reactivity they imply."""

    enrichment: float = 4.5             # weight percent U-235
    burnup: float = 0.0                 # GWd/tU
    #: Burnable absorbers are mixed into fresh fuel to hold down the enormous
    #: excess reactivity of a new core; they burn out over the first year.
    burnable_poison: float = 1.0

    def step(self, thermal_mw: float, dt: float) -> None:
        if thermal_mw <= 0 or dt <= 0:
            return
        gigawatt_days = (thermal_mw / 1000.0) * (dt / 86400.0)
        self.burnup += gigawatt_days / C.FUEL_MASS_TU
        # Burnable absorber depletion, roughly exponential in burnup.
        self.burnable_poison = math.exp(-self.burnup / 8.0)

    @property
    def fresh_excess(self) -> float:
        return (
            max(self.enrichment - C.CRITICAL_ENRICHMENT, 0.0)
            * C.EXCESS_REACTIVITY_PER_PERCENT
            * 1e-5
        )

    @property
    def excess_reactivity(self) -> float:
        """Reactivity available from the fuel, all rods out and no boron."""
        burnt = self.burnup * C.BURNUP_REACTIVITY_SLOPE * 1e-5
        poison = self.burnable_poison * 0.11
        return self.fresh_excess - burnt - poison

    @property
    def cycle_fraction(self) -> float:
        """How far through its life the fuel is, 0 to 1."""
        end_of_life = self.fresh_excess / (C.BURNUP_REACTIVITY_SLOPE * 1e-5)
        if end_of_life <= 0:
            return 1.0
        return min(self.burnup / end_of_life, 1.0)
