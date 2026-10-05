"""Small music-theory toolkit: pitch spelling, keys, chord qualities, numerals."""

from __future__ import annotations

from dataclasses import dataclass, field

SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
# Spelling used when the key has no sharps or flats (C major / A minor).
NEUTRAL_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

MAJOR_TONIC_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
MINOR_TONIC_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]
# Key-signature size (positive = sharps, negative = flats) for each major tonic.
MAJOR_FIFTHS = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: -6, 1: -5, 8: -4, 3: -3, 10: -2, 5: -1}

NAME_TO_PC = {n: i for i, n in enumerate(SHARP_NAMES)} | {n: i for i, n in enumerate(FLAT_NAMES)}
NAME_TO_PC |= {"Cb": 11, "Fb": 4, "E#": 5, "B#": 0}


def pretty(name: str) -> str:
    """Use real music glyphs for display (Bb -> B♭)."""
    if len(name) >= 2 and name[1] in "b#":
        return name[0] + ("♭" if name[1] == "b" else "♯") + name[2:]
    return name


@dataclass(frozen=True)
class KeyInfo:
    tonic_pc: int
    mode: str  # "major" | "minor"

    @property
    def tonic(self) -> str:
        names = MAJOR_TONIC_NAMES if self.mode == "major" else MINOR_TONIC_NAMES
        return names[self.tonic_pc]

    @property
    def fifths(self) -> int:
        rel_major = self.tonic_pc if self.mode == "major" else (self.tonic_pc + 3) % 12
        return MAJOR_FIFTHS[rel_major]

    @property
    def label(self) -> str:
        return f"{pretty(self.tonic)} {self.mode}"

    @property
    def short(self) -> str:
        return self.tonic + ("m" if self.mode == "minor" else "")

    @property
    def music21_name(self) -> str:
        t = self.tonic.replace("b", "-")
        return t if self.mode == "major" else t.lower()

    @property
    def mido_name(self) -> str:
        return self.short

    def spell(self, pc: int) -> str:
        return spell_pc(pc, self.fifths)

    @classmethod
    def parse(cls, text: str) -> KeyInfo:
        """Parse "Ab major", "F# minor", "Ebm", "C"."""
        t = text.strip().replace("♭", "b").replace("♯", "#")
        mode = "major"
        lower = t.lower()
        if lower.endswith(" minor") or lower.endswith(" min"):
            mode, t = "minor", t.rsplit(" ", 1)[0]
        elif lower.endswith(" major") or lower.endswith(" maj"):
            t = t.rsplit(" ", 1)[0]
        elif t.endswith("m") and len(t) > 1:
            mode, t = "minor", t[:-1]
        t = t.strip()
        name = t[0].upper() + t[1:]
        if name not in NAME_TO_PC:
            raise ValueError(f"Unknown key: {text!r}")
        return cls(NAME_TO_PC[name], mode)


def spell_pc(pc: int, fifths: int = 0) -> str:
    pc %= 12
    if fifths < 0:
        return FLAT_NAMES[pc]
    if fifths > 0:
        return SHARP_NAMES[pc]
    return NEUTRAL_NAMES[pc]


def midi_to_name(midi: int, fifths: int = 0) -> str:
    return f"{spell_pc(midi, fifths)}{midi // 12 - 1}"


# --- Chord qualities -----------------------------------------------------------


@dataclass(frozen=True)
class ChordQuality:
    suffix: str
    # interval (semitones above root) -> importance weight
    tones: dict[int, float]
    music21: str
    minor: bool = False
    roman_suffix: str = ""
    nashville_suffix: str = ""
    # Extra cost for choosing this quality (keeps simple triads preferred).
    complexity: float = 0.0
    intervals: frozenset[int] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "intervals", frozenset(self.tones))


R, M3, m3, P5, d5, A5 = 0, 4, 3, 7, 6, 8

CHORD_QUALITIES: list[ChordQuality] = [
    ChordQuality("", {R: 1.0, M3: 1.0, P5: 0.8}, "", roman_suffix="", nashville_suffix=""),
    ChordQuality("m", {R: 1.0, m3: 1.0, P5: 0.8}, "m", True, "", "m"),
    ChordQuality("dim", {R: 1.0, m3: 1.0, d5: 1.0}, "dim", True, "°", "°", 0.03),
    ChordQuality("aug", {R: 1.0, M3: 1.0, A5: 1.0}, "aug", False, "+", "+", 0.05),
    ChordQuality("sus4", {R: 1.0, 5: 1.0, P5: 0.8}, "sus4", False, "sus4", "sus4", 0.02),
    ChordQuality("sus2", {R: 1.0, 2: 1.0, P5: 0.8}, "sus2", False, "sus2", "sus2", 0.03),
    ChordQuality("6", {R: 1.0, M3: 1.0, P5: 0.6, 9: 0.9}, "6", False, "6", "6", 0.03),
    ChordQuality("m6", {R: 1.0, m3: 1.0, P5: 0.6, 9: 0.9}, "m6", True, "6", "m6", 0.04),
    ChordQuality("7", {R: 1.0, M3: 1.0, P5: 0.5, 10: 1.0}, "7", False, "7", "7", 0.01),
    ChordQuality("maj7", {R: 1.0, M3: 1.0, P5: 0.5, 11: 1.0}, "maj7", False, "maj7", "maj7", 0.01),
    ChordQuality("m7", {R: 1.0, m3: 1.0, P5: 0.5, 10: 1.0}, "m7", True, "7", "m7", 0.01),
    ChordQuality("m7b5", {R: 1.0, m3: 1.0, d5: 1.0, 10: 1.0}, "m7b5", True, "ø7", "ø7", 0.02),
    ChordQuality("dim7", {R: 1.0, m3: 1.0, d5: 1.0, 9: 1.0}, "dim7", True, "°7", "°7", 0.03),
    ChordQuality("7sus4", {R: 1.0, 5: 1.0, P5: 0.5, 10: 1.0}, "7sus4", False, "7sus4", "7sus4", 0.03),
    ChordQuality("add9", {R: 1.0, M3: 1.0, P5: 0.6, 2: 0.8}, "add9", False, "add9", "add9", 0.04),
    ChordQuality("9", {R: 1.0, M3: 1.0, P5: 0.3, 10: 1.0, 2: 0.8}, "9", False, "9", "9", 0.04),
    ChordQuality("maj9", {R: 1.0, M3: 1.0, P5: 0.3, 11: 1.0, 2: 0.8}, "M9", False, "maj9", "maj9", 0.04),
    ChordQuality("m9", {R: 1.0, m3: 1.0, P5: 0.3, 10: 1.0, 2: 0.8}, "m9", True, "9", "m9", 0.04),
    ChordQuality("11", {R: 1.0, 5: 0.9, P5: 0.3, 10: 1.0, 2: 0.8}, "11", False, "11", "11", 0.05),
    ChordQuality("m11", {R: 1.0, m3: 1.0, 5: 0.8, P5: 0.3, 10: 1.0, 2: 0.5}, "m11", True, "11", "m11", 0.06),
    ChordQuality("13", {R: 1.0, M3: 1.0, 10: 1.0, 9: 0.9, 2: 0.4}, "13", False, "13", "13", 0.06),
]
QUALITY_BY_SUFFIX = {q.suffix: q for q in CHORD_QUALITIES}

_NUMERALS = ["I", "II", "II", "III", "III", "IV", "IV", "V", "VI", "VI", "VII", "VII"]
_NUMBERS = ["1", "2", "2", "3", "3", "4", "4", "5", "6", "6", "7", "7"]
_FLAT_DEGREES = {1, 3, 8, 10}


def _degree_accidental(semitones: int, quality: ChordQuality) -> tuple[int, str]:
    """Return (index into numeral tables, accidental) relative to the major scale."""
    if semitones in _FLAT_DEGREES:
        return semitones, "♭"
    if semitones == 6:
        # #iv° (gospel/jazz passing chord) vs bV (borrowed major chord)
        if quality.suffix in {"dim", "dim7", "m7b5"}:
            return 5, "♯"
        return 7, "♭"
    return semitones, ""


def roman_numeral(root_pc: int, quality: ChordQuality, key: KeyInfo, bass_pc: int | None = None) -> str:
    semis = (root_pc - key.tonic_pc) % 12
    idx, acc = _degree_accidental(semis, quality)
    numeral = _NUMERALS[idx]
    if quality.minor:
        numeral = numeral.lower()
    out = f"{acc}{numeral}{quality.roman_suffix}"
    if bass_pc is not None and bass_pc != root_pc:
        out += "/" + nashville_degree(bass_pc, key)
    return out


def nashville_degree(pc: int, key: KeyInfo) -> str:
    semis = (pc - key.tonic_pc) % 12
    if semis in _FLAT_DEGREES:
        return "♭" + _NUMBERS[semis]
    if semis == 6:
        return "♯4"
    return _NUMBERS[semis]


def nashville_number(root_pc: int, quality: ChordQuality, key: KeyInfo, bass_pc: int | None = None) -> str:
    semis = (root_pc - key.tonic_pc) % 12
    idx, acc = _degree_accidental(semis, quality)
    out = f"{acc}{_NUMBERS[idx]}{quality.nashville_suffix}"
    if bass_pc is not None and bass_pc != root_pc:
        out += "/" + nashville_degree(bass_pc, key)
    return out


def chord_label(root_pc: int, quality: ChordQuality, fifths: int, bass_pc: int | None = None) -> str:
    out = spell_pc(root_pc, fifths) + quality.suffix
    if bass_pc is not None and bass_pc != root_pc:
        out += "/" + spell_pc(bass_pc, fifths)
    return out


def music21_figure(root_pc: int, quality: ChordQuality, fifths: int, bass_pc: int | None = None) -> str:
    root = spell_pc(root_pc, fifths).replace("b", "-")
    out = root + quality.music21
    if bass_pc is not None and bass_pc != root_pc:
        out += "/" + spell_pc(bass_pc, fifths).replace("b", "-")
    return out
