import pandas as pd
import numpy as np
import statsmodels.api as sm
import logging
from typing import Dict, Any
from linearmodels.panel import PanelOLS, RandomEffects

logger = logging.getLogger(__name__)


def run_xtreg(df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    面板数据回归，支持固定效应 (FE) 和随机效应 (RE)。
    """
    # 传入参数
    dep_var = (params.get('dependent_vars') or [params.get('dependent_var')])[0]
    indep_vars = params.get('independent_vars', [])
    control_vars = params.get('control_vars', [])
    cluster_var = params.get('cluster_var')
    entity_col = params.get('entity_col') or None
    time_col = params.get('time_col') or None
    effect_type = params.get('effect_type') or 'fe'
    all_x = list(indep_vars) + list(control_vars)

    # 校验
    missing = [v for v in all_x + [dep_var] if v not in df.columns]
    if missing:
        raise ValueError(f"以下变量不在数据中: {missing}")
    if not entity_col or entity_col not in df.columns:
        raise ValueError("xtreg 需要有效的个体变量 (entity_col)")
    if not time_col or time_col not in df.columns:
        raise ValueError("xtreg 需要有效的时间变量 (time_col)")

    logger.info(f"xtreg [{effect_type}] entity={entity_col}, time={time_col}")
    logger.info(f"xtreg 数据形状: {df.shape}, 列: {list(df.columns)}")
    logger.info(f"xtreg dep_var={dep_var}, all_x={all_x}")

    # 声明面板数据
    data = df.set_index([entity_col, time_col])
    y = data[[dep_var]]
    x = data[all_x].copy()
    x = sm.add_constant(x)

    # 判断回归类型并回归
    if effect_type == 'fe':
        model = PanelOLS(y, x, entity_effects=True, time_effects=True)

        if cluster_var and cluster_var in df.columns:
            results = model.fit(cov_type='clustered', cluster_entity=True, debiased=True)
        else:
            results = model.fit(debiased=True)

        model_name = "Fixed Effects (PanelOLS)"
    elif effect_type == 're':
        model = RandomEffects(y, x, check_rank=False)
        results = model.fit(debiased=True)
        model_name = "Random Effects"
    else:
        raise ValueError(f"不支持的效应类型: {effect_type}，请选择 'fe' 或 're'")

    # 提取系数
    coef_dict = {}
    for var_name in results.params.index:
        label = "常数项" if var_name == 'const' else var_name
        p_value = results.pvalues[var_name]
        significance = ""
        if not (pd.isna(p_value) or np.isinf(p_value)):
            if p_value < 0.01:
                significance = "***"
            elif p_value < 0.05:
                significance = "**"
            elif p_value < 0.1:
                significance = "*"
        coef_dict[label] = {
            "coef": float(results.params[var_name]) if pd.notna(results.params[var_name]) else None,
            "std_err": float(results.std_errors[var_name]) if pd.notna(results.std_errors[var_name]) else None,
            "t_value": float(results.tstats[var_name]) if pd.notna(results.tstats[var_name]) else None,
            "p_value": float(p_value) if pd.notna(p_value) else None,
            "significance": significance,
        }

    # 固定效应信息
    fe_info = {}
    if effect_type == 'fe':
        fe_info["个体固定效应"] = "是"
        fe_info["时间固定效应"] = "是"
    else:
        fe_info["效应类型"] = "随机效应"

    # 构建表格
    return {
        "model_name": model_name,
        "dependent_var": dep_var,
        "coefficients": coef_dict,
        "model_stats": {
            "n_obs": int(results.nobs),
            "r_squared": float(results.rsquared) if hasattr(results, 'rsquared') else None,
            "within_r_squared": float(results.rsquared_within) if hasattr(results, 'rsquared_within') else None,
            "between_r_squared": float(results.rsquared_between) if hasattr(results, 'rsquared_between') else None,
            "f_statistic": float(results.f_statistic.stat) if hasattr(results, 'f_statistic') else None,
            "f_pvalue": float(results.f_statistic.pval) if hasattr(results, 'f_statistic') else None,
            "fe_info": fe_info,
        },
        "entity_col": entity_col,
        "time_col": time_col,
        "effect_type": effect_type,
        "summary": str(results.summary),
    }
