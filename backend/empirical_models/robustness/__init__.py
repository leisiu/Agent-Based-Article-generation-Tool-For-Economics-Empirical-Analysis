from .replace_dep_var import run_replace_dep_var
from .replace_indep_var import run_replace_indep_var
from .shorten_window import run_shorten_window
from .winsorize import run_winsorize
from .remove_outliers import run_remove_outliers

ROBUSTNESS_REGISTRY = {
    "replace_dep_var": ("替换被解释变量", run_replace_dep_var),
    "replace_indep_var": ("替换解释变量", run_replace_indep_var),
    "shorten_window": ("缩短时间窗口", run_shorten_window),
    "winsorize": ("缩尾处理", run_winsorize),
    "remove_outliers": ("剔除异常值", run_remove_outliers),
}

def get_robustness_runner(test_type: str):
    if test_type not in ROBUSTNESS_REGISTRY:
        return None
    label, runner = ROBUSTNESS_REGISTRY[test_type]
    return label, runner
