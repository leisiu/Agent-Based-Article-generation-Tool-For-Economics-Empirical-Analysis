import pandas as pd
import logging
from typing import Dict, Any
from ..models import get_model_runner

logger = logging.getLogger(__name__)


def run_shorten_window(df: pd.DataFrame, params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    缩短时间窗口
    config 示例: {"time_col": "年度", "exclude_start": 2015, "exclude_end": 2017}
    剔除 exclude_start 到 exclude_end 之间的年份
    也支持 "exclude_years": [2015, 2016] 直接指定要剔除的年份列表
    """
    time_col = config.get("time_col")
    if not time_col or time_col not in df.columns:
        possible_time = ["年度", "年份", "year", "Year", "date", "DATE"]
        for col in possible_time:
            if col in df.columns:
                time_col = col
                break
        if not time_col:
            logger.warning("未找到时间列，无法缩短时间窗口")
            return {"model_name": "缩短时间窗口", "error": "未找到时间列"}

    filtered_df = df.copy()

    exclude_years = config.get("exclude_years", [])
    if exclude_years:
        filtered_df = filtered_df[~filtered_df[time_col].isin(exclude_years)]
        logger.info(f"剔除年份: {exclude_years}，剩余 {len(filtered_df)} 行")
    else:
        exclude_start = config.get("exclude_start")
        exclude_end = config.get("exclude_end")
        if exclude_start is not None and exclude_end is not None:
            filtered_df = filtered_df[
                (filtered_df[time_col] < exclude_start) | (filtered_df[time_col] > exclude_end)
            ]
            logger.info(f"剔除 {exclude_start}-{exclude_end} 年份，剩余 {len(filtered_df)} 行")
        else:
            return {"model_name": "缩短时间窗口", "error": "未配置要剔除的年份"}

    if len(filtered_df) < 10:
        return {"model_name": "缩短时间窗口", "error": f"剔除后样本量不足({len(filtered_df)}行)"}

    model_type = params.get("model_type", "ols")
    entry = get_model_runner(model_type)
    if not entry:
        return {"model_name": "缩短时间窗口", "error": f"不支持的模型类型: {model_type}"}

    label, runner = entry
    result = runner(filtered_df, params)
    result["model_name"] = f"缩短时间窗口 - {label}"
    return result
