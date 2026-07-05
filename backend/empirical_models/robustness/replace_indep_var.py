import pandas as pd
import logging
from typing import Dict, Any
from ..models import get_model_runner

logger = logging.getLogger(__name__)


def run_replace_indep_var(df: pd.DataFrame, params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    替换解释变量
    config 示例: {"replacements": {"旧解释变量": "新解释变量", ...}}
    """
    replacements = config.get("replacements", {})
    if not replacements:
        logger.warning("替换解释变量配置为空")
        return {"model_name": "替换解释变量", "error": "未配置变量替换关系"}

    new_params = dict(params)
    new_indep = list(new_params.get("independent_vars", []))

    for old_var, new_var in replacements.items():
        if old_var in new_indep and new_var in df.columns:
            idx = new_indep.index(old_var)
            new_indep[idx] = new_var
            logger.info(f"替换解释变量: {old_var} -> {new_var}")
        elif old_var in new_indep:
            logger.warning(f"替换变量 '{new_var}' 不存在于数据中，跳过替换 {old_var}")

    new_params["independent_vars"] = new_indep

    model_type = params.get("model_type", "ols")
    entry = get_model_runner(model_type)
    if not entry:
        return {"model_name": "替换解释变量", "error": f"不支持的模型类型: {model_type}"}

    label, runner = entry
    result = runner(df, new_params)
    result["model_name"] = f"替换解释变量 - {label}"
    return result
