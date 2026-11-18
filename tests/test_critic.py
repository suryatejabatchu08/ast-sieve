from types import SimpleNamespace

from ast_sieve import critic
from ast_sieve.engine import collect, scan


class FakeClient:
    def __init__(self, reply: str | Exception):
        self.reply = reply
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.calls = 0

    def _create(self, **kwargs):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        message = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _project(tmp_path):
    code = "def _unused():\n    return 1\n\n\ndef public():\n    return 2\n"
    (tmp_path / "a.py").write_text(code)
    return collect(tmp_path), scan(tmp_path)


def test_critic_drops_findings_it_refutes(tmp_path):
    files, findings = _project(tmp_path)
    client = FakeClient('Sure: {"valid": false, "reason": "framework hook"}')
    kept, dropped = critic.filter_findings(findings, files, client, "m", ambiguous_below=0.6)
    assert [f.message for f in dropped] == [
        "Function 'public' is never reachable from any entrypoint"
    ]
    assert len(kept) == len(findings) - 1
    assert client.calls == 1


def test_critic_keeps_findings_when_the_model_errors_or_rambles(tmp_path):
    files, findings = _project(tmp_path)
    for reply in (RuntimeError("down"), "no json here"):
        kept, dropped = critic.filter_findings(findings, files, FakeClient(reply), "m", 0.6)
        assert dropped == [] and len(kept) == len(findings)


def test_confident_findings_are_not_sent_to_the_model(tmp_path):
    files, findings = _project(tmp_path)
    client = FakeClient('{"valid": false}')
    critic.filter_findings(findings, files, client, "m", ambiguous_below=0.4)
    assert client.calls == 0
