"""Notification routing tests with fake integrations — no network."""
from app.services.integrations.registry import Integration
from app.services.integrations.registry import TestResult as IntegrationTestResult
from app.services.notifications import Alert, NotificationService


class FakeAlertIntegration(Integration):
    kind, label, category = "fake_alert", "Fake", "alerts"

    def __init__(self, fail: bool = False):
        super().__init__({}, {})
        self.fail = fail
        self.sent: list = []

    async def test(self) -> IntegrationTestResult:
        return IntegrationTestResult(True, "ok")

    async def send(self, payload):
        if self.fail:
            raise RuntimeError("boom")
        self.sent.append(payload)


class NonAlertIntegration(Integration):
    kind, label, category = "obs", "Obs", "observability"

    async def test(self):
        return IntegrationTestResult(True, "ok")


def alert():
    return Alert(severity="critical", kind="killswitch", title="Kill switch", body="global hard")


async def test_delivers_to_alert_integrations():
    svc = NotificationService()
    ok = FakeAlertIntegration()
    svc.set_routes([ok])
    a = await svc.deliver(alert())
    assert a.delivered == {"fake_alert": "ok"}
    assert ok.sent and "Kill switch" in ok.sent[0]["title"]


async def test_channel_failure_is_isolated():
    svc = NotificationService()
    good, bad = FakeAlertIntegration(), FakeAlertIntegration(fail=True)
    good.kind = "good"; bad.kind = "bad"
    svc.set_routes([good, bad])
    a = await svc.deliver(alert())
    assert a.delivered["good"] == "ok"
    assert a.delivered["bad"].startswith("error")
    assert good.sent  # good channel still delivered despite bad one failing


async def test_non_alert_integration_is_not_routed():
    svc = NotificationService()
    svc.set_routes([NonAlertIntegration({}, {})])
    a = await svc.deliver(alert())
    assert a.delivered == {}


def test_feed_and_ack():
    svc = NotificationService()
    a = svc.record(alert())
    assert svc.feed()[0]["title"] == "Kill switch"
    assert svc.acknowledge(a.id) is True
    assert svc.feed()[0]["acknowledged"] is True
    assert svc.acknowledge("missing") is False
