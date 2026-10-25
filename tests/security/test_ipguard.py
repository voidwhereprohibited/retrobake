import pytest

from retrobake.security import InputRejected, check_title, find_ip, scrub_ip


@pytest.mark.parametrize(
    "text",
    [
        "like Super Mario meets Zelda",
        "a game like M a r i o",
        "Mar1o style jumping",
        "catch them like Pok\u00e9mon",
        "\u0405\u043enic the hedgehog speed",  # Cyrillic look-alikes
        "Nintendo64 vibes",
        "SuperMario",
        "MEGA-MAN boss rush",
        "\uff2d\uff41\uff52\uff49\uff4f",  # fullwidth
    ],
)
def test_finds_franchise_names(text):
    assert find_ip(text)


@pytest.mark.parametrize(
    "text",
    [
        "a toad jumps over peach trees",
        "a metroidvania with a cute hero",
        "the marionette castle",
        "a sonic boom shakes the sky",
        "a brave knight explores dungeons",
    ],
)
def test_everyday_words_pass(text):
    assert find_ip(text) == []


def test_ambiguous_words_caught_with_franchise_context():
    hits = find_ip("Mario and Toad save Peach")
    assert {"mario", "toad", "peach"} <= set(hits)


def test_scrub_replaces_names():
    clean, hits = scrub_ip("Zelda meets Mario in space")
    assert "zelda" in hits and "mario" in hits
    assert "zelda" not in clean.lower() and "mario" not in clean.lower()
    assert "space" in clean


def test_titles():
    assert check_title("Sky Knight") == "Sky Knight"
    for bad in ("Super Mari0 World", "Toad Quest", "Zelda II", "Pokemons"):
        with pytest.raises(InputRejected):
            check_title(bad)
