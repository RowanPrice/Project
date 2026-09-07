# How to play

You run a 3400 MW pressurised water reactor and the company that owns it. The
reactor is a machine with opinions; the company has creditors, a regulator, and
contracts it has already signed. Nothing in the simulation is on rails and
nothing is scripted. Everything that happens is the physics or the market doing
what it does.

---

## The first ten minutes

Start on **Baseload Operation**. The plant is at full power with a contract
already signed, which means it is already earning, so you have time to look
around before you touch anything.

Watch the left rail. Those readings are the ones a control room keeps in front
of the operator at all times, and they are the ones that will tell you
something is wrong before anything flashes.

Then do this, in this order:

1. **Look at the reactivity balance** on the Reactor tab. The total should be
   within a few pcm of zero. That is what "critical" means — not that anything
   is about to happen, but that production and loss are exactly in balance.
2. **Move the control banks down 1%** and watch what happens. Power falls a
   little, fuel temperature falls, and Doppler gives you some of the reactivity
   back. The reactor finds a new equilibrium on its own.
3. **Put the banks back** and go to the Thermal tab. Pull the turbine demand
   down to 80% and watch the reactor follow it down without you touching a rod.
   That is the negative moderator coefficient doing the work. Put it back to
   100% and watch power come back up.
4. **Sign a second contract** on the Commercial tab. The plant makes about
   1119 MW net; the baseload block only takes 900. Everything spare is being
   sold at whatever the spot price happens to be, which overnight is sometimes
   negative.

Now you know what the machine does. Everything after this is consequences.

---

## The five things that will kill you

### 1. Xenon

This is the one that catches everybody. Reduce power, and xenon-135 starts
building because the iodine laid down at full power keeps decaying while the
flux that was burning the xenon out has gone. It peaks about **nine hours
later** at roughly twice its equilibrium worth — five thousand pcm of negative
reactivity that was not there when you made the decision.

If you have a peaking contract at four in the afternoon, the question is not
"can I reduce power now" but "will I be able to come back up in time". Work out
the answer before you start down, not after. Buy **Incore Flux Mapping** and
the game will draw you the projected curve nine hours ahead.

If you find yourself in a pit, the correct action is almost always to accept
it, take the shortfall penalty, and wait. The incorrect action — pulling every
rod you have to chase the reactivity — is how Chernobyl happened.

### 2. Boron and the moderator coefficient

Rods are for minutes. Boron is for hours. Trying to compensate a xenon
transient with rods alone drives the banks somewhere you do not want them, and
trying to compensate a fast transient with boron does not work at all because
the dilution takes too long.

Watch the **MTC** reading. Above about 1810 ppm of boron the moderator
temperature coefficient goes positive, and a rise in coolant temperature then
*adds* reactivity instead of removing it. The self-regulating behaviour you
have been relying on inverts. The game alarms on it; take the alarm seriously.

### 3. Decay heat

Tripping the reactor stops fission in milliseconds and stops nothing else. A
core that has been at power for months is still making 6.5% of rated — 220 MW —
the instant the rods hit the bottom, 1% an hour later, and half a percent a day
later.

That heat has to reach the condenser or the atmosphere. It goes: core →
coolant → steam generators → steam dumps. Every link needs pumps, and pumps
need power. If you lose offsite power and the diesels do not start, you have
natural circulation and whatever is left in the steam generators, and about
ninety minutes.

**Passive Residual Heat Removal** is the most expensive upgrade in the game and
the only one that removes decay heat with no pumps, no power and no operator.

### 4. Load rejection

The steam dumps pass 45% of rated steam flow. If the turbine load falls further
and faster than that, the extra heat has nowhere to go, coolant temperature
climbs, and the core outlet temperature trip fires in under three minutes.

A large load reduction has to be matched by reducing reactor power at the same
time. Ramp; do not step. **Enlarged Steam Dumps** nearly doubles the margin.

### 5. Wear

Nothing in a power station stays new. Every component has a health that decays
with use and a failure hazard that follows a bathtub curve — negligible while
healthy, steep below about 35%. Overhauling something before it fails costs 55%
of a repair and, more importantly, does not happen at four in the morning
during a capacity test.

**Condition-Based Maintenance** slows wear by 35% and warns you before things
break.

---

## The money

Six kinds of arrangement, each of which asks something different of the
reactor.

| Product | Pays | Asks |
|---------|------|------|
| **Baseload** | ~£58/MWh | A flat block for days on end. Dull and safe. |
| **Load following** | ~£92/MWh | Track national demand. Xenon makes this hard, which is why it pays. |
| **Peaking** | ~£214/MWh | 1100 MW from 16:00 to 20:30 and nothing the rest of the day. The trap is being back at full power by four. |
| **Capacity** | ~£430/MW/day | A retainer for being *available*, audited by unannounced tests. Fail one and you forfeit far more than the retainer was worth. |
| **Frequency response** | ~£1250/MW/day | Answer grid frequency within seconds. A reactor cannot. The battery can. |
| **Spot** | &minus;£70 to £900/MWh | Everything not contracted, sold at whatever the market is paying right now. |

Spot prices are not decoration. On a windy Sunday night with the system long,
prices go negative and you are paying to generate. On a still winter evening
they go to several hundred pounds and being at full power is worth a fortune.
The battery exists to move energy from the first situation to the second.

Costs that never stop: staff (£148k/day), the regulator (£26k/day), the
decommissioning fund (£2.40 per MWh generated, which is a legal obligation
rather than a savings account), maintenance, fuel, and fines.

---

## The regulator

A safety score, starting at 92, which decays with trips and safety system
challenges and slowly recovers with uneventful operation. Inspections come
every two to four weeks, unannounced.

| Grade | Score | Consequence |
|-------|-------|-------------|
| Green | 85+ | No findings |
| White | 70–85 | £120k and a pointed question |
| Yellow | 50–70 | £850k, an enforcement notice, increased oversight |
| Red | 30–50 | £3.4m and special measures |
| Licence revoked | <30 | The run ends |

A radiological release beyond the site boundary costs £4.5m and 25 points, on
its own, immediately.

---

## The scenarios

**Commissioning** *(tutorial)* — Cold plant, fresh core, empty order book. Start
the coolant pumps and let their 18 MW of shaft work warm the primary circuit,
dilute boron, pull rods to criticality, and take the turbine up. Watch the
period: anything shorter than about thirty seconds means you are adding
reactivity faster than you can take it back. Watch the heat-up rate too — above
55 K/h you are damaging the pressure vessel.

**Baseload Operation** *(standard)* — A running plant and a book to fill. The
money is in what you sign on top of the block you already have.

**Load Following** *(hard)* — A week of tracking national demand between 55%
and 100% of 1000 MW. Every reduction buys a xenon transient. Plan the recovery
before you start down, and use boron for the slow half of the job.

**The Xenon Pit** *(hard)* — You came down to 20% three hours ago and xenon is
climbing towards &minus;5000 pcm. Peak cover is contracted for 16:00 at 1100 MW.
Work out whether you can get there on the reactivity you have — and if you
cannot, say so early rather than pulling every rod out to find out.

**Station Blackout** *(brutal)* — Full power, and the transmission line is about
to go. Everything you do in the first ten minutes decides how the next six
hours go.

**End of Cycle** *(hard)* — Two thirds through the fuel cycle with no fuel on
order. Enrichment takes weeks and an outage takes twenty-two days. Run the
numbers before the core runs out of reactivity and makes the decision for you.

**Sandbox** — No contracts, no regulator, unlimited money. The physics is
identical. Try withdrawing every bank at once and see how much reactivity it
takes to go prompt critical; the answer is 650 pcm and the core will not
survive the demonstration.

---

## Controls

| Key | Action |
|-----|--------|
| Space | Pause / resume |
| ↑ / ↓ | Withdraw / insert control banks by 0.2% |
| Shift + ↑ / ↓ | ...by 1% |
| B / D / H | Borate / dilute / hold |
| A | Acknowledge alarms |
| Shift + S | Scram |

The clock runs at 1×, 5×, 30×, 120× or 240×. It is automatically limited to 5×
whenever the plant is in an abnormal condition, so nobody fast-forwards through
an accident.

---

## Reading the instruments

**Reactor period** is the time for power to change by a factor of e. Infinite
means critical and steady. Anything under 30 seconds during a startup means
stop and think. It goes red under 30 seconds for a reason.

**Subcooling margin** is how many kelvin of margin the hot leg has to boiling
at the current pressure. Nominal is 18 K. Zero means there is steam in your
core, which means heat transfer has collapsed at the same moment reactivity
did, and the fuel temperature is about to do something you will not like.

**Differential worth** tells you what the next rod step is actually worth right
now. It changes by a factor of forty over the bank's travel. Check it before
you move, not after.

**Shutdown margin** is how much negative reactivity a trip would insert from
where you are standing. If it is small, a trip will not shut you down.

---

## Winning

There is no win condition, which is the point — you are running a plant, not
completing a level. What there is instead:

* **Capacity factor** — energy actually delivered against nameplate. Real
  plants achieve 90%+. It is harder than it sounds.
* **Profit** — after fuel, staff, the regulator, maintenance and the
  decommissioning fund.
* **Trips** — a good plant has none for years at a time.
* **Burnup achieved** — how much energy you got out of the fuel you bought.
* **Release** — anything above zero is a bad day. Anything above 1 is a news
  story.

The run ends when the core is destroyed, the licence is revoked, or the company
is insolvent. Two of those three are avoidable by reading this document.
