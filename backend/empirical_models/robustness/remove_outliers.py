import numpy as np
import pandas as pd
from scipy import stats
import logging
from typing import Dict, Any
from ..models import get_model_runner

logger = logging.getLogger(__name__)


def run_remove_outliers(df: pd.DataFrame, params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    剔除异常值后回归
    config 示例: {"z_threshold": 3.0}  默认3个标准差
    """
    z_threshold = config.get("z_threshold", 3.0)
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    z_scores = np.abs(stats.zscore(df[numeric_cols], nan_policy='omit'))
    out_df = df[(z_scores < z_threshold).all(axis=1)].copy()
    removed = len(df) - len(out_df)

    logger.info(f"异常值剔除完成(z_threshold={z_threshold})，移除 {removed} 行，剩余 {len(out_df)} 行")

    if len(out_df) < 10:
        return {"model_name": "剔除异常值", "error": f"剔除后样本量不足({len(out_df)}行)"}

    model_type = params.get("model_type", "ols")
    entry = get_model_runner(model_type)
    if not entry:
        return {"model_name": "剔除异常值", "error": f"不支持的模型类型: {model_type}"}

    label, runner = entry
    result = runner(out_df, params)
    result["model_name"] = f"剔除异常值(Z>{z_threshold}) - {label}"
    return result
