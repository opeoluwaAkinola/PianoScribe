"""Rhythm quantisation for readable sheet music.

A live performance never lands exactly on a grid, so naive rounding to 16th
notes produces split chords, needless ties and fragments. This module turns one
hand's notes into clean notation events:

1. **Ghost notes** (very quiet *and* very short) are dropped from the score.
2. **Chord clustering** – notes struck within a few tens of milliseconds
   (rolled or slightly uneven chords) become one chord before quantising.
3. **Grace notes** – a very short note that slides into the next chord
   (a typical gospel/blues crush) is written as a grace note, not a 16th.
4. **Adaptive grid per beat** – each beat picks the simplest subdivision that
   fits its onsets (quarter, 8ths, 16ths or triplets). 16ths and triplets are
   only made cheap when the whole performance shows them, so loose timing in a
   straight piece doesn't turn into stray triplets.
5. **Clean durations** – notes are held until the next onset unless there is a
   clear gap; rests shorter than half a beat are absorbed and rests start on
   the grid.

Positions are in beats from the start of bar 1 (see BeatGrid) and are returned
as exact Fractions so triplets stay exact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

# Extra "cost" of choosing a finer / rarer grid (in beats of timing error).
# Finer grids get cheaper only when the performance shows evidence of them
# (see ``grid_costs``), so loose timing isn't mistaken for 16ths or triplets.
COLLISION_COST = 0.06  # merging two distinct onsets into one slot
EVIDENCE_RATIO = 1.6  # peak density vs. background needed to call a grid "present"


def _density(offsets: list[float], targets: list[float], tol: float) -> float:
    if not offsets:
        return 0.0
    hits = sum(1 for o in offsets if min(abs(o - t) for t in targets) <= tol)
    return hits / (len(offsets) * len(targets) * 2 * tol)


def rhythm_evidence(offsets: list[float]) -> dict[str, float]:
    """How strongly 16ths and triplets stand out from timing noise.

    ``offsets`` are onset positions within their beat (0..1). Densities at the
    16th / triplet positions are compared with the density at the in-between
    positions (1/8, 3/8, …), which only timing noise should populate.
    """
    background = _density(offsets, [0.125, 0.375, 0.625, 0.875], 0.03) or 1e-6
    return {
        "sixteenth": _density(offsets, [0.25, 0.75], 0.04) / background,
        "triplet": _density(offsets, [1 / 3, 2 / 3], 0.04) / background,
    }


def grid_costs(offsets: list[float], compound: bool) -> dict[int, float]:
    ev = rhythm_evidence(offsets)
    has_16 = ev["sixteenth"] >= EVIDENCE_RATIO
    has_trip = ev["triplet"] >= EVIDENCE_RATIO and ev["triplet"] >= ev["sixteenth"]
    if compound:
        # beat = dotted quarter: 3 = 8ths, 6 = 16ths, 2 = duplets
        return {1: 0.0, 3: 0.012, 6: 0.03 if has_16 else 0.07, 2: 0.10}
    return {1: 0.0, 2: 0.012, 4: 0.03 if has_16 else 0.07, 3: 0.035 if has_trip else 0.10}


@dataclass
class TimedNote:
    pitch: int
    velocity: int
    start: float  # seconds
    end: float  # seconds
    start_beat: float
    end_beat: float


@dataclass
class Event:
    onset: Fraction  # beats from the start of bar 1
    duration: Fraction  # beats
    pitches: list[int]
    graces: list[int] = field(default_factory=list)


@dataclass
class QuantizeOptions:
    compound: bool = False
    fixed_grid: int | None = None  # force one subdivision per beat
    costs: dict[int, float] | None = None  # adaptive grid costs (from grid_costs())
    ghost_velocity: int = 22
    ghost_max_sec: float = 0.08
    grace_max_sec: float = 0.11
    min_rest: Fraction = Fraction(1, 2)  # shorter gaps are absorbed into the note

    def resolved_costs(self) -> dict[int, float]:
        if self.fixed_grid:
            return {self.fixed_grid: 0.0}
        if self.costs:
            return self.costs
        return grid_costs([], self.compound)


@dataclass
class _Cluster:
    notes: list[TimedNote]
    onset_beat: float
    onset_sec: float
    graces: list[int] = field(default_factory=list)
    pos: Fraction | None = None

    @property
    def end_beat(self) -> float:
        return max(n.end_beat for n in self.notes)

    @property
    def pitches(self) -> list[int]:
        return sorted({n.pitch for n in self.notes})

    @property
    def duration_sec(self) -> float:
        return max(n.end for n in self.notes) - self.onset_sec


def _round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def _cluster(notes: list[TimedNote]) -> list[_Cluster]:
    clusters: list[_Cluster] = []
    current: list[TimedNote] = []
    for n in sorted(notes, key=lambda n: (n.start, n.pitch)):
        if current:
            first = current[0]
            d_sec = n.start - first.start
            d_beat = n.start_beat - first.start_beat
            if d_sec <= 0.045 or (d_beat <= 0.1 and d_sec <= 0.09):
                current.append(n)
                continue
            clusters.append(_make_cluster(current))
        current = [n]
    if current:
        clusters.append(_make_cluster(current))
    return clusters


def _make_cluster(notes: list[TimedNote]) -> _Cluster:
    starts = sorted(n.start_beat for n in notes)
    secs = sorted(n.start for n in notes)
    mid = len(starts) // 2
    return _Cluster(list(notes), starts[mid], secs[mid])


def _extract_graces(clusters: list[_Cluster], opts: QuantizeOptions) -> list[_Cluster]:
    out: list[_Cluster] = []
    i = 0
    while i < len(clusters):
        c = clusters[i]
        nxt = clusters[i + 1] if i + 1 < len(clusters) else None
        if (
            nxt is not None
            and len(c.notes) == 1
            and c.duration_sec < opts.grace_max_sec
            and nxt.onset_sec - c.onset_sec <= 0.14
            and nxt.onset_beat - c.onset_beat < 0.3
            and c.notes[0].pitch not in nxt.pitches
            and min(abs(c.notes[0].pitch - p) for p in nxt.pitches) <= 3
        ):
            nxt.graces = c.graces + [c.notes[0].pitch] + nxt.graces
            i += 1
            continue
        out.append(c)
        i += 1
    return out


def _choose_grid(offsets: list[float], costs: dict[int, float]) -> int:
    best_g, best_cost = next(iter(costs)), math.inf
    for g, penalty in costs.items():
        slots = [_round_half_up(o * g) for o in offsets]
        err = sum(abs(o - s / g) for o, s in zip(offsets, slots, strict=True)) / len(offsets)
        collisions = len(slots) - len(set(slots))
        cost = err + penalty + COLLISION_COST * collisions
        if cost < best_cost - 1e-9:
            best_g, best_cost = g, cost
    return best_g


def _snap(value: float, grid: int) -> Fraction:
    return Fraction(_round_half_up(value * grid), grid)


def quantize_hand(notes: list[TimedNote], opts: QuantizeOptions | None = None) -> list[Event]:
    opts = opts or QuantizeOptions()
    notes = [n for n in notes if not (n.velocity < opts.ghost_velocity and n.end - n.start < opts.ghost_max_sec)]
    if not notes:
        return []

    clusters = _extract_graces(_cluster(notes), opts)

    # Assign each cluster to a beat (onsets a little early belong to the next beat).
    by_beat: dict[int, list[_Cluster]] = {}
    for c in clusters:
        by_beat.setdefault(math.floor(c.onset_beat + 0.12), []).append(c)

    costs = opts.resolved_costs()
    beat_grid: dict[int, int] = {}
    for k, group in by_beat.items():
        g = _choose_grid([c.onset_beat - k for c in group], costs)
        beat_grid[k] = g
        for c in group:
            c.pos = max(Fraction(0), k + _snap(c.onset_beat - k, g))

    # Merge clusters that landed on the same position into one chord.
    merged: list[_Cluster] = []
    for c in sorted(clusters, key=lambda c: (c.pos, c.onset_beat)):
        if merged and merged[-1].pos == c.pos:
            merged[-1].notes.extend(c.notes)
            merged[-1].graces.extend(c.graces)
        else:
            merged.append(c)

    def grid_at(beat_pos: float) -> int:
        return beat_grid.get(math.floor(beat_pos + 0.12), 1 if opts.fixed_grid is None else opts.fixed_grid)

    events: list[Event] = []
    for i, c in enumerate(merged):
        q = c.pos
        assert q is not None
        unit = Fraction(1, grid_at(float(q)))
        if i + 1 < len(merged):
            nq = merged[i + 1].pos
        else:
            nq = q + max(Fraction(1), _snap(c.end_beat - float(q), 2))
        span = nq - q
        held = c.end_beat - float(q)
        if held >= 0.6 * float(span) or float(span) - held < float(opts.min_rest):
            dur = span
        else:
            g_end = beat_grid.get(math.floor(c.end_beat + 0.12), 2)
            end_q = min(nq, max(q + unit, math.floor(c.end_beat) + _snap(c.end_beat - math.floor(c.end_beat), g_end)))
            dur = span if nq - end_q < opts.min_rest else end_q - q
        dur = min(max(dur, unit), span) if span > 0 else unit
        events.append(Event(q, dur, c.pitches, list(dict.fromkeys(c.graces))))
    return events
