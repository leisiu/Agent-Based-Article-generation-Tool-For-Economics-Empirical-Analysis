import pandas as pd
import numpy as np
import logging
from typing import Dict, Any
from pyfixest.estimation import feols

logger = logging.getLogger(__name__)


def _backtick(name: str) -> str:
    """用反引号包裹变量名，以支持括号等特殊字符"""
    return f"`{name}`"


def run_reghdfe(df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    reghdfe 高维固定效应回归：使用 pyfixest.feols。
    等价于 Stata 的 reghdfe y x, absorb(entity time)。

    参数:
      - entity_col: 个体固定效应列名
      - time_col:   时间固定效应列名
      - 其他标准参数 (dependent_vars, independent_vars, control_vars, cluster_var)
    """
    # 提取参数
    dep_var = (params.get('dependent_vars') or [params.get('dependent_var')])[0]
    indep_vars = params.get('independent_vars', [])
    control_vars = params.get('control_vars', [])
    cluster_var = params.get('cluster_var')
    entity_col = params.get('entity_col') or None
    time_col = params.get('time_col') or None

    if not entity_col or entity_col not in df.columns:
        raise ValueError("reghdfe 需要有效的个体固定效应变量 (entity_col)")
    if not time_col or time_col not in df.columns:
        raise ValueError("reghdfe 需要有效的时间固定效应变量 (time_col)")

    all_x = list(indep_vars) + list(control_vars)
    missing = [v for v in all_x + [dep_var] if v not in df.columns]
    if missing:
        raise ValueError(f"以下变量不在数据中: {missing}")

    logger.info(f"reghdfe: entity={entity_col}, time={time_col}")
    logger.info(f"reghdfe dep_var={dep_var}, all_x={all_x}")

    # 处理缺失值
    model_vars = [dep_var] + all_x + [entity_col, time_col]
    clean_df = df[model_vars].dropna()
    n_dropped = len(df) - len(clean_df)
    if n_dropped > 0:
        logger.info(f"reghdfe: 删除 {n_dropped} 行含缺失值的样本")
    if len(clean_df) == 0:
        raise ValueError("删除缺失值后无有效样本")

    # 构建公式：所有变量名用反引号包裹，以支持括号等特殊字符
    x_formula = " + ".join(_backtick(v) for v in all_x)
    fe_formula = f"{_backtick(entity_col)} + {_backtick(time_col)}"
    formula = f"{_backtick(dep_var)} ~ {x_formula} | {fe_formula}"
    logger.info(f"reghdfe formula: {formula}")

    # 聚类设置
    if cluster_var and cluster_var in df.columns:
        cluster_entity_vals = clean_df[entity_col].nunique()
        cluster_nobs = len(clean_df)
        logger.info(f"reghdfe: 聚类变量={entity_col}, 聚类数={cluster_entity_vals}, 样本量={cluster_nobs}")
        vcov_spec = {"CRV1": entity_col}
    else:
        vcov_spec = "hetero"

    # 回归
    fit = feols(formula, data=clean_df, vcov=vcov_spec)
    results = fit

    # 提取系数
    coef_dict = {}
    param_names = results.coef().index.tolist()
    for var_name in param_names:
        label = str(var_name)
        p_value = float(results.pvalue().loc[var_name])
        significance = ""
        if not (pd.isna(p_value) or np.isinf(p_value)):
            if p_value < 0.01:
                significance = "***"
            elif p_value < 0.05:
                significance = "**"
            elif p_value < 0.1:
                significance = "*"
        coef_dict[label] = {
            "coef": float(results.coef().loc[var_name]),
            "std_err": float(results.se().loc[var_name]),
            "t_value": float(results.tstat().loc[var_name]),
            "p_value": p_value,
            "significance": significance,
        }

    fe_info = {
        "个体固定效应": "是",
        "时间固定效应": "是",
    }

    return {
        "model_name": "reghdfe (pyfixest, 2D FE)",
        "dependent_var": dep_var,
        "coefficients": coef_dict,
        "model_stats": {
            "n_obs": int(results._N),
            "r_squared": float(results._r2),
            "within_r_squared": None,
            "between_r_squared": None,
            "f_statistic": None,
            "f_pvalue": None,
            "fe_info": fe_info,
        },
        "entity_col": entity_col,
        "time_col": time_col,
        "summary": str(results),
    }
