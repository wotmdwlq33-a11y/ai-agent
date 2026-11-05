from datetime import datetime

import pytest

from jev import local_skills
from jev.assistant import Jev
from jev.config import Config, ConfigError
from jev.memory import ConversationStore
from tests.fakes import AskOnlyClaude, FakeClaude


@pytest.fixture
def cfg(tmp_path):
    return Config(model=None, data_dir=tmp_path / "data")


def test_local_request_does_not_call_claude(cfg):
    claude = FakeClaude()
    jev = Jev(claude, config=cfg)
    answer = jev.handle("몇 시야?")
    assert answer.route.target == "local"
    assert claude.calls == []
    assert jev.history == []


def test_claude_request_appends_history(cfg):
    claude = FakeClaude()
    jev = Jev(claude, config=cfg)
    jev.handle("안녕")
    jev.handle("이 코드 분석해줘")

    assert [effort for _, effort in claude.calls] == ["low", "high"]
    # 두 번째 호출에는 첫 번째 대화가 앞에 그대로 들어 있어야 한다
    second_messages, _ = claude.calls[1]
    assert second_messages[0] == {"role": "user", "content": "안녕"}
    assert second_messages[1]["role"] == "assistant"
    assert len(jev.history) == 4


def test_refusal_is_not_added_to_history(cfg):
    jev = Jev(FakeClaude(refused=True), config=cfg)
    jev.handle("안녕")
    assert jev.history == []


def test_reset_clears_history(cfg):
    jev = Jev(FakeClaude(), config=cfg)
    jev.handle("안녕")
    answer = jev.handle("/reset")
    assert answer.route.skill == "reset"
    assert jev.history == []
    assert not cfg.history_path.exists()


def test_local_skill_formats():
    t = datetime(2026, 10, 9, 14, 5, tzinfo=local_skills.TIMEZONE)
    assert local_skills.run("time", t) == "지금은 14시 05분이에요."
    assert local_skills.run("date", t) == "오늘은 2026년 10월 09일 금요일이에요."


def test_history_persists_across_instances(cfg):
    Jev(FakeClaude(), config=cfg).handle("안녕")
    assert cfg.history_path.exists()

    claude = FakeClaude()
    jev = Jev(claude, config=cfg)
    assert len(jev.history) == 2
    jev.handle("또 안녕")
    sent, _ = claude.calls[0]
    assert sent[0] == {"role": "user", "content": "안녕"}


def test_memory_disabled_does_not_write(tmp_path):
    cfg = Config(model=None, data_dir=tmp_path / "data", memory_enabled=False)
    jev = Jev(FakeClaude(), config=cfg)
    jev.handle("안녕")
    assert len(jev.history) == 2
    assert not cfg.history_path.exists()


def test_history_limit_is_applied(tmp_path):
    cfg = Config(model=None, data_dir=tmp_path, max_history_messages=4)
    jev = Jev(FakeClaude(), config=cfg)
    for i in range(5):
        jev.handle(f"안녕 {i}")
    assert len(jev.history) <= 4
    assert jev.history[0]["role"] == "user"
    assert jev.history[-2] == {"role": "user", "content": "안녕 4"}
    assert ConversationStore(cfg.history_path).load() == jev.history


def test_streaming_uses_ask_stream(cfg):
    claude = FakeClaude(chunks=["응", "답"])
    jev = Jev(claude, config=cfg)
    seen = []
    answer = jev.handle("안녕", on_text=seen.append)
    assert seen == ["응", "답"]
    assert answer.streamed
    assert answer.text == "응답"


def test_streaming_falls_back_to_ask(cfg):
    claude = AskOnlyClaude()
    jev = Jev(claude, config=cfg)
    seen = []
    answer = jev.handle("안녕", on_text=seen.append)
    assert seen == []
    assert not answer.streamed
    assert len(claude.calls) == 1


def test_streamed_refusal_is_flagged_and_not_saved(cfg):
    jev = Jev(FakeClaude(refused=True), config=cfg)
    answer = jev.handle("안녕", on_text=lambda _: None)
    assert answer.refused and answer.streamed
    assert jev.history == []


def test_missing_model_raises_config_error(cfg):
    jev = Jev(config=cfg)
    with pytest.raises(ConfigError, match="JEV_MODEL"):
        jev.handle("안녕")
