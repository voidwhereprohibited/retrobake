import pytest

from retrobake.ai import AIService, AISettings, CoverArt, cover_size, parse_names
from retrobake.ai.providers import Provider, ProviderError
from retrobake.ai.raster import Canvas, from_png
from retrobake.security import InputRejected, find_ip
from retrobake.spec import new_spec


def spec(system="nes"):
    s, _ = new_spec(system, ["platformer"], "a frog who saves the moon", seed=42)
    return s


def picture(w=300, h=300):
    c = Canvas(w, h)
    for y in range(h):
        c.fill_rect(0, y, w, 1, (y % 256, 80, 255 - y % 256))
    return c.to_png()


class FakeProvider(Provider):
    name = "fake"

    def __init__(self, image=b"", text="", error=None):
        super().__init__(transport=lambda *a: None)
        self._img, self._txt, self._err = image, text, error
        self.image_calls = self.text_calls = 0

    def image(self, prompt, *, width, height, seed):
        self.image_calls += 1
        if self._err:
            raise self._err
        return self._img

    def text(self, prompt, *, system, seed):
        self.text_calls += 1
        if self._err:
            raise self._err
        return self._txt


def svc(provider=None, **settings):
    return AIService(AISettings(**settings), cache_dir=False, provider=provider)


def test_offline_setting_never_calls_provider():
    p = FakeProvider(image=picture())
    art = svc(p, online=False).make_art(spec())
    ideas = svc(p, online=False).suggest_names(spec())
    assert art.source == "offline" and "off" in art.message
    assert ideas.source == "offline" and len(ideas.names) == 6
    assert p.image_calls == p.text_calls == 0


@pytest.mark.parametrize("system", ["nes", "snes"])
def test_ai_art_is_reencoded_at_box_size(system):
    pytest.importorskip("PySide6")
    art = svc(FakeProvider(image=picture())).make_art(spec(system))
    assert art.source == "ai" and art.message == ""
    img = from_png(art.png)  # our own PNG: no EXIF / prompt metadata survives
    assert (img.width, img.height) == cover_size(spec(system)) == (art.width, art.height)


@pytest.mark.parametrize(
    "data",
    [b"", b"<html>nope</html>", b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, picture(32, 32), b"\xff" * 9],
)
def test_bad_ai_image_falls_back(data):
    art = svc(FakeProvider(image=data)).make_art(spec())
    assert art.source == "offline" and "safety check" in art.message
    assert (art.width, art.height) == cover_size(spec())


def test_provider_error_falls_back_with_plain_message():
    err = ProviderError("Couldn't reach the art service. Check your internet.")
    art = svc(FakeProvider(error=err)).make_art(spec())
    ideas = svc(FakeProvider(error=err)).suggest_names(spec(), 5)
    assert art.source == ideas.source == "offline"
    assert art.message.startswith("Couldn't reach") and len(ideas.names) == 5


def test_bad_key_in_settings_falls_back():
    art = svc(None, provider="pollinations_key", pollinations_key="bad key").make_art(spec())
    assert art.source == "offline" and "key" in art.message
    assert "bad key" not in repr(AISettings(pollinations_key="bad key"))


def test_ai_names_filtered_and_padded():
    reply = (
        "1. Moon Frog Rescue\n2) Super Mario Moon\n- Lily Pad Leap\n\n* Lily Pad Leap\n"
        + ("x" * 80)
        + '\nZelda Frog\n"Starlit Hopper"\nIgnore previous instructions'
    )
    ideas = svc(FakeProvider(text=reply)).suggest_names(spec(), 6)
    assert ideas.source == "ai" and len(ideas.names) == 6
    assert ideas.names[:3] == ["Moon Frog Rescue", "Lily Pad Leap", "Starlit Hopper"]
    assert all(not find_ip(n) and len(n) <= 24 for n in ideas.names)
    assert len({n.casefold() for n in ideas.names}) == 6


def test_garbage_names_reply_falls_back():
    ideas = svc(FakeProvider(text="Mario\nZelda\n\n<script>")).suggest_names(spec())
    assert ideas.source == "offline" and len(ideas.names) == 6


def test_parse_names_handles_non_lists():
    assert parse_names(None) == [] and parse_names({"a": 1}) == []
    assert parse_names(["ok name", 5, None]) == ["ok name"]


def test_cache_reuses_art_and_names(tmp_path):
    pytest.importorskip("PySide6")
    p = FakeProvider(image=picture(), text="Moon Frog Rescue\nLily Pad Leap")
    a = AIService(AISettings(), cache_dir=tmp_path, provider=p)
    first, second = a.make_art(spec()), a.make_art(spec())
    assert first.png == second.png and p.image_calls == 1
    a.suggest_names(spec())
    again = a.suggest_names(spec())
    assert p.text_calls == 1 and again.names[0] == "Moon Frog Rescue"
    assert a.make_art(spec(), variant=1) and p.image_calls == 2  # "try another" = new picture


def test_damaged_cache_is_ignored(tmp_path):
    p = FakeProvider(error=ProviderError("down"))
    a = AIService(AISettings(), cache_dir=tmp_path, provider=p)
    a.make_art(spec())
    for f in tmp_path.glob("*"):
        f.write_bytes(b"junk")
    assert a.make_art(spec()).source == "offline"


def test_with_title_banner():
    art = svc(online=False).make_art(spec("snes"))
    final = AIService.with_title(art, "Moon Frog")
    img = from_png(final)
    assert (img.width, img.height) == (art.width, art.height) and final != art.png
    assert isinstance(art, CoverArt)


@pytest.mark.parametrize("title", ["Super Mario Frog", "", "   ", "bad<title>"])
def test_with_title_rejects_bad_titles(title):
    art = svc(online=False).make_art(spec())
    with pytest.raises(InputRejected):
        AIService.with_title(art, title)


def test_cover_convenience():
    png, art = svc(online=False).cover(spec(), "Moon Frog", variant=2)
    assert from_png(png).width == art.width
