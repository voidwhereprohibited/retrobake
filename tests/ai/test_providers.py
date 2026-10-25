import base64
import json
import urllib.parse

import pytest

from retrobake.ai import providers as pv
from retrobake.ai.providers import (
    Cloudflare,
    HttpResponse,
    PollinationsFree,
    PollinationsKey,
    ProviderError,
    check_url,
)


class FakeNet:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout, max_bytes):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        return self.responses.pop(0)


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def sleep(self, s):
        self.slept.append(s)
        self.now += s

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def _reset_throttle():
    pv._FREE_STATE["next"] = 0.0
    yield
    pv._FREE_STATE["next"] = 0.0


def query(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


def test_free_image_url_and_required_params():
    net, clk = FakeNet(HttpResponse(200, b"img")), Clock()
    p = PollinationsFree(net, sleep=clk.sleep, clock=clk)
    assert p.image("a b/c?d", width=512, height=704, seed=7) == b"img"
    url = net.calls[0]["url"]
    parts = urllib.parse.urlsplit(url)
    assert parts.hostname == "image.pollinations.ai"
    assert parts.path == "/prompt/a%20b%2Fc%3Fd"  # user text can't add path or query parts
    q = query(url)
    assert q["safe"] == "true" and q["private"] == "true" and q["enhance"] == "false"
    assert (q["width"], q["height"], q["seed"], q["nologo"]) == ("512", "704", "7", "true")
    assert net.calls[0]["headers"]["User-Agent"].startswith("RetroBake/")


def test_free_text_url():
    net, clk = FakeNet(HttpResponse(200, b"Star Ranger\nMoon Dash")), Clock()
    out = PollinationsFree(net, sleep=clk.sleep, clock=clk).text("p", system="sys", seed=3)
    assert out.splitlines() == ["Star Ranger", "Moon Dash"]
    url = net.calls[0]["url"]
    assert urllib.parse.urlsplit(url).hostname == "text.pollinations.ai"
    assert query(url)["system"] == "sys" and query(url)["safe"] == "true"


def test_free_tier_throttles_between_requests():
    net, clk = FakeNet(HttpResponse(200, b"a"), HttpResponse(200, b"b")), Clock()
    p = PollinationsFree(net, sleep=clk.sleep, clock=clk)
    p.text("x", system="s", seed=1)
    p.text("y", system="s", seed=1)
    assert clk.slept == [pytest.approx(pv.FREE_TIER_INTERVAL)]


def test_retry_once_on_429_then_give_up():
    net, clk = (
        FakeNet(
            HttpResponse(429, b"", {"retry-after": "5"}),
            HttpResponse(429, b"", {}),
        ),
        Clock(),
    )
    p = PollinationsKey("sk_testkey123", net, sleep=clk.sleep, clock=clk)
    with pytest.raises(ProviderError) as err:
        p.image("x", width=64, height=64, seed=1)
    assert err.value.status == 429 and len(net.calls) == 2 and 5.0 in clk.slept
    assert "sk_testkey123" not in err.value.message


def test_long_retry_after_is_not_waited_for():
    net, clk = FakeNet(HttpResponse(503, b"", {"retry-after": "3600"})), Clock()
    with pytest.raises(ProviderError):
        PollinationsKey("sk_testkey123", net, sleep=clk.sleep, clock=clk).text(
            "x", system="s", seed=1
        )
    assert clk.slept == [] and len(net.calls) == 1


def test_oversize_body_rejected():
    big = b"x" * (pv.MAX_TEXT_BYTES + 1)
    net, clk = FakeNet(HttpResponse(200, big)), Clock()
    with pytest.raises(ProviderError):
        PollinationsKey("sk_testkey123", net, sleep=clk.sleep, clock=clk).text(
            "x", system="s", seed=1
        )


def test_key_provider_uses_bearer_and_strict_safe():
    net = FakeNet(HttpResponse(200, b"img"))
    PollinationsKey("sk_abcDEF_123", net).image("x", width=64, height=64, seed=1)
    call = net.calls[0]
    assert call["headers"]["Authorization"] == "Bearer sk_abcDEF_123"
    assert urllib.parse.urlsplit(call["url"]).hostname == "gen.pollinations.ai"
    assert query(call["url"])["safe"] == pv.GEN_SAFE
    assert "sk_abcDEF_123" not in call["url"]  # key never goes in the URL


@pytest.mark.parametrize("bad", ["", "short", "sk_has space", "sk_new\nline", "x" * 300])
def test_bad_keys_rejected(bad):
    with pytest.raises(ProviderError):
        PollinationsKey(bad)


def test_cloudflare_image_and_text():
    img = b"\x89PNG fake"
    net = FakeNet(
        HttpResponse(
            200, json.dumps({"result": {"image": base64.b64encode(img).decode()}}).encode()
        ),
        HttpResponse(200, json.dumps({"result": {"response": "Nova Run"}}).encode()),
    )
    cf = Cloudflare("0" * 32, "cf_token_123456", net)
    assert cf.image("x", width=64, height=64, seed=1) == img
    assert cf.text("x", system="s", seed=1) == "Nova Run"
    first = net.calls[0]
    assert (
        first["method"] == "POST" and "/ai/run/@cf/black-forest-labs/flux-1-schnell" in first["url"]
    )
    assert json.loads(first["body"])["prompt"] == "x"


@pytest.mark.parametrize("payload", [b"not json", b"[]", b'{"result": {"image": "!!!"}}', b"{}"])
def test_cloudflare_bad_payloads(payload):
    cf = Cloudflare("a" * 32, "cf_token_123456", FakeNet(HttpResponse(200, payload)))
    with pytest.raises(ProviderError):
        cf.image("x", width=64, height=64, seed=1)


@pytest.mark.parametrize("acct", ["", "../../evil", "A" * 32, "a" * 31])
def test_cloudflare_bad_account(acct):
    with pytest.raises(ProviderError):
        Cloudflare(acct, "cf_token_123456")


@pytest.mark.parametrize(
    "url",
    [
        "http://image.pollinations.ai/x",
        "https://evil.example.com/x",
        "https://image.pollinations.ai.evil.com/x",
        "https://user@image.pollinations.ai/x",
        "file:///etc/passwd",
    ],
)
def test_url_allowlist(url):
    with pytest.raises(ProviderError):
        check_url(url)
