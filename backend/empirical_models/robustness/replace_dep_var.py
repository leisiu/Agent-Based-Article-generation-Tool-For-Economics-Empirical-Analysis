import pandas as pd
import logging
from typing import Dict, Any
from ..models import get_model_runner

logger = logging.getLogger(__name__)


def run_replace_dep_var(df: pd.DataFrame, params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    替换被解释变量
    config 示例: {"new_dep_var": "新被解释变量列名"}
    """
    new_dep_var = config.get("new_dep_var")
    if not new_dep_var or new_dep_var not in df.columns:
        logger.warning(f"替换被解释变量无效: {new_dep_var}")
        return {"model_name": "替换被解释变量", "error": f"变量 '{new_dep_var}' 不存在"}

    new_params = dict(params)
    new_params["dependent_vars"] = [new_dep_var]

    model_type = params.get("model_type", "ols")
    entry = get_model_runner(model_type)
    if not entry:
        return {"model_name": "替换被解释变量", "error": f"不支持的模型类型: {model_type}"}

    label, runner = entry
    result = runner(df, new_params)
    result["model_name"] = f"替换被解释变量({new_dep_var}) - {label}"
    return result
