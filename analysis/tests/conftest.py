import sys
from pathlib import Path

# 项目根加入 sys.path（analysis/tests/conftest.py -> analysis -> org-repo-util）
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
