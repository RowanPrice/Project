# The physics

Every number in this simulation is either a physical constant, a design figure
from the open literature on large pressurised water reactors, or something
derived from those two. Where a value has been chosen to make the game
playable rather than to match a specific plant, the code says so.

This document explains what is modelled and why it behaves the way it does.
The tests in `tests/` check these claims against published values, so if the
model drifts away from the physics the test suite fails.

---

## 1. Neutron kinetics

### The problem

A fission chain reaction is governed by one number: **reactivity**, written
&rho;, the fractional departure of the neutron multiplication factor from one.

```
rho = (k - 1) / k
```

It is a tiny quantity and is quoted in **pcm** — parts per hundred thousand, so
1 pcm = 10⁻⁵.

If every neutron from fission appeared immediately, a reactor would be
uncontrollable. The prompt neutron generation time &Lambda; in a light water
reactor is about 2×10⁻⁵ seconds, so a core held 0.1% supercritical on prompt
neutrons alone would double its power every twenty milliseconds. No operator,
and no control system, could live with that.

### Delayed neutrons

A small fraction of neutrons — &beta; = 0.0065 for U-235, so about one in 150 —
does not come from fission directly. It comes from the beta decay of certain
fission products seconds to minutes later. Those neutrons arrive far too late
to matter to the prompt chain, but they matter enormously to its *average*
timing, because the reactor cannot sustain itself without them until &rho;
reaches &beta;.

Below &rho; = &beta; the reactor is **delayed critical**: the rate of change of
power is set by radioactive decay, on a timescale of tens of seconds. At
&rho; = &beta; it is **prompt critical**: the chain sustains itself on prompt
neutrons alone and the reactor is gone. This is why &beta; is called a
*dollar* of reactivity, and why every operating limit in a power reactor is
expressed as a fraction of it.

`reactorsim/constants.py` carries the standard six-group Keepin data:

| Group | &beta;ᵢ | &lambda;ᵢ (s⁻¹) | Half life |
|-------|---------|-----------------|-----------|
| 1 | 0.000215 | 0.0124 | 55.6 s |
| 2 | 0.001424 | 0.0305 | 22.7 s |
| 3 | 0.001274 | 0.111 | 6.2 s |
| 4 | 0.002568 | 0.301 | 2.3 s |
| 5 | 0.000748 | 1.14 | 0.61 s |
| 6 | 0.000273 | 3.01 | 0.23 s |

### The equations

```
dn/dt   = (rho - beta)/Lambda * n + sum_i lambda_i * C_i + S
dC_i/dt = beta_i/Lambda * n - lambda_i * C_i
```

`n` is the neutron population, normalised so that 1.0 is rated power. `Cᵢ` are
the delayed neutron precursor concentrations. `S` is an intrinsic source —
spontaneous fission of U-238 plus the startup source assembly — which is what
lets a shut-down core show a readable count rate and makes a safe approach to
criticality possible.

### How they are solved

These equations are notoriously **stiff**. &Lambda; is 2×10⁻⁵ s while the
slowest precursor group has a 56 second half life: seven orders of magnitude.
An explicit integrator would need microsecond steps to stay stable, and this
game runs at up to 240× real time.

Two regimes, two methods:

**Below prompt critical**, the model uses the **prompt jump approximation**.
The prompt population equilibrates in microseconds, so d*n*/d*t* is set to zero
and the flux is solved algebraically from the precursors:

```
n = Lambda * (sum_i lambda_i C_i + S/Lambda) / (beta - rho)
```

The precursors are then advanced with an exact exponential step. This is
unconditionally stable, needs no sub-stepping, and reproduces the correct
stable reactor period from the inhour equation. It also produces the *prompt
jump* itself — the instantaneous factor &beta;/(&beta;&minus;&rho;) by which
power steps the moment reactivity changes, before any delayed neutron has
responded.

**At or above prompt critical** the approximation breaks down, which is exactly
the interesting case. There the model switches to explicit integration at a
20 microsecond internal step, so a prompt excursion behaves like one: power
rises by orders of magnitude in tens of milliseconds until Doppler feedback in
the fuel arrests it, having already destroyed the core.

### Reactor period

The **inhour equation** relates a reactivity to the asymptotic exponential
period the reactor settles onto:

```
rho = Lambda * omega + sum_i (beta_i * omega) / (omega + lambda_i)
```

`reactorsim/neutronics.py` solves it by bisection for the stable root and
returns 1/&omega;. Some values it produces, all of which match the standard
tables:

| Reactivity | Period |
|-----------:|-------:|
| +100 pcm | 54.9 s |
| +200 pcm | 24 s |
| +500 pcm | 1.2 s |
| &minus;100 pcm | &minus;51 s |
| &minus;1000 pcm | &minus;83 s |
| &minus;10000 pcm | &minus;80 s |

Note the asymmetry, which is the single most important operational fact about
a reactor. Positive reactivity can produce arbitrarily short periods. Negative
reactivity cannot: however much you insert, power cannot fall faster than the
longest-lived precursor group allows, about &minus;80 seconds. **A reactor can
be made fast quickly and slow only slowly**, which is why control is about not
getting into trouble rather than getting out of it.

---

## 2. Fission product poisons

### Xenon-135

Xenon-135 has the largest thermal neutron absorption cross-section of any known
nuclide: 2.65 million barns, roughly 2.65×10⁻¹⁸ cm². At equilibrium in a power
reactor it is worth about &minus;2700 pcm, which is a large fraction of the
reactivity a core has available.

What makes it dangerous is not its size but its *dynamics*. Xenon-135 is
produced mostly not by fission directly but by the decay of iodine-135 (6.6
hour half life), and it is destroyed both by its own decay (9.1 hours) and by
absorbing the very neutrons it is poisoning.

```
dI/dt  = gamma_I * Sigma_f * phi - lambda_I * I
dXe/dt = gamma_Xe * Sigma_f * phi + lambda_I * I - lambda_Xe * Xe - sigma_Xe * phi * Xe
```

Reduce power, and the flux term that was burning xenon out disappears while the
iodine inventory laid down at full power keeps decaying into more of it. Xenon
therefore **rises after a power reduction**, peaks around nine hours later at
roughly twice its equilibrium worth, and only then decays away.

This model reproduces that: from full power equilibrium of &minus;2720 pcm, a
trip drives xenon to about &minus;5200 pcm eight and a half hours later. That
is the **xenon pit**, and it is deep enough that a core which could have been
restarted immediately after the trip cannot be restarted at all four hours
later, and will not be restartable for the best part of a day.

Every operator knows this. On 26 April 1986 the night shift at Chernobyl-4
found themselves in a xenon pit after an unplanned power reduction and pulled
rods to get out of it. The reactivity they needed was greater than the
reactivity they had in hand, and by the time they had enough neutrons they had
no shutdown margin left.

### Samarium-149

Samarium-149 is the same idea with the drama removed. It builds through
promethium-149, absorbs at 41 000 barns, and — crucially — is **stable**. It
does not decay away when the reactor shuts down. It grows to about &minus;550
pcm and stays, forming a permanent part of the poison load until refuelling.

---

## 3. Reactivity balance

Total reactivity is the sum of eight terms, each with its own timescale:

| Term | Typical magnitude | Timescale | Set by |
|------|------------------|-----------|--------|
| Fuel | +26 000 pcm fresh | months | enrichment, burnup |
| Rods | 0 to &minus;11 600 pcm | seconds | the operator |
| Boron | 0 to &minus;21 000 pcm | hours | the operator |
| Doppler | &minus;1300 pcm at power | **instant** | fuel temperature |
| Moderator | &plusmn;a few hundred pcm | seconds | coolant temperature |
| Void | 0 to &minus;14 500 pcm | seconds | steam in the core |
| Xenon | 0 to &minus;5200 pcm | hours | power history |
| Samarium | &minus;550 pcm | weeks | burnup |

### Doppler

As fuel heats, thermal broadening of the U-238 absorption resonances captures
more neutrons. The effect is **instantaneous** — it acts at the speed of heat
appearing in a fuel pellet, not at the speed of anything moving — and it is
**always negative**. It is the reason a prompt excursion terminates itself
rather than continuing until the core has vaporised.

Resonance broadening goes as the square root of absolute temperature, so the
model uses the physically correct form rather than a linear coefficient:

```
rho_doppler = K * (sqrt(T_fuel) - sqrt(T_ref))
```

which gives about &minus;2.7 pcm/K at operating temperature and a much stronger
effect when the fuel is cold.

### Moderator temperature coefficient, and why boron matters

Hotter water is less dense, so it moderates less well, so fewer neutrons are
thermalised. In a well-designed PWR that is a strongly negative coefficient,
around &minus;45 pcm/K, and it is what makes the plant self-regulating.

But boron is dissolved *in the water*. Less dense water holds less boron, and
less boron means less absorption — a positive contribution that grows with
concentration. The net coefficient is modelled as

```
MTC = -58 + 0.032 * boron_ppm   pcm/K
```

so above about 1810 ppm the moderator coefficient goes **positive**, and a rise
in coolant temperature then *adds* reactivity instead of removing it. Operating
a power reactor in that condition is prohibited, and the game raises an alarm
when it happens. It is the same class of design fault — a positive coefficient
in a feedback loop — that made RBMK-1000 lethal at low power.

### Void

Steam in the core is a far worse moderator than water and a far worse coolant,
so the void coefficient in a PWR is strongly negative: &minus;145 pcm per
percent void. Boiling shuts the reactor down. It also destroys heat transfer
from the fuel, so the fuel temperature runs away even as reactor power falls —
which is why loss of subcooling margin is treated as an emergency here.

---

## 4. Control rods

Two properties matter and both are modelled.

**Differential worth follows sin²(&pi;x).** A rod's worth per centimetre of
travel depends on the neutron flux where the rod is. Near the top or bottom of
the core the flux is low and the rod does almost nothing; through the middle,
where the flux peaks, the same movement is worth several times as much.
Integrating gives the familiar S-shaped integral worth curve. In this model the
control group is worth 35 pcm per percent of travel at mid-position and 0.9 pcm
per percent near the top — a factor of forty. A step that is harmless at 95%
withdrawn is not harmless at 50%.

**Drive speed and scram time are asymmetric.** Rods move at 2.4% of travel per
second under their motors, so reactivity cannot be added quickly. On a trip the
electromagnets release and the whole bank falls into the core under gravity in
2.6 seconds. That asymmetry *is* the safety case: a minute to make the reactor
more reactive, three seconds to make it safe.

Banks are sequenced with overlap — A withdraws first and inserts last — so the
group behaves like one very long rod with a smooth worth curve.

---

## 5. Thermal hydraulics

Four lumped-capacity nodes, coupled by heat flows:

```
fuel  --(film)-->  coolant  --(steam generator)-->  secondary  --(turbine)--> grid
```

| Node | Heat capacity | Time constant |
|------|--------------|---------------|
| Fuel | 35 MJ/K | ~4 s |
| Primary coolant | 1100 MJ/K | ~8 s |
| Secondary | 420 MJ/K | ~3 s |

The fuel and coolant nodes are advanced by **exponential relaxation** rather
than forward Euler:

```
T <- T + (T_equilibrium - T) * (1 - exp(-dt / tau))
```

This is exact for a constant driving temperature and unconditionally stable for
any step size, which matters because a forward Euler scheme on a 4 second time
constant goes unstable above about 8 seconds and this game runs 30 second
sub-steps at high speed. The secondary side cannot be solved that way — steam
pressure depends on saturation temperature through a table that cannot be
inverted analytically — so it guards itself with a half-second internal step.

### The reactor follows the turbine

This is the defining behaviour of a pressurised water reactor and it is not
scripted anywhere. It emerges from the negative moderator coefficient plus the
steam generator heat balance:

1. Open the turbine governor valve.
2. More heat leaves the secondary side, so the steam generators cool.
3. Cooler steam generators pull more heat out of the primary circuit.
4. Primary coolant average temperature falls.
5. A negative moderator coefficient turns that fall into positive reactivity.
6. Reactor power rises to meet the new load and settles when temperature is
   back where it started.

Nobody moved a control rod. Close the valve and the reverse happens. Learning
to work with this rather than against it is most of the skill in operating a
PWR, and the game gives you an automatic rod control system only as a purchased
upgrade, so you have to understand it first.

### Steam tables

Saturation temperature and pressure come from a 34-point tabulation with
logarithmic interpolation in pressure, accurate to better than 0.5 K across the
whole operating range:

| Pressure | This model | Steam tables |
|---------:|-----------:|-------------:|
| 0.1 MPa | 99.6 °C | 99.6 °C |
| 6.9 MPa | 284.8 °C | 285.0 °C |
| 15.5 MPa | 344.8 °C | 344.8 °C |

### Decay heat

When the rods drop, the fission chain stops in milliseconds. The core does not.
Fission products keep decaying, and the Wigner-Way correlation gives the
fraction of pre-shutdown power still being produced:

```
P(t)/P0 = 0.066 * [ t^-0.2 - (t + T_operating)^-0.2 ]
```

For a core that has run a year at full power that is about **6.5% at the
instant of the trip** — 220 MW on this plant — 1.1% after an hour and 0.5%
after a day. It has to go somewhere. Removing it is what the steam dumps, the
feedwater system, the coolant pumps and the emergency diesels all exist to do,
and it is why a station blackout is lethal rather than merely inconvenient.

A core that has only run for twenty minutes has almost no decay heat, which the
correlation handles correctly and which changes how a scenario plays.

### Pressuriser

The pressuriser is a steam bubble on a standpipe off the hot leg. Coolant
expansion surges into it and compresses the bubble; contraction surges out and
expands it. Heaters and sprays then restore the setpoint, but only at a finite
rate, so what the operator sees on every temperature change is a pressure
*transient* followed by a recovery — not a permanent offset.

The asymmetry matters: the bubble collapses as fast as physics allows, while
the heaters push back at 0.02 MPa/s. A leak therefore shows on the pressure
gauge long before it shows anywhere else.

Above 16.2 MPa the power operated relief valve lifts, losing inventory and
releasing a little activity. Above 17.1 MPa the code safety valves lift.

### Damage

| Temperature | What happens |
|------------:|--------------|
| 900 °C | Cladding balloons and bursts; fission gas released |
| 1200 °C | Zirconium-steam reaction begins: exothermic, self-accelerating, produces hydrogen |
| 2800 °C | UO₂ melts |

The zirconium-steam reaction is modelled as a positive feedback on fuel
temperature, because that is what it is. It is what turned three damaged cores
into hydrogen explosions at Fukushima Daiichi.

---

## 6. Fuel cycle

Fresh 4.5% enriched fuel carries about 26 000 pcm of excess reactivity — far
more than the core needs — held down by soluble boron and by burnable absorbers
mixed into the pellets. Burnup consumes it at about 520 pcm per GWd/tU, and the
cycle ends when the core can no longer hold criticality with all rods out and
no boron, at around 50 GWd/tU. On this plant that is roughly eighteen months.

### Enrichment

Natural uranium is 0.711% U-235 and a PWR wants around 4.5%. The work of
separating isotopes is measured in **separative work units**, and the maths is
exact rather than approximated:

```
V(x)    = (2x - 1) * ln( x / (1 - x) )
F/P     = (x_p - x_w) / (x_f - x_w)
SWU/kg  = V(x_p) + (F/P - 1) * V(x_w) - (F/P) * V(x_f)
```

For 4.5% product from natural feed at 0.25% tails this gives 9.22 kg of natural
uranium and 6.87 SWU per kilogram of fuel, which is the number the industry
quotes.

The **tails assay is a real decision**, not a slider. Drive it down and each
kilogram of product needs less natural uranium but far more separative work:

| Tails assay | Feed per kg | SWU per kg |
|------------:|------------:|-----------:|
| 0.15% | 7.75 kg | 8.80 |
| 0.25% | 9.22 kg | 6.87 |
| 0.35% | 11.50 kg | 5.71 |

Uranium and SWU have separate prices which move independently, so the optimum
moves, and finding it is worth real money.

---

## 7. What is deliberately simplified

Honesty about the boundaries of the model:

* **The core is a point.** There is no axial or radial flux shape, so no axial
  offset control, no xenon oscillations in space, and no local peaking factors.
  Spatial xenon instability is a genuine operational concern in large cores and
  it is not here.
* **One coolant loop.** The four loops are lumped into one, so a single loop
  isolation or an asymmetric cooldown cannot be represented.
* **No boiling crisis.** Departure from nucleate boiling is approximated by
  degrading heat transfer with void fraction rather than by a proper DNB ratio
  correlation.
* **Chemistry is one number.** Boron concentration is uniform and instantaneous
  throughout the primary circuit; there is no mixing delay and no crud.
* **Containment is not modelled.** Radioactive release is tracked as a single
  scalar rather than as a source term through a building.
* **Neutron flux is one energy group.** Real analysis uses at least two.

None of these changes the behaviour the game is about. All of them would matter
if you were licensing a reactor.
