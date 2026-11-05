"""AI 引擎单元测试：JSON 提取 + 失败取证（第三方 provider 噪音过滤）"""

import subprocess

import pytest

from analysis.ai.engine import AIEngine, AIEngineError, extract_json


# ---------- extract_json ----------

def test_extract_json_code_block():
    text = '分析如下：\n```json\n{"score": 80, "reasons": ["r1"]}\n```\n以上。'
    assert extract_json(text) == {"score": 80, "reasons": ["r1"]}


def test_extract_json_bare():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_noise_text():
    text = '好的，以下是结果：{"a": [1,2]} 希望有帮助'
    assert extract_json(text) == {"a": [1, 2]}


def test_extract_json_invalid_raises():
    with pytest.raises(AIEngineError):
        extract_json("完全没有 JSON 的回复")


# ---------- 失败取证（_failure_detail） ----------

def _proc(stdout="", stderr="", code=1):
    return subprocess.CompletedProcess(args=["claude"], returncode=code,
                                       stdout=stdout, stderr=stderr)


def test_failure_detail_filters_provider_noise():
    """stderr 只有 unrecognized_model 警告时不应把它当作错误主体"""
    p = _proc(stderr='[claude-code:unrecognized_model] {"model":"qwen3.8-max[1m]"}\n')
    detail = AIEngine._failure_detail(p)
    assert "unrecognized_model" not in detail


def test_failure_detail_parses_max_turns():
    envelope = '{"stop_reason":"max_turns","num_turns":60,"result":"..."}'
    p = _proc(stdout=envelope,
              stderr='[claude-code:unrecognized_model] {...}\nsome real error line\n')
    detail = AIEngine._failure_detail(p)
    assert "max_turns" in detail
    assert "max-turns 上限" in detail
    assert "some real error line" in detail


def test_failure_detail_keeps_real_stderr():
    p = _proc(stderr='[claude-code:unrecognized_model] {...}\nAPI Error: 429 rate limited\n')
    detail = AIEngine._failure_detail(p)
    assert "429" in detail


def test_failure_detail_no_output():
    assert AIEngine._failure_detail(_proc()) == "(无错误输出)"


def test_run_raises_with_detail_on_nonzero_exit(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _proc(stdout='{"stop_reason":"error_max_budget","num_turns":3}',
                     stderr='[claude-code:unrecognized_model] noise\nupstream 503\n')

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(AIEngine, "available", staticmethod(lambda: (True, "/usr/bin/claude")))
    engine = AIEngine()
    with pytest.raises(AIEngineError) as ei:
        engine.run("prompt", __import__("pathlib").Path("/tmp"), timeout=30)
    msg = str(ei.value)
    assert "503" in msg and "unrecognized_model" not in msg
    # 只读白名单与 max-turns 参数校验
    assert "--allowedTools" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--allowedTools") + 1] == "Read,Grep,Glob"
    assert captured["cmd"][captured["cmd"].index("--max-turns") + 1] == "120"
