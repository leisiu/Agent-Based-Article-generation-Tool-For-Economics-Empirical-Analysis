import numpy as np
import pandas as pd
import logging
from typing import Dict, Any
from ..models import get_model_runner

logger = logging.getLogger(__name__)


def run_winsorize(df: pd.DataFrame, params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    缩尾处理后回归
    config 示例: {"threshold": 0.01}  或  {"threshold": 0.05}
    """
    threshold = config.get("threshold", 0.01)
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    winsorized_df = df.copy()

    for col in numeric_cols:
        lower = df[col].quantile(threshold)
        upper = df[col].quantile(1 - threshold)
        winsorized_df[col] = np.clip(df[col], lower, upper)

    logger.info(f"缩尾处理完成(threshold={threshold})")

    model_type = params.get("model_type", "ols")
    entry = get_model_runner(model_type)
    if not entry:
        return {"model_name": "缩尾处理", "error": f"不支持的模型类型: {model_type}"}

    label, runner = entry
    result = runner(winsorized_df, params)
    result["model_name"] = f"缩尾处理({threshold*100}%) - {label}"
    return result
