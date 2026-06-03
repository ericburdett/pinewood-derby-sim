"""RaceResult and its sub-objects (Outcome, EnergyLedger, NormalForces, TrajectoryPoint).

The simulation output is dumb, immutable data (TRD §3 data model): the engine
computes the physics and packs the answer into these frozen dataclasses so the
deferred UI can read and animate the run without re-simulating. No physics or
behavior lives here — only the contract.

Traceability (PRD §6 Output contract; TRD §3/§11):

- AC-O1: ``RaceResult`` exposes ``outcome``, ``race_time_s`` (``None`` iff not
  FINISHED), ``exit_velocity``, ``top_speed``, ``finish_velocity``, ``energy``,
  ``normal_forces`` (``front``/``rear``), ``legal_weight``, and a down-sampled
  ``trajectory`` of ``TrajectoryPoint``s (``t``/``position``/``velocity``/``angle``).
  Every value type is a frozen dataclass; ``trajectory`` is a tuple, so the whole
  result is immutable.
- AC-O2: FINISHED ⇒ ``race_time_s`` is a positive finite float; DNF ⇒
  ``race_time_s is None``.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Outcome(enum.Enum):
    """How the run ended (TRD §3)."""

    FINISHED = "finished"   # the car reached the end of the track
    DNF = "dnf"             # unstable: front lifts / wobble crash (spec §4.2)


@dataclass(frozen=True)
class NormalForces:
    """Axle normal forces on the flat (spec §4.1), in newtons."""

    front: float    # N_f
    rear: float     # N_r


@dataclass(frozen=True)
class EnergyLedger:
    """The per-force energy breakdown of a run, in joules (spec §2).

    The ledger closes by construction (discrete work-energy theorem): the gravity
    work less the friction/drag/rail losses equals the final kinetic energy.
    """

    pe_initial: float           # M·g·Δh_com
    ke_linear_final: float      # ½·M·v²
    ke_rotational_final: float  # Σ ½·I·ω²
    w_gravity: float            # Σ F_gravity·dx
    w_drag: float               # Σ F_drag·dx
    w_axle: float               # Σ F_axle·dx
    w_rail: float               # Σ F_rail·dx


@dataclass(frozen=True)
class TrajectoryPoint:
    """A down-sampled snapshot of the run for the UI to animate (PRD A7)."""

    t: float            # seconds since release
    position: float     # arc-position along the track [m]
    velocity: float     # linear speed [m/s]
    angle: float        # track angle at this position [rad]


@dataclass(frozen=True)
class RaceResult:
    """The immutable result of a single ``simulate(...)`` call (TRD §3).

    ``race_time_s`` is a positive finite float for a FINISHED run and ``None`` for a
    DNF (the "None iff not FINISHED" biconditional, AC-O2).
    """

    outcome: Outcome
    race_time_s: float | None               # None iff not FINISHED
    exit_velocity: float                     # v at the end of the ramp [m/s]
    top_speed: float                         # max v over the run [m/s]
    finish_velocity: float                   # v at the finish line [m/s]
    energy: EnergyLedger
    normal_forces: NormalForces
    legal_weight: bool                       # M ≤ M_max
    trajectory: tuple[TrajectoryPoint, ...]  # down-sampled (≤ ~500 pts)
