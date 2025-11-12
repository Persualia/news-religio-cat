from integrations.slack import SlackNotifier
from config import SlackSettings
from types import SimpleNamespace


class _DummyResponse:
    def __init__(self, *, ok: bool = True):
        self._ok = ok

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {"ok": self._ok}


def test_notify_webhook_defaults_to_public_channel(monkeypatch):
    calls = {}

    def fake_post(url, json, timeout):
        calls["url"] = url
        calls["json"] = json
        calls["timeout"] = timeout
        return _DummyResponse()

    monkeypatch.setattr("integrations.slack.httpx.post", fake_post)
    dummy_settings = SimpleNamespace(
        slack=SlackSettings(webhook_url="https://hooks.slack.test", bot_token=None)
    )
    monkeypatch.setattr("integrations.slack.get_settings", lambda: dummy_settings)
    notifier = SlackNotifier()

    notifier.notify("Incidència detectada")

    assert calls["url"] == "https://hooks.slack.test"
    assert calls["timeout"] == 10
    assert calls["json"]["text"] == "Incidència detectada"
    assert calls["json"]["channel"] == "#catalunya-religio"


def test_notify_api_targets_channel(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _DummyResponse()

    monkeypatch.setattr("integrations.slack.httpx.post", fake_post)
    dummy_settings = SimpleNamespace(slack=SlackSettings(webhook_url=None, bot_token="xoxb-test"))
    monkeypatch.setattr("integrations.slack.get_settings", lambda: dummy_settings)
    notifier = SlackNotifier()

    notifier.notify("Missatge directe")

    assert captured["url"].endswith("/chat.postMessage")
    assert captured["json"]["channel"] == "#catalunya-religio"
    assert captured["json"]["text"] == "Missatge directe"
    assert captured["headers"]["Authorization"] == "Bearer xoxb-test"


def test_notify_blocks_via_api(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _DummyResponse()

    monkeypatch.setattr("integrations.slack.httpx.post", fake_post)
    dummy_settings = SimpleNamespace(slack=SlackSettings(webhook_url=None, bot_token="xoxb-test"))
    monkeypatch.setattr("integrations.slack.get_settings", lambda: dummy_settings)
    notifier = SlackNotifier()

    blocks = [{"type": "section", "text": {"type": "plain_text", "text": "Hola"}}]
    notifier.notify_blocks(blocks=blocks, text="Resum")

    assert captured["json"]["channel"] == "#catalunya-religio"
    assert captured["json"]["blocks"] == blocks
    assert captured["json"]["text"] == "Resum"


def test_notify_blocks_via_webhook(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _DummyResponse()

    monkeypatch.setattr("integrations.slack.httpx.post", fake_post)
    dummy_settings = SimpleNamespace(
        slack=SlackSettings(webhook_url="https://hooks.slack.test", bot_token=None)
    )
    monkeypatch.setattr("integrations.slack.get_settings", lambda: dummy_settings)
    notifier = SlackNotifier()

    blocks = [{"type": "section", "text": {"type": "plain_text", "text": "Hola"}}]
    notifier.notify_blocks(blocks=blocks, text="Resum")

    assert captured["url"] == "https://hooks.slack.test"
    assert captured["json"]["blocks"] == blocks
    assert captured["json"]["text"] == "Resum"
    assert captured["json"]["channel"] == "#catalunya-religio"


def test_notify_webhook_channel_override_for_text(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _DummyResponse()

    monkeypatch.setattr("integrations.slack.httpx.post", fake_post)
    dummy_settings = SimpleNamespace(
        slack=SlackSettings(webhook_url="https://hooks.slack.test", bot_token=None)
    )
    monkeypatch.setattr("integrations.slack.get_settings", lambda: dummy_settings)
    notifier = SlackNotifier()

    notifier.notify("Incidència detectada")

    assert captured["json"]["channel"] == "#catalunya-religio"
