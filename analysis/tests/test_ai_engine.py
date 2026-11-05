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
        captured["kwargs"] = kwargs
        return _proc(stdout='{"stop_reason":"error_max_budget","num_turns":3}',
                     stderr='[claude-code:unrecognized_model] noise\nupstream 503\n')

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(AIEngine, "available", staticmethod(lambda: (True, "/usr/bin/claude")))
    engine = AIEngine()
    with pytest.raises(AIEngineError) as ei:
        engine.run("prompt", __import__("pathlib").Path("/tmp"), timeout=30)
    msg = str(ei.value)
    assert "503" in msg and "unrecognized_model" not in msg
    cmd = captured["cmd"]
    # 只读白名单与 max-turns 参数校验
    assert cmd[cmd.index("--allowedTools") + 1] == "Read,Grep,Glob"
    assert cmd[cmd.index("--max-turns") + 1] == "120"
    # token 优化参数：MCP 注入屏蔽 + 环境清理
    assert "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    env = captured["kwargs"]["env"]
    assert not any(k.startswith("CMUX_") for k in env)


def test_run_success_returns_data_and_meta(monkeypatch):
    envelope = ('{"is_error":false,"stop_reason":"end_turn","num_turns":7,'
                '"duration_api_ms":1234,"total_cost_usd":0.42,'
                '"usage":{"input_tokens":10,"cache_creation_input_tokens":5000,'
                '"cache_read_input_tokens":40000,"output_tokens":800},'
                '"result":"```json\\n{\\"score\\": 80}\\n```"}')

    def fake_run(cmd, **kwargs):
        return _proc(stdout=envelope, code=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(AIEngine, "available", staticmethod(lambda: (True, "/usr/bin/claude")))
    data, meta = AIEngine().run("p", __import__("pathlib").Path("/tmp"), timeout=30)
    assert data == {"score": 80}
    assert meta["num_turns"] == 7
    assert meta["total_cost_usd"] == 0.42
    assert meta["cache_read_input_tokens"] == 40000


def test_run_empty_whitelist_no_flag_value(monkeypatch):
    """解读型子任务：空白名单传 --allowedTools ''（禁止一切工具）"""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _proc(stdout='{"result":"{\\"a\\":1}","is_error":false}', code=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(AIEngine, "available", staticmethod(lambda: (True, "/usr/bin/claude")))
    AIEngine().run("p", __import__("pathlib").Path("/tmp"), timeout=30, allowed_tools="")
    cmd = captured["cmd"]
    assert cmd[cmd.index("--allowedTools") + 1] == ""
