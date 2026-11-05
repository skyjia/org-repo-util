"""确定性采集器包。import 本包即完成全部 collector 的 handler 注册。"""

from analysis.collectors import base  # noqa: F401
from analysis.collectors import overview  # noqa: F401
from analysis.collectors import git_context  # noqa: F401
from analysis.collectors import structure  # noqa: F401
from analysis.collectors import docs  # noqa: F401
from analysis.collectors import tests  # noqa: F401
from analysis.collectors import dependencies  # noqa: F401
from analysis.collectors import quality  # noqa: F401
from analysis.collectors import security  # noqa: F401
from analysis.collectors import performance  # noqa: F401
