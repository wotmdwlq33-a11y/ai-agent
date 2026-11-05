import builtins

import anthropic
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


class InterruptingClaude(FakeClaude):
    def ask_stream(self, messages, effort, on_text):
        on_text("앞부분")
        raise KeyboardInterrupt


def test_ctrl_c_during_stream_stops_only_this_answer(tmp_path):
    jev = Jev(InterruptingClaude(), config=Config(model=None, data_dir=tmp_path))
    cap = Capture()
    cli.respond(jev, "안녕", stream=True, debug=False, out=cap.out, write=cap.write)
    assert cap.text == "Jev: 앞부분\nJev: (답변을 중단했어요)\n"
    assert jev.history == []


def test_one_shot_message(capsys):
    assert cli.main(["--no-memory", "메모:", "우유", "사기"]) == 0
    out = capsys.readouterr().out
    assert "메모했어요" in out
    assert "안녕하세요" not in out


def test_due_reminders_are_shown_and_removed(tmp_path):
    from datetime import timedelta

    from jev.korean import now
    from jev.skills import reminders

    reminders.add(tmp_path, "물 마시기", now() - timedelta(minutes=1))
    lines = cli._due_reminders(tmp_path)
    assert len(lines) == 1 and "물 마시기" in lines[0]
    assert cli._due_reminders(tmp_path) == []


def test_corrupt_reminders_file_does_not_crash(tmp_path):
    (tmp_path / "reminders.json").write_text("{broken", encoding="utf-8")
    (line,) = cli._due_reminders(tmp_path)
    assert "알림을 확인하지 못했어요" in line


def _api_error(cls, status):
    import httpx2

    request = httpx2.Request("POST", "https://api.example.invalid/v1/messages")
    if cls is anthropic.APIConnectionError:
        return cls(request=request)
    return cls("오류", response=httpx2.Response(status, request=request), body=None)


class RaisingClaude(FakeClaude):
    def __init__(self, error, partial=None):
        super().__init__()
        self.error = error
        self.partial = partial

    def ask_stream(self, messages, effort, on_text):
        if self.partial:
            on_text(self.partial)
        raise self.error


@pytest.mark.parametrize(
    "cls, status, fragment",
    [
        (anthropic.AuthenticationError, 401, "ANTHROPIC_API_KEY"),
        (anthropic.RateLimitError, 429, "잠시 후"),
        (anthropic.InternalServerError, 500, "(500)"),
        (anthropic.APIConnectionError, 0, "네트워크"),
    ],
)
def test_api_errors_are_explained(tmp_path, cls, status, fragment):
    jev = Jev(RaisingClaude(_api_error(cls, status)), config=Config(model=None, data_dir=tmp_path))
    cap = Capture()
    cli.respond(jev, "안녕", stream=True, debug=False, out=cap.out, write=cap.write)
    assert fragment in cap.text
    assert jev.history == []


def test_connection_error_mid_stream_starts_new_line(tmp_path):
    error = _api_error(anthropic.APIConnectionError, 0)
    jev = Jev(RaisingClaude(error, partial="앞부분"), config=Config(model=None, data_dir=tmp_path))
    cap = Capture()
    cli.respond(jev, "안녕", stream=True, debug=False, out=cap.out, write=cap.write)
    assert cap.text.startswith("Jev: 앞부분\nJev: 네트워크")


def test_status_error_mid_stream_starts_new_line(tmp_path):
    error = _api_error(anthropic.InternalServerError, 500)
    jev = Jev(RaisingClaude(error, partial="앞부분"), config=Config(model=None, data_dir=tmp_path))
    cap = Capture()
    cli.respond(jev, "안녕", stream=True, debug=False, out=cap.out, write=cap.write)
    assert cap.text == "Jev: 앞부분\nJev: Claude API 오류가 났어요 (500).\n"


def test_unexpected_errors_are_not_swallowed(tmp_path):
    jev = Jev(RaisingClaude(ZeroDivisionError()), config=Config(model=None, data_dir=tmp_path))
    with pytest.raises(ZeroDivisionError):
        cli.respond(jev, "안녕", stream=True, debug=False, out=print, write=print)


def test_stream_error_event_shows_error_type(tmp_path):
    import httpx2

    request = httpx2.Request("POST", "https://api.example.invalid/v1/messages")
    error = anthropic.APIStatusError(
        "overloaded",
        response=httpx2.Response(200, request=request),
        body={"type": "error", "error": {"type": "overloaded_error", "message": "x"}},
    )
    jev = Jev(RaisingClaude(error), config=Config(model=None, data_dir=tmp_path))
    cap = Capture()
    cli.respond(jev, "안녕", stream=True, debug=False, out=cap.out, write=cap.write)
    assert "overloaded_error" in cap.text
    assert "(200)" not in cap.text


def test_one_shot_exit_codes(capsys):
    assert cli.main(["--no-memory", "여행지", "추천해줘"]) == 2  # JEV_MODEL 없음
    assert cli.main(["--no-memory", ""]) == 2
    assert "비어 있어요" in capsys.readouterr().err


def test_one_shot_runtime_error_exit_code(tmp_path):
    jev = Jev(
        RaisingClaude(_api_error(anthropic.RateLimitError, 429)),
        config=Config(model=None, data_dir=tmp_path),
    )
    code = cli.respond(jev, "안녕", stream=True, debug=False, out=print, write=print)
    assert code == 1


def test_flags_can_be_mixed_with_message(capsys):
    assert cli.main(["메모", "--no-memory", "목록"]) == 0
    assert "메모" in capsys.readouterr().out


def test_reminder_watcher_emits_due_reminders(tmp_path):
    import threading
    from datetime import timedelta

    from jev.korean import now
    from jev.skills import reminders

    reminders.add(tmp_path, "스트레칭", now() - timedelta(seconds=1))
    emitted = []
    watcher = cli.ReminderWatcher(tmp_path, threading.Lock(), emitted.append, interval=0.01)
    watcher.check_once()
    watcher.check_once()  # 같은 알림을 두 번 보여 주지 않는다
    assert len(emitted) == 1
    assert "스트레칭" in emitted[0]
    assert emitted[0].endswith(cli.PROMPT)


def test_reminder_watcher_thread_stops(tmp_path):
    import threading
    from datetime import timedelta

    from jev.korean import now
    from jev.skills import reminders

    reminders.add(tmp_path, "물", now() - timedelta(seconds=1))
    seen = threading.Event()
    watcher = cli.ReminderWatcher(tmp_path, threading.Lock(), lambda _: seen.set(), interval=0.01)
    watcher.start()
    assert seen.wait(2)
    watcher.stop()
    watcher.join(2)
    assert not watcher.is_alive()


def test_reminder_watcher_waits_for_lock(tmp_path):
    import threading
    from datetime import timedelta

    from jev.korean import now
    from jev.skills import reminders

    reminders.add(tmp_path, "회의", now() - timedelta(seconds=1))
    lock = threading.Lock()
    emitted = []
    watcher = cli.ReminderWatcher(tmp_path, lock, emitted.append, interval=0.01)
    with lock:  # 답변을 출력하는 중
        t = threading.Thread(target=watcher.check_once)
        t.start()
        t.join(0.1)
        assert emitted == []
    t.join(2)
    assert len(emitted) == 1
