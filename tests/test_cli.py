import builtins

import pytest

from jev import cli
from jev.assistant import Jev
from jev.config import Config
from tests.fakes import FakeClaude


class Capture:
    def __init__(self):
        self.parts = []

    def out(self, text):
        self.parts.append(text + "\n")

    def write(self, text):
        self.parts.append(text)

    @property
    def text(self):
        return "".join(self.parts)


@pytest.fixture
def jev(tmp_path):
    return Jev(FakeClaude(chunks=["안녕", "하세요"]), config=Config(model=None, data_dir=tmp_path))


def test_respond_streams_chunks(jev):
    cap = Capture()
    cli.respond(jev, "안녕", stream=True, debug=False, out=cap.out, write=cap.write)
    assert cap.parts[:3] == ["Jev: ", "안녕", "하세요"]
    assert cap.text == "Jev: 안녕하세요\n"


def test_respond_without_stream(jev):
    cap = Capture()
    cli.respond(jev, "안녕", stream=False, debug=True, out=cap.out, write=cap.write)
    assert "[route] claude" in cap.text
    assert cap.text.endswith("Jev: 응답\n")


def test_respond_streamed_refusal_warns(tmp_path):
    jev = Jev(
        FakeClaude(refused=True, chunks=["부분"]), config=Config(model=None, data_dir=tmp_path)
    )
    cap = Capture()
    cli.respond(jev, "안녕", stream=True, debug=False, out=cap.out, write=cap.write)
    assert "중단" in cap.text


def test_respond_reports_missing_model(tmp_path):
    jev = Jev(config=Config(model=None, data_dir=tmp_path))
    cap = Capture()
    cli.respond(jev, "안녕", stream=True, debug=False, out=cap.out, write=cap.write)
    assert "JEV_MODEL" in cap.text


def test_main_bad_config_exits_2(monkeypatch, capsys):
    monkeypatch.setenv("JEV_MAX_TOKENS", "lots")
    assert cli.main(["--no-memory"]) == 2
    assert "JEV_MAX_TOKENS" in capsys.readouterr().err


def test_main_missing_env_file_exits_2(tmp_path, capsys):
    assert cli.main(["--env-file", str(tmp_path / "none.env")]) == 2
    assert ".env" in capsys.readouterr().err


def test_main_loop_exits_on_eof(monkeypatch, capsys):
    inputs = iter(["", "/help"])

    def fake_input(prompt):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr(builtins, "input", fake_input)
    assert cli.main(["--no-memory"]) == 0
    assert "Jev:" in capsys.readouterr().out
