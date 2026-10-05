import pytest

from app.analysis.theory import QUALITY_BY_SUFFIX, KeyInfo, chord_label, nashville_number, roman_numeral


@pytest.mark.parametrize(
    ("text", "tonic", "mode", "fifths"),
    [
        ("Ab major", 8, "major", -4),
        ("F# minor", 6, "minor", 3),
        ("Ebm", 3, "minor", -6),
        ("C", 0, "major", 0),
        ("B♭ major", 10, "major", -2),
        ("Gb", 6, "major", -6),
    ],
)
def test_key_parse(text, tonic, mode, fifths):
    k = KeyInfo.parse(text)
    assert (k.tonic_pc, k.mode, k.fifths) == (tonic, mode, fifths)


def test_spelling_follows_key():
    ab = KeyInfo(8, "major")
    assert ab.spell(1) == "Db" and ab.spell(10) == "Bb"
    e = KeyInfo(4, "major")
    assert e.spell(1) == "C#" and e.spell(6) == "F#"


def test_gospel_numerals():
    key = KeyInfo(8, "major")  # A♭
    q = QUALITY_BY_SUFFIX
    assert roman_numeral(10, q["m7"], key) == "ii7"
    assert roman_numeral(3, q["13"], key) == "V13"
    assert roman_numeral(8, q["maj9"], key) == "Imaj9"
    assert roman_numeral(2, q["dim7"], key) == "♯iv°7"
    assert nashville_number(5, q["m9"], key) == "6m9"
    assert nashville_number(8, q[""], key, bass_pc=0) == "1/3"
    assert chord_label(8, q["maj7"], key.fifths, bass_pc=0) == "Abmaj7/C"
