#!/bin/bash
# 代码审计工具 - 环境设置脚本（使用 uv）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔧 使用 uv 设置 Python 环境..."

# 检查 uv 是否已安装
if ! command -v uv &> /dev/null; then
    echo "❌ 错误: 未找到 uv，请先安装 uv"
    echo "   安装命令: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# 检查 Python 版本
uv python list | grep -q "3.11" || {
    echo "⚠️  警告: 未检测到 Python 3.11+，尝试安装..."
    uv python install 3.11
}

# 创建虚拟环境
echo "📦 创建虚拟环境..."
cd "$SCRIPT_DIR"
uv venv --python 3.11

# 安装依赖
echo "📦 安装依赖..."
uv pip install -r requirements.txt

echo ""
echo "✅ 设置完成！"
echo ""
echo "使用方法："
echo "  激活虚拟环境: source $SCRIPT_DIR/.venv/bin/activate"
echo "  或直接使用:   uv run audit --help"
echo "  退出虚拟环境: deactivate"
echo ""
