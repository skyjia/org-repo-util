#!/bin/bash
# 仓库全面分析工具 - 环境设置脚本（使用 uv，参照 audit/setup.sh）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔧 使用 uv 设置 Python 环境..."

if ! command -v uv &> /dev/null; then
    echo "❌ 错误: 未找到 uv，请先安装 uv"
    echo "   安装命令: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

uv python list | grep -q "3.11" || {
    echo "⚠️  警告: 未检测到 Python 3.11+，尝试安装..."
    uv python install 3.11
}

echo "📦 创建虚拟环境..."
cd "$SCRIPT_DIR"
uv venv --python 3.11

echo "📦 安装依赖..."
uv pip install -r requirements.txt

echo "📁 创建状态目录..."
mkdir -p "$SCRIPT_DIR/state/tasks"

echo ""
echo "✅ 设置完成！"
echo ""
echo "使用方法："
echo "  直接运行:     $SCRIPT_DIR/bin/analyze --help"
echo "  或激活环境:   source $SCRIPT_DIR/.venv/bin/activate"
echo ""
