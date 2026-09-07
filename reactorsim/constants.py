"""Physical constants and plant design data for the simulation.

Every number in this module is either a genuine physical constant or a design
figure taken from the open literature on large four-loop pressurised water
reactors (the Westinghouse 4-loop / EPR class of plant).  Where a value has
been rounded or simplified for the sake of a playable simulation, the comment
says so.

Units, unless a name says otherwise:

    energy / power      MW (thermal or electric, the name says which)
    temperature         degrees Celsius, except where ``_K`` says kelvin
    pressure            MPa absolute
    mass flow           kg/s
    time                seconds
    reactivity          dimensionless dk/k -- 1 pcm = 1e-5
    concentration       atoms/cm3, or ppm by mass for boron
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Universal constants
# ---------------------------------------------------------------------------

#: Energy released per fission of U-235, recoverable in the core, in joules.
#: 200 MeV total, of which ~193 MeV is deposited locally.
ENERGY_PER_FISSION_J = 3.204e-11

#: Avogadro's number, atoms per mole.
AVOGADRO = 6.02214076e23

#: Absolute zero offset.
KELVIN_OFFSET = 273.15


# ---------------------------------------------------------------------------
# Delayed neutron data (U-235, thermal fission, six-group Keepin data)
# ---------------------------------------------------------------------------
#
# These six numbers are the entire reason a reactor can be controlled by a
# human being.  Prompt neutrons appear ~1e-5 s after fission; if they were all
# there was, a reactor 0.1% supercritical would double its power every 20 ms.
# A small fraction of neutrons instead comes from the decay of fission products
# seconds to minutes later, and it is that fraction which sets the achievable
# rate of change.
#
# (beta_i, lambda_i) -- delayed fraction and decay constant in 1/s.

DELAYED_GROUPS: tuple[tuple[float, float], ...] = (
    (0.000215, 0.0124),   # group 1, ~55.6 s half life
    (0.001424, 0.0305),   # group 2, ~22.7 s
    (0.001274, 0.1110),   # group 3, ~6.2 s
    (0.002568, 0.3010),   # group 4, ~2.3 s
    (0.000748, 1.1400),   # group 5, ~0.61 s
    (0.000273, 3.0100),   # group 6, ~0.23 s
)

#: Total delayed neutron fraction, beta.  One dollar of reactivity.
BETA_TOTAL = sum(beta for beta, _ in DELAYED_GROUPS)  # 0.006502

#: Prompt neutron generation time, Lambda, in seconds.  Typical LWR value.
GENERATION_TIME = 2.0e-5

#: Intrinsic neutron source (spontaneous fission of U-238, plus the startup
#: source assembly), as an equivalent fractional power.  This is what lets a
#: shut-down core show a readable count rate and makes subcritical
#: multiplication -- the basis of a safe approach to criticality -- work.
NEUTRON_SOURCE = 1.0e-9


# ---------------------------------------------------------------------------
# Fission product poisons
# ---------------------------------------------------------------------------
#
# Xenon-135 is the single most important transient in reactor operation. It has
# the largest thermal absorption cross-section of any known nuclide, it is
# produced mostly by the decay of iodine-135 rather than directly, and it is
# burned out by the very flux it poisons. Reduce power and iodine keeps
# decaying into xenon while the flux that was destroying it has gone: xenon
# peaks about nine hours later, deep enough to make restart impossible.  That
# is the "xenon pit", and it is what killed the Chernobyl-4 crew's night.

IODINE_YIELD = 0.06386          # fission yield of I-135 per fission
XENON_YIELD = 0.00228           # direct fission yield of Xe-135
IODINE_DECAY = 2.926e-5         # 1/s, 6.58 h half life
XENON_DECAY = 2.106e-5          # 1/s, 9.14 h half life
XENON_SIGMA_A = 2.65e-18        # cm2, 2.65 million barns at 0.0253 eV

PROMETHIUM_YIELD = 0.01071      # fission yield of Pm-149
PROMETHIUM_DECAY = 3.63e-6      # 1/s, 53.1 h half life
SAMARIUM_SIGMA_A = 4.02e-20     # cm2, 40 200 barns -- stable, so it accumulates

#: Core-average thermal flux at 100% power, n/cm2/s.
NOMINAL_FLUX = 3.0e13

#: Macroscopic fission cross-section of the core, 1/cm.  Chosen so that
#: SIGMA_F * NOMINAL_FLUX * ENERGY_PER_FISSION_J * CORE_VOLUME_CM3 equals the
#: nominal thermal power.
SIGMA_F = 0.10403

#: Macroscopic absorption cross-section of the core, 1/cm.  Poison reactivity
#: is -sigma_poison * N_poison / SIGMA_A, so this number sets the depth of the
#: xenon pit: it is tuned to give the textbook -2700 pcm equilibrium xenon.
SIGMA_A = 0.200


# ---------------------------------------------------------------------------
# Core geometry and thermal masses
# ---------------------------------------------------------------------------

NOMINAL_THERMAL_MW = 3400.0     # MW thermal at 100% power
CORE_VOLUME_CM3 = 3.4e7         # 34 m3, giving ~100 W/cm3 power density
FUEL_MASS_TU = 104.0            # tonnes of uranium in the core

#: Heat capacity of the fuel + cladding, MJ/K.  UO2 cp ~ 300 J/kg/K.
FUEL_HEAT_CAPACITY = 35.0

#: Heat capacity of the primary coolant inventory, MJ/K.  ~200 t of water at
#: 15.5 MPa, cp ~ 5.5 kJ/kg/K.
COOLANT_HEAT_CAPACITY = 1100.0

#: Heat capacity of the secondary side (steam generator inventory + steam
#: piping), MJ/K.
SECONDARY_HEAT_CAPACITY = 420.0

#: Fuel-to-coolant heat transfer coefficient at full flow, MW/K.  Sized so
#: that 3400 MW crosses a 390 K film at rated conditions.
FUEL_COOLANT_HTC = 8.72

#: Steam generator overall heat transfer, MW/K at full primary flow.
SG_HTC = 136.0

#: Primary mass flow at 100% pump speed, kg/s (four reactor coolant pumps).
FULL_PRIMARY_FLOW = 18700.0

#: Specific heat of the primary coolant, MJ/kg/K.
COOLANT_CP = 5.5e-3

#: Fraction of rated flow that natural circulation provides with every pump
#: stopped and the core hot.  Real plants see 4-8%.
NATURAL_CIRCULATION_FRACTION = 0.055

#: Reactor coolant pump flow half-life during coastdown, seconds.
PUMP_COASTDOWN_TAU = 12.0

#: Electrical load of one reactor coolant pump, MW.
PUMP_LOAD_MW = 6.5

#: Shaft work each pump puts into the coolant as heat, MW. Four pumps warm a
#: cold plant at roughly 60 K/h, which is how a real startup is done.
PUMP_HEAT_MW = 4.5


# ---------------------------------------------------------------------------
# Nominal operating point
# ---------------------------------------------------------------------------

NOMINAL_PRIMARY_PRESSURE = 15.5     # MPa
NOMINAL_COOLANT_TEMP = 310.0        # degC, T-average
NOMINAL_HOT_LEG = 326.5             # degC
NOMINAL_COLD_LEG = 293.5            # degC
NOMINAL_FUEL_TEMP = 700.0           # degC, volume-averaged
NOMINAL_STEAM_PRESSURE = 6.9        # MPa
CONDENSER_PRESSURE = 0.006          # MPa, ~40 degC saturation
AMBIENT_TEMP = 15.0                 # degC

#: Pressuriser stiffness: how far primary pressure moves per kelvin of
#: coolant average temperature change, MPa/K.  Real plants ride ~0.1-0.2.
PRESSURISER_STIFFNESS = 0.125

#: Pressuriser heater / spray authority, MPa/s at full demand.
PRESSURISER_CONTROL_RATE = 0.02

PORV_SETPOINT = 16.2                # power operated relief valve lifts
SAFETY_VALVE_SETPOINT = 17.1        # code safety valves lift
PORV_CAPACITY = 0.35                # MPa/s of relief at full lift


# ---------------------------------------------------------------------------
# Turbine and generator
# ---------------------------------------------------------------------------

#: Steam flow constant: MW of heat drawn per MPa of steam-to-condenser
#: pressure difference at a fully open turbine governor valve.
TURBINE_FLOW_COEFF = 493.0

#: Rankine cycle efficiency at rated steam conditions.
BASE_CYCLE_EFFICIENCY = 0.341

#: House load -- everything the station itself consumes other than the coolant
#: pumps, MW.
HOUSE_LOAD_MW = 22.0

#: Maximum turbine governor valve slew, fraction per second.
TURBINE_VALVE_SLEW = 0.02

#: Generator ramp limit imposed by the grid code, MW per minute.
GRID_RAMP_LIMIT_MW_PER_MIN = 55.0


# ---------------------------------------------------------------------------
# Control rods
# ---------------------------------------------------------------------------

ROD_BANKS = ("SA", "SB", "A", "B", "C", "D")
SHUTDOWN_BANKS = ("SA", "SB")
CONTROL_BANKS = ("A", "B", "C", "D")

#: Total worth of each bank in pcm when fully inserted from fully withdrawn.
#: Shutdown banks are parked out during power operation and exist to guarantee
#: shutdown margin; control banks do the work.
ROD_BANK_WORTH = {
    "SA": 3200.0,
    "SB": 3200.0,
    "A": 900.0,
    "B": 1150.0,
    "C": 1400.0,
    "D": 1750.0,
}

#: Normal drive speed, percent withdrawal per second (72 steps/min on a
#: 228-step drive is about 2.6 %/s at maximum speed).
ROD_DRIVE_SPEED = 2.4

#: Free-fall insertion time on a trip, seconds. Real plants specify < 2.7 s to
#: the dashpot for the full 3.6 m of travel.
ROD_SCRAM_TIME = 2.6


# ---------------------------------------------------------------------------
# Reactivity coefficients
# ---------------------------------------------------------------------------

#: Doppler coefficient, expressed through the square-root-of-temperature law
#: that resonance broadening actually obeys.  rho = DOPPLER_K * (sqrt(T_K) -
#: sqrt(T_ref_K)); the constant gives about -2.7 pcm/K at operating fuel
#: temperature, and a much stronger effect when the fuel is cold.
DOPPLER_K = -0.00165
DOPPLER_REF_K = 550.0

#: Moderator temperature coefficient, pcm/K, as a function of soluble boron:
#: MTC = MTC_BASE + MTC_BORON_SLOPE * ppm.  Boron is a poison dissolved in the
#: coolant, so hotter (less dense) water holds less of it -- which is why a
#: heavily borated core early in the cycle has a much weaker, and can have a
#: positive, moderator coefficient.  Operating a plant with a positive MTC is
#: prohibited above low power for exactly the reason Chernobyl demonstrated.
MTC_BASE = -58.0
MTC_BORON_SLOPE = 0.0320

#: Void coefficient, pcm per percent steam void in the core.  Strongly
#: negative in a PWR -- boiling shuts the reactor down.
VOID_COEFFICIENT = -145.0

#: Boron worth, pcm per ppm.
BORON_WORTH = -8.1

#: Reactivity held down by boron at beginning of cycle, ppm.
INITIAL_BORON_PPM = 1302.0

#: Boration and dilution rates available from the chemical and volume control
#: system, ppm per second at full demand.
BORATION_RATE = 0.55
DILUTION_RATE = 0.55


# ---------------------------------------------------------------------------
# Fuel cycle
# ---------------------------------------------------------------------------

#: Excess reactivity of fresh fuel above a critical core, per percent U-235
#: enrichment above the 0.9% that a bare core would need. Fitted so that 4.5%
#: fuel starts with roughly 26 000 pcm of excess, held down by boron and
#: burnable absorbers.
EXCESS_REACTIVITY_PER_PERCENT = 7250.0
CRITICAL_ENRICHMENT = 0.9

#: Reactivity lost per GWd/tU of burnup, pcm.  A cycle ends -- the core will no
#: longer hold criticality with all rods out and no boron -- at around
#: 50 GWd/tU for this fuel.
BURNUP_REACTIVITY_SLOPE = 520.0

#: Natural uranium assay and the tails assay of the enrichment plant.
NATURAL_ASSAY = 0.711
DEFAULT_TAILS_ASSAY = 0.25


# ---------------------------------------------------------------------------
# Damage thresholds
# ---------------------------------------------------------------------------

CLAD_DAMAGE_TEMP = 900.0        # degC, cladding starts to balloon and burst
ZIRC_OXIDATION_TEMP = 1200.0    # degC, runaway zirconium-steam reaction begins
FUEL_MELT_TEMP = 2800.0         # degC, UO2 melting point

#: Heat released by the zirconium-steam reaction, MW per K of overtemperature
#: per second, once it has started. Exothermic, self-accelerating, and the
#: source of the hydrogen that blew the roofs off at Fukushima.
ZIRC_REACTION_GAIN = 0.0085


# ---------------------------------------------------------------------------
# Reactor protection system setpoints
# ---------------------------------------------------------------------------

TRIP_HIGH_FLUX = 1.18               # fraction of nominal
TRIP_HIGH_FLUX_RATE = 0.06          # fraction per second
TRIP_LOW_FLOW = 0.87                # fraction of rated flow
TRIP_HIGH_PRESSURE = 16.4           # MPa
TRIP_LOW_PRESSURE = 13.1            # MPa
TRIP_HIGH_OUTLET_TEMP = 342.0       # degC
TRIP_HIGH_FUEL_TEMP = 1500.0        # degC
TRIP_LOW_SG_LEVEL = 0.28            # fraction of nominal inventory
TRIP_DELAY = 0.9                    # seconds from setpoint to rod release


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------

GRID_NOMINAL_FREQUENCY = 50.0       # Hz -- this is a British plant
GRID_INERTIA_CONSTANT = 0.028       # Hz per percent power imbalance
GRID_FREQUENCY_RECOVERY = 0.16      # 1/s, other generators responding
GRID_DISCONNECT_DEVIATION = 0.9     # Hz, beyond which the plant is tripped off

#: Statutory frequency band. Sustained operation outside it earns fines.
GRID_STATUTORY_BAND = 0.5
