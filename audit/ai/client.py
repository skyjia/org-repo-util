"""
AI 客户端 - 仅支持 Claude，复用本机 Claude Code 配置
"""

import os
import json
from typing import Optional, Dict, Any, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ClaudeClient:
    """Claude API 客户端 - 复用 ~/.claude/settings.json 配置"""

    def __init__(self):
        """从 ~/.claude/settings.json 读取配置"""
        config = self._load_claude_config()

        self.api_key = config.get("ANTHROPIC_AUTH_TOKEN") or config.get("ANTHROPIC_API_KEY")
        self.base_url = config.get("ANTHROPIC_BASE_URL")
        self.model = config.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

        if not self.api_key:
            raise ValueError("未在 ~/.claude/settings.json 中找到 ANTHROPIC_AUTH_TOKEN")

        try:
            import anthropic
            if self.base_url:
                self.client = anthropic.Anthropic(
                    api_key=self.api_key,
                    base_url=self.base_url
                )
            else:
                self.client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("请安装 anthropic 包: pip install anthropic")

    def _load_claude_config(self) -> Dict[str, Any]:
        """从 ~/.claude/settings.json 加载配置"""
        settings_path = Path.home() / ".claude" / "settings.json"

        if not settings_path.exists():
            logger.warning(f"未找到 {settings_path}，使用默认配置")
            return {}

        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)

            # 从 env 字段提取配置
            env_config = settings.get("env", {})
            return env_config
        except Exception as e:
            logger.error(f"读取 {settings_path} 失败: {e}")
            return {}

    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 4096, **kwargs) -> str:
        """发送聊天请求到 Claude"""
        try:
            # 转换消息格式
            claude_messages = []
            for msg in messages:
                claude_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=claude_messages,
                **kwargs
            )

            # 处理响应内容（可能是 TextBlock 或 ThinkingBlock）
            content = response.content[0]
            if hasattr(content, 'text'):
                return content.text
            elif hasattr(content, 'thinking'):
                return content.thinking
            else:
                return str(content)

        except Exception as e:
            logger.error(f"Claude API 调用失败: {e}")
            raise


def create_claude_client() -> ClaudeClient:
    """创建 Claude 客户端"""
    return ClaudeClient()
