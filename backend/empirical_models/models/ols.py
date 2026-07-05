import statsmodels.formula.api as smf
import pandas as pd
import logging
from typing import Dict, Any
from .utils import build_formula, extract_regression_results, detect_panel_vars

logger = logging.getLogger(__name__)


def run_ols(df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
    dep_var = params["dependent_vars"][0]
    indep_vars = params.get("independent_vars", [])
    control_vars = params.get("control_vars", [])
    cluster_var = params.get("cluster_var")
    fixed_effects = params.get("fixed_effects", {}) or {}

    formula = build_formula(dep_var, indep_vars, control_vars)
    logger.info(f"OLS 公式: {formula}")

    model = smf.ols(formula=formula, data=df)

    if cluster_var:
        results = model.fit(cov_type='cluster', cov_kwds={'groups': df[cluster_var]})
    else:
        results = model.fit()

    # fe_info 在 utils.extract_regression_results 中从 fixed_effects 自动 normalize
    return extract_regression_results(results, "OLS", fe_info=None, dep_var=dep_var, fixed_effects=fixed_effects)
