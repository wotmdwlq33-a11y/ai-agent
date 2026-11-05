from datetime import datetime

from jev import local_skills
from jev.assistant import Jev
from jev.claude_client import ClaudeReply


class FakeClaude:
    def __init__(self, refused=False):
        self.calls = []
        self.refused = refused

    def ask(self, messages, effort):
        self.calls.append((list(messages), effort))
        content = [{"type": "text", "text": "응답"}]
        return ClaudeReply("응답", content, refused=self.refused)


def test_local_request_does_not_call_claude():
    claude = FakeClaude()
    jev = Jev(claude)
    answer = jev.handle("몇 시야?")
    assert answer.route.target == "local"
    assert claude.calls == []
    assert jev.history == []


def test_claude_request_appends_history():
    claude = FakeClaude()
    jev = Jev(claude)
    jev.handle("안녕")
    jev.handle("이 코드 분석해줘")

    assert [effort for _, effort in claude.calls] == ["low", "high"]
    # 두 번째 호출에는 첫 번째 대화가 앞에 그대로 들어 있어야 한다
    second_messages, _ = claude.calls[1]
    assert second_messages[0] == {"role": "user", "content": "안녕"}
    assert second_messages[1]["role"] == "assistant"
    assert len(jev.history) == 4


def test_refusal_is_not_added_to_history():
    jev = Jev(FakeClaude(refused=True))
    jev.handle("안녕")
    assert jev.history == []


def test_reset_clears_history():
    jev = Jev(FakeClaude())
    jev.handle("안녕")
    answer = jev.handle("/reset")
    assert answer.route.skill == "reset"
    assert jev.history == []


def test_local_skill_formats():
    t = datetime(2026, 10, 9, 14, 5, tzinfo=local_skills.TIMEZONE)
    assert local_skills.run("time", t) == "지금은 14시 05분이에요."
    assert local_skills.run("date", t) == "오늘은 2026년 10월 09일 금요일이에요."
