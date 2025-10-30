from config import SlackSettings
from integrations.slack import SlackNotifier


class _DummyResponse:
    def __init__(self, *, ok: bool = True):
        self._ok = ok

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {"ok": self._ok}


def test_notify_webhook_prefixes_albert(monkeypatch):
    calls = {}

    def fake_post(url, json, timeout):
        calls["url"] = url
        calls["json"] = json
        calls["timeout"] = timeout
        return _DummyResponse()

    monkeypatch.setattr("integrations.slack.httpx.post", fake_post)
    notifier = SlackNotifier(
        SlackSettings(webhook_url="https://hooks.slack.test", bot_token=None, target_user=None)
    )

    notifier.notify("Incidència detectada")

    assert calls["url"] == "https://hooks.slack.test"
    assert calls["timeout"] == 10
    payload = calls["json"]["text"]
    assert payload.startswith("<@albert> ")
    assert "Incidència detectada" in payload


def test_notify_api_targets_user(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _DummyResponse()

    monkeypatch.setattr("integrations.slack.httpx.post", fake_post)
    notifier = SlackNotifier(
        SlackSettings(webhook_url=None, bot_token="xoxb-test", target_user="albert")
    )

    notifier.notify("Missatge directe")

    assert captured["url"].endswith("/chat.postMessage")
    assert captured["json"]["channel"] == "@albert"
    assert captured["json"]["text"] == "Missatge directe"
    assert captured["headers"]["Authorization"] == "Bearer xoxb-test"
