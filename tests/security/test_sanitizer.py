import pytest

from retrobake.security import (
    InputRejected,
    SandboxError,
    clean_choice,
    clean_text,
    safe_filename,
    safe_join,
    sanitize,
)


def test_strips_controls_bidi_and_zero_width():
    raw = "Hero\x00\x07 \u202egnirts\u202c\u200b jumps\ufeff"
    assert clean_text(raw, max_len=100) == "Hero gnirts jumps"


def test_nfkc_and_whitespace():
    assert clean_text("\uff28\uff49   there\t\n\nfriend", max_len=50) == "Hi there friend"
    assert clean_text("a\n\n\n\nb", max_len=50, multiline=True) == "a\n\nb"


def test_zalgo_marks_capped():
    out = clean_text("a" + "\u0301" * 30, max_len=50)
    assert len(out) <= 3


def test_length_cap():
    assert len(clean_text("x" * 10_000, max_len=24)) == 24


def test_title_rules():
    assert sanitize("title", "  Caf\u00e9  Quest!  ") == "Cafe Quest!"
    assert sanitize("title", "Sky\u2019s Edge") == "Sky's Edge"
    for bad in ["<script>", "", "   ", "$(rm -rf ~)"]:
        with pytest.raises(InputRejected):
            sanitize("title", bad)


def test_description_keeps_unicode_text():
    assert sanitize("description", "Une \u00e9p\u00e9e magique") == "Une \u00e9p\u00e9e magique"


def test_unknown_field():
    with pytest.raises(KeyError):
        sanitize("nope", "x")


def test_choice():
    assert clean_choice("nes", {"nes", "snes"}) == "nes"
    with pytest.raises(InputRejected):
        clean_choice("n64", {"nes", "snes"})


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("My Cool Game", "My_Cool_Game.nes"),
        ("../../etc/passwd", "etcpasswd.nes"),
        ("CON", "my-game.nes"),
        ("com1", "my-game.nes"),
        ("...", "my-game.nes"),
        ("C:\\Windows\\evil", "CWindowsevil.nes"),
    ],
)
def test_safe_filename(name, expected):
    assert safe_filename(name, "nes") == expected


def test_safe_join(tmp_path):
    assert safe_join(tmp_path, "a", "b.txt") == (tmp_path / "a" / "b.txt").resolve()
    for bad in (("..", "x"), ("/etc/passwd",), ("a", "../../x")):
        with pytest.raises(SandboxError):
            safe_join(tmp_path, *bad)


@pytest.mark.parametrize(
    "bad", ["a\x00b", "a\ud800b", "\\\\srv\\share", "//srv/share", "C:\\x", "C:x", "x" * 2000]
)
def test_safe_join_rejects_bad_parts_cleanly(tmp_path, bad):
    with pytest.raises(SandboxError):
        safe_join(tmp_path, bad)


def test_clean_text_is_idempotent_with_stacked_marks():
    once = sanitize("description", "Mar1o\u0301\u0301\u0301x")
    assert sanitize("description", once) == once
