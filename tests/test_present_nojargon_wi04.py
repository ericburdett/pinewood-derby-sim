"""WI04-PRESENT-NOJARGON — RED tests for the banned-terms (no-jargon) guard.

Acceptance criteria (PRD AC-X3; TRD §4 / §11 "banned-terms guard shared by
``test_present.py`` and a UI text scan"):

- **AC-1 (no jargon in any emitted string):** no technical unit or term (Joules,
  Newtons, coefficient, m/s², ``C_d``, ``μ``/``mu``, "moment of inertia", "normal
  force", and the rest of the agreed banned-term list) appears in **any** string field
  of **any** ``RaceView`` — ``headline``, ``why``, every ``tips`` entry, every
  ``breakdown`` bar ``label`` (and ``key``), and (defensively) ``outcome`` — across a
  **matrix of designs**: finished, tipped, stalled × legal, over-limit (PRD AC-X3).
- **AC-2 (reusable checker exposed):** a single reusable banned-terms checker is exposed
  from ``pinewood_derby.present`` — a shared ``BANNED_TERMS`` list plus a pure
  ``find_banned_terms(text) -> list[str]`` — so the **same** list backs both this pytest
  guard and the later UI text scan (TRD §11). It is pure, case-insensitive, and matches
  the spelled-out *and* symbol forms of the units (``μ`` and ``mu``; ``m/s²`` and ``m/s2``).
- **AC-3 (guard fails on any new banned term):** the guard is a pytest test that **fails
  if any newly emitted string introduces a banned term** — proven here by feeding the
  *exposed checker* deliberately jargon-laced strings (it must flag them) and by scanning
  a synthetic ``RaceView`` whose fields carry jargon (the scan must fail it). A guard that
  only ever sees today's clean copy could pass vacuously; these tests prove it actually
  bites.

These tests drive ``present()`` with **real ``simulate()`` output** (no hand-built
``RaceResult`` fixtures, TRD §12) and are deterministic: one fixed seed, ``dt = 1e-3``,
no clock / network / unseeded RNG.

True RED: the reusable checker (``BANNED_TERMS`` / ``find_banned_terms``) does **not**
exist in ``pinewood_derby.present`` yet, so every criterion fails on the missing public
symbol — a real per-criterion RED, not a happy-path leak. Imports of the checker live
*inside* each test body so a missing symbol fails each test independently rather than
aborting whole-file collection.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

import pytest

from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
from pinewood_derby.engine import simulate
from pinewood_derby.result import Outcome
from pinewood_derby.track import STANDARD_TRACK
from pinewood_derby.units import Length, Mass

if TYPE_CHECKING:
    from pinewood_derby.present import RaceView
    from pinewood_derby.result import RaceResult

# The fixed seed the UI pins so a design's emitted copy is reproducible (PRD A6).
FIXED_SEED = 0

# The agreed banned-term list (PRD AC-X3 enumerates "Joules, Newtons, coefficient,
# m/s², C_d, μ, 'moment of inertia', 'normal force'" and "the rest of an agreed
# banned-term list"). These are the terms a *test in this repo* expects the exposed,
# shared ``BANNED_TERMS`` checker to catch. Each must never appear (case-insensitively)
# in any kid-facing string (PRD AC-X3; profile "Constraints": nothing technical reaches
# the kid). This is the test's INDEPENDENT expectation — the SUT ships its own
# ``BANNED_TERMS``; ``test_exposed_banned_terms_cover_the_agreed_list`` asserts the SUT's
# list is a superset of this agreed core, so the two cannot silently drift apart.
EXPECTED_BANNED_TERMS = (
    # Energy / force units (spelled out and symbol forms).
    "joule",
    "joules",
    "newton",
    "newtons",
    "watt",
    "kilogram",
    # Velocity / acceleration units (symbol and spelled-out).
    "m/s",
    "m/s2",
    "m/s²",
    "meters per second",
    "metres per second",
    # The generic "coefficient" plus the named coefficients.
    "coefficient",
    "c_d",
    "drag coefficient",
    "friction coefficient",
    # Greek / symbol jargon for the friction coefficient.
    "μ",
    "mu_axle",
    # Physics terms that must never reach a kid.
    "moment of inertia",
    "rotational inertia",
    "normal force",
    "kinetic energy",
    "potential energy",
    "integration",
    "trajectory",
    # Raw engine ledger field names must never surface as copy.
    "w_drag",
    "w_axle",
    "w_rail",
    "w_gravity",
    "ke_linear",
    "ke_rotational",
    "pe_initial",
    "d_com",
    "proportion",
    # Internal physics phrasing the engine/present modules use behind the boundary.
    "front-load fraction",
    "stability cliff",
)


# ───────────────────────────────────────────────────────────────────────────── #
# Fixtures — real value objects, real engine (TRD §12). The matrix below realises
# every reachable (outcome × legality) combination on the STANDARD_TRACK.
# ───────────────────────────────────────────────────────────────────────────── #
def _wheels(*, count_touching: int = 4) -> Wheels:
    return Wheels(
        count_touching=count_touching,
        wheel_mass=Mass.from_ounces(0.09),
        outer_radius=Length.from_inches(0.595),
        inner_radius=Length.from_inches(0.37),
        axle_radius=Length.from_inches(0.045),
    )


def _car(
    *,
    mass_oz: float,
    com_in: float = 0.85,
    mu: float = 0.20,
    cd: float = 0.30,
    alignment: str = "STRAIGHT",
    count_touching: int = 4,
) -> CarDesign:
    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_in),
        wheelbase=Length.from_inches(4.375),
        wheels=_wheels(count_touching=count_touching),
        body=BodyShape(drag_coefficient=cd, frontal_area=0.0028),
        axle=Axle(friction_coefficient=mu),
        alignment=Alignment[alignment],
    )


# Matrix of designs spanning every reachable outcome × legality combination plus a few
# control/axle/wheel/body permutations, so the jargon scan exercises every coaching
# branch (axle/rails/air/wheels "why" + tips, placement & weight tips, finisher praise,
# the tipped fix, and the stalled-under-energised message). A heavy *over-limit* car
# always finishes (more mass overcomes friction), so "stalled over-limit" is physically
# unreachable on this track and is intentionally absent (not a coverage gap).
_MATRIX: dict[str, CarDesign] = {
    # ── finished ───────────────────────────────────────────────────────────── #
    "finished_legal_baseline": _car(mass_oz=5.0),
    "finished_legal_railrider_wedge_polished": _car(
        mass_oz=5.0, mu=0.10, cd=0.20, alignment="RAIL_RIDER"
    ),
    "finished_legal_3wheel": _car(mass_oz=5.0, count_touching=3),
    "finished_legal_block_unprepared": _car(mass_oz=4.5, mu=0.30, cd=0.85),
    "finished_legal_forward_com": _car(mass_oz=5.0, com_in=2.0),
    "finished_overlimit": _car(mass_oz=6.0),
    "finished_overlimit_block": _car(mass_oz=6.5, mu=0.30, cd=0.85),
    # ── tipped (unstable: rearward COM below the cliff) ──────────────────────── #
    "tipped_legal": _car(mass_oz=5.0, com_in=0.15),
    "tipped_overlimit": _car(mass_oz=6.0, com_in=0.15),
    # ── stalled (light, high-friction legal car that runs out of speed) ──────── #
    "stalled_legal": _car(mass_oz=1.0, mu=0.35, cd=0.85),
    "stalled_legal_railrider": _car(mass_oz=1.0, mu=0.35, cd=0.85, alignment="RAIL_RIDER"),
}


def _simulate(car: CarDesign) -> RaceResult:
    return simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED)


def _present(car: CarDesign) -> RaceView:
    from pinewood_derby.present import present

    return present(_simulate(car), car)


def _iter_view_strings(obj: Any) -> list[str]:
    """Flatten every string a view-model RENDERS TO THE KID (RaceView/payload string
    *values*: headline, why, tips, breakdown labels, outcome) for the jargon scan.

    PRD AC-X3 governs the text shown to the user. Dict **keys** are structural
    identifiers the JS bridge/animator address by name (e.g. ``trajectory``), never
    rendered to the kid, so they are NOT scanned — the animator legitimately needs a
    ``trajectory`` data key (PRD AC-R1) and that data-contract name must not be policed
    by a guard that only applies to rendered copy. (Adjudicated 2026-06-03: scanning
    keys here contradicted the AC-R1 ``to_json`` trajectory-key test; re-scoped to
    values, where every kid-facing string actually lives.)"""
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_iter_view_strings(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_iter_view_strings(v))
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            out.extend(_iter_view_strings(getattr(obj, f.name)))
    return out


# ───────────────────────────────────────────────────────────────────────────── #
# Sanity guard — confirm the matrix actually realises the intended engine states, so a
# later engine change that, say, moved the stability cliff can't silently hollow the
# scan (pins the TEST INPUTS, not the SUT).
# ───────────────────────────────────────────────────────────────────────────── #
def _design_state(result: RaceResult) -> str:
    """Classify a design by the engine's own evidence (TRD §4) — the durable invariant,
    independent of the not-yet-implemented view ``outcome`` label (that distinction is a
    separate work item; WI04 only owns the jargon guard):

    - ``finished`` — ``outcome=FINISHED``.
    - ``tipped`` — a DNF the engine short-circuited before the run: single at-rest
      trajectory point at position 0 with an all-zero ledger.
    - ``stalled`` — a DNF that ran (multi-point trajectory) but ran out of speed.
    """
    if result.outcome is Outcome.FINISHED:
        return "finished"
    if len(result.trajectory) == 1 and result.trajectory[0].position == 0.0:
        return "tipped"
    return "stalled"


def test_matrix_realises_finished_tipped_and_stalled_states() -> None:
    """The design matrix spans all three engine states across legal & over-limit so the
    jargon scan exercises every coaching branch (PRD AC-X3 'across a matrix of designs:
    finished, tipped, stalled, legal, over-limit'). Classification uses the ENGINE's
    evidence, not the view ``outcome`` label, so WI04 stays decoupled from the separate
    tipped/stalled labeling work item."""
    from pinewood_derby.present import present

    seen_states: set[str] = set()
    seen_legal: set[bool] = set()
    for name, car in _MATRIX.items():
        result = _simulate(car)
        view = present(result, car)
        seen_states.add(_design_state(result))
        seen_legal.add(view.legal_weight)
        if name.startswith("finished"):
            assert view.finished is True, f"{name} should be a finisher"
        else:
            assert view.finished is False, f"{name} should be a non-finisher"
    assert seen_states == {"finished", "tipped", "stalled"}, (
        f"matrix must cover all three engine states; saw {seen_states}"
    )
    assert seen_legal == {True, False}, "matrix must cover legal AND over-limit cars"


def test_tipped_and_stalled_fixtures_match_their_engine_signatures() -> None:
    """Pin the engine truth: the 'tipped' fixtures are pre-run instability short-circuits
    (single at-rest point, all-zero ledger) and the 'stalled' fixtures are multi-point
    non-finishes — so the matrix names map to the real engine states (TRD §4)."""
    tip = _simulate(_MATRIX["tipped_legal"])
    assert tip.outcome is Outcome.DNF and len(tip.trajectory) == 1
    assert tip.trajectory[0].position == 0.0 and tip.energy.w_gravity == 0.0

    stall = _simulate(_MATRIX["stalled_legal"])
    assert stall.outcome is Outcome.DNF and len(stall.trajectory) > 1


# ───────────────────────────────────────────────────────────────────────────── #
# AC-2 — A reusable banned-terms checker is exposed from pinewood_derby.present so the
# SAME list backs this pytest guard AND the later UI text scan (TRD §4 / §11).
# ───────────────────────────────────────────────────────────────────────────── #
def test_banned_terms_list_is_exposed_and_nonempty() -> None:
    """``pinewood_derby.present`` exposes a shared ``BANNED_TERMS`` collection of jargon
    strings — the single source of truth shared with the UI text scan (TRD §11)."""
    from pinewood_derby.present import BANNED_TERMS

    terms = list(BANNED_TERMS)
    assert len(terms) > 0, "BANNED_TERMS must be a non-empty list of jargon strings"
    assert all(isinstance(t, str) and t for t in terms), (
        "every banned term must be a non-empty string"
    )


def test_find_banned_terms_is_exposed_and_callable() -> None:
    """``find_banned_terms(text) -> list[str]`` is the exposed reusable checker the UI
    text scan reuses; on clean text it returns an empty list."""
    from pinewood_derby.present import find_banned_terms

    hits = find_banned_terms("Polish your axles so the wheels spin freely.")
    assert isinstance(hits, list)
    assert hits == [], f"clean copy must flag no banned terms; got {hits!r}"


def test_exposed_banned_terms_cover_the_agreed_list() -> None:
    """The exposed ``BANNED_TERMS`` must be a **superset** of the agreed core list this
    repo's tests expect — so the shared checker (used by both the pytest guard and the UI
    scan) catches every PRD AC-X3 term and can't silently drop one. Compared
    case-insensitively because the checker is case-insensitive."""
    from pinewood_derby.present import BANNED_TERMS

    shipped = {t.lower() for t in BANNED_TERMS}
    missing = [t for t in EXPECTED_BANNED_TERMS if t.lower() not in shipped]
    assert not missing, (
        f"the shared BANNED_TERMS list is missing agreed jargon terms {missing!r} — the "
        "checker that backs both the pytest guard and the UI scan must cover the full "
        "agreed list (PRD AC-X3)"
    )


@pytest.mark.parametrize(
    "term",
    [
        "Joules",
        "Newtons",
        "coefficient",
        "m/s",
        "m/s²",
        "C_d",
        "μ",
        "moment of inertia",
        "normal force",
        "kinetic energy",
        "w_drag",
    ],
)
def test_find_banned_terms_flags_each_agreed_term(term: str) -> None:
    """The exposed checker flags every PRD AC-X3 enumerated term when embedded in copy —
    case-insensitively and as a substring (so 'measured in Joules.' is caught)."""
    from pinewood_derby.present import find_banned_terms

    hits = find_banned_terms(f"This run produced 12 {term} of effort, kids!")
    assert hits, f"find_banned_terms failed to flag jargon term {term!r}"


def test_find_banned_terms_is_case_insensitive() -> None:
    """The checker is case-insensitive: 'JOULES', 'Joules', 'joules' are all flagged —
    so a stray capitalisation can't smuggle jargon past the guard (PRD AC-X3)."""
    from pinewood_derby.present import find_banned_terms

    for variant in ("JOULES of energy", "Joules of energy", "joules of energy"):
        assert find_banned_terms(variant), f"case variant {variant!r} must be flagged"


def test_find_banned_terms_matches_both_mu_and_symbol() -> None:
    """Both the symbol (``μ``) and the spelled-out friction-coefficient forms are caught,
    so jargon can't slip through by switching notation (PRD AC-X3)."""
    from pinewood_derby.present import find_banned_terms

    assert find_banned_terms("the μ of the axle is high")
    assert find_banned_terms("the friction coefficient of the axle is high")


def test_find_banned_terms_is_pure_and_deterministic() -> None:
    """The checker is a pure function: same input ⇒ same output, no side effects — so it is
    safe to share between the pytest guard and the UI scan (TRD §11)."""
    from pinewood_derby.present import find_banned_terms

    text = "measured in Newtons and Joules"
    first = find_banned_terms(text)
    second = find_banned_terms(text)
    assert first == second


# ───────────────────────────────────────────────────────────────────────────── #
# AC-1 — No jargon in ANY emitted string of ANY RaceView across the design matrix
# (headline, why, tips, breakdown labels/keys, outcome) — PRD AC-X3.
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize("design_name", list(_MATRIX.keys()))
def test_no_jargon_in_any_view_string_across_matrix(design_name: str) -> None:
    """For each design in the matrix, scan EVERY string the view emits with the SHARED
    exposed checker and assert it flags nothing. This is the regression guard: any newly
    emitted string carrying a banned term fails here (PRD AC-X3; AC-3 below proves it bites)."""
    from pinewood_derby.present import find_banned_terms

    view = _present(_MATRIX[design_name])
    for text in _iter_view_strings(view):
        hits = find_banned_terms(text)
        assert not hits, (
            f"design {design_name!r} emitted jargon {hits!r} in string {text!r} "
            "— no technical term may reach a kid (PRD AC-X3)"
        )


def test_headline_why_tips_and_breakdown_labels_are_individually_clean() -> None:
    """Belt-and-braces over the matrix: each named field (headline, why, every tip, every
    breakdown bar label) is individually checked so a regression points at the exact field."""
    from pinewood_derby.present import find_banned_terms

    for design_name, car in _MATRIX.items():
        view = _present(car)
        assert not find_banned_terms(view.headline), (
            f"{design_name}: headline leaks jargon: {view.headline!r}"
        )
        assert not find_banned_terms(view.why), (
            f"{design_name}: why leaks jargon: {view.why!r}"
        )
        for tip in view.tips:
            assert not find_banned_terms(tip), f"{design_name}: tip leaks jargon: {tip!r}"
        for bar in view.breakdown:
            assert not find_banned_terms(bar.label), (
                f"{design_name}: breakdown label leaks jargon: {bar.label!r}"
            )


def test_to_json_payload_is_jargon_free_across_matrix() -> None:
    """The JSON payload the bridge actually ships to the UI (the strings the kid really
    sees) is jargon-free for every design — the scan follows the data the UI renders, not
    just the dataclass (PRD AC-X3; TRD §5 the bridge ships to_json)."""
    from pinewood_derby.present import find_banned_terms, present, to_json

    for design_name, car in _MATRIX.items():
        payload = to_json(present(_simulate(car), car))
        for text in _iter_view_strings(payload):
            assert not find_banned_terms(text), (
                f"{design_name}: to_json payload leaks jargon in {text!r}"
            )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-3 — The guard FAILS if any newly emitted string introduces a banned term. Proven by
# feeding the scan a synthetic RaceView whose fields carry jargon: the scan must catch it
# (a guard that can't fail is worthless).
# ───────────────────────────────────────────────────────────────────────────── #
def test_scan_catches_jargon_injected_into_a_view_field() -> None:
    """If a developer ships a new emitted string containing jargon, the shared scan must
    flag it. Build a real view, replace a string field with jargon-laced copy, and assert
    the scan over the view's strings now finds a banned term (PRD AC-X3 regression bite)."""
    from pinewood_derby.present import find_banned_terms

    view = _present(_MATRIX["finished_legal_baseline"])
    # Simulate a regression: a new headline that leaked the energy unit.
    jargoned = dataclasses.replace(
        view, headline="Your car kept 12 Joules of kinetic energy at the line!"
    )
    flagged = [t for t in _iter_view_strings(jargoned) if find_banned_terms(t)]
    assert flagged, (
        "the scan must FAIL when an emitted string introduces a banned term — a guard that "
        "can't catch injected jargon is worthless (PRD AC-X3; AC-3)"
    )


def test_scan_catches_jargon_injected_into_a_breakdown_label() -> None:
    """Jargon hidden in a *nested* breakdown bar label (not just a top-level field) is also
    caught — the scan recurses into every string the view-model carries (PRD AC-X3)."""
    from pinewood_derby.present import LossBar, find_banned_terms

    view = _present(_MATRIX["finished_legal_baseline"])
    assert view.breakdown, "baseline finisher must have a breakdown to mutate"
    bad_bar = dataclasses.replace(view.breakdown[0], label="Drag coefficient C_d losses")
    mutated = dataclasses.replace(view, breakdown=(bad_bar, *view.breakdown[1:]))
    assert isinstance(view.breakdown[0], LossBar)
    flagged = [t for t in _iter_view_strings(mutated) if find_banned_terms(t)]
    assert flagged, "jargon in a nested breakdown label must be caught by the scan (PRD AC-X3)"


def test_guard_uses_the_shared_list_so_extending_it_tightens_the_guard() -> None:
    """The guard and the UI scan share ONE list: a term present in ``BANNED_TERMS`` is, by
    construction, flagged by ``find_banned_terms`` — so adding a term to the shared list
    immediately tightens BOTH consumers (TRD §11 'shared by test_present.py and a UI text
    scan'). Asserted for every shipped term."""
    from pinewood_derby.present import BANNED_TERMS, find_banned_terms

    for term in BANNED_TERMS:
        assert find_banned_terms(f"prefix {term} suffix"), (
            f"a term in the shared BANNED_TERMS ({term!r}) must be flagged by the shared "
            "find_banned_terms — otherwise the list and the checker have drifted apart"
        )


# ───────────────────────────────────────────────────────────────────────────── #
# Determinism (gate) — the emitted copy (and therefore the scan result) is a stable
# function of the seeded design, so the guard never flakes.
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize("design_name", list(_MATRIX.keys()))
def test_emitted_strings_are_deterministic(design_name: str) -> None:
    """Re-presenting a design yields identical strings across runs, so the jargon scan is
    deterministic (gate: no clock/network/unseeded RNG)."""
    car = _MATRIX[design_name]
    s1 = _iter_view_strings(_present(car))
    s2 = _iter_view_strings(_present(car))
    assert s1 == s2
