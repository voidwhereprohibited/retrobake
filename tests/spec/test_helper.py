import pytest

from retrobake.spec import analyze, new_spec, questions_for, validate
from retrobake.spec import helper as h

SAMPLES = [
    "A brave knight jumps through a haunted castle full of skeletons",
    "fly a spaceship and blast aliens in deep space",
    "a cozy fox explores frozen caves to find a relic",
    "no shooting! push blocks and flip switches to solve each room",
    "race karts around a desert track",
    "",
    "ninja punches thugs on the city streets",
]


def test_lexicons_and_templates_are_complete():
    lex = h.lexicon()
    assert len(lex["templates"]) == 12
    assert set(lex["compat"]) == set(lex["setting"]) == set(lex["title_words"])
    for theme, c in lex["compat"].items():
        assert set(c["hero"]) <= set(lex["hero"]), theme
        assert set(c["enemy"]) <= set(lex["enemy"]), theme


def test_tokens_stem_join_and_negate():
    assert h.tokens("Jumping foxes") == ["jump", "jump_fox", "fox"]
    assert "top_down" in h.tokens("a top down game")
    assert "shoot" not in h.tokens("no shooting please")


@pytest.mark.parametrize(
    ("text", "template"),
    [
        ("jump across platforms", "action_platformer"),
        ("solve puzzles by pushing blocks", "puzzle_platformer"),
        ("pilot a ship and fly through space", "shmup"),
        ("explore a top down dungeon with a sword", "top_down_adventure"),
        ("a quest with a party, turn based xp", "rpg_lite"),
        ("an rpg", "rpg_lite"),
        ("", "action_platformer"),
        ("purple elephants", "action_platformer"),
    ],
)
def test_templates_pick_exactly_one(text, template):
    assert analyze(text).template == template


def test_ties_go_to_the_earliest_signal_then_list_order():
    assert analyze("race then jump").template == "racing"
    assert analyze("jump then race").template == "action_platformer"


def test_genre_limits_the_templates():
    plan = analyze("fly a ship through space", "platformer")
    assert plan.genre == "platformer"


def test_one_theme_and_consistent_cast():
    plan = analyze("skeletons in space")
    assert plan.theme == "space"
    assert plan.enemies == ["alien"]  # skeletons don't belong in space
    assert analyze("ice ice lava").theme == "snow"
    assert analyze("lava then ice").theme == "volcano"  # tie: first mentioned


@pytest.mark.parametrize("text", SAMPLES)
def test_titles_follow_the_rules(text):
    plan = analyze(text)
    assert h.title_ok(plan.title, plan.theme)
    assert plan.title == analyze(text).title  # deterministic
    assert len(plan.title) <= 20 and plan.title.isascii()


@pytest.mark.parametrize(
    "title",
    ["Ninjabot", "Lava Ice Quest", "Super Glacier", "Glacier Hollow 2", "Glacier: Drift",
     "Glacier Platformer", "GLACIER Drift", "Drift Meets Peak"],
)  # fmt: skip
def test_banned_titles_are_rejected(title):
    assert not h.title_ok(title, "snow")


def test_good_titles_pass():
    assert h.title_ok("Glacier Hollow", "snow")
    assert h.title_ok("The Pale Drift", "snow")


def test_new_spec_uses_the_plan_and_prefills_questions():
    spec, _ = new_spec("nes", "platformer", "a frozen arctic adventure with a fox", seed=1)
    assert validate(spec) == []
    assert spec["world"]["setting"] == "ice"
    assert spec["hero"]["archetype"] == "animal"
    assert spec["style"]["palette_mood"] == "icy"
    assert h.title_ok(spec["title"], "snow")
    defaults = {q["id"]: q["default"] for q in questions_for(spec)}
    assert defaults["setting"] == "ice" and defaults["hero_archetype"] == "animal"


def test_new_spec_keeps_a_typed_title():
    spec, _ = new_spec("nes", "platformer", "a frozen land", "My Own Name", seed=1)
    assert spec["title"] == "My Own Name"


def test_summary_is_short_and_plain():
    text = analyze("a cozy fox explores frozen caves").summary()
    assert "an animal" in text and "top-down adventure" in text
    assert len(text) < 240 and "Working title" in text
