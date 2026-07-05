import statsmodels.formula.api as smf
import pandas as pd
import logging
from typing import Dict, Any
from .utils import build_formula, extract_regression_results

logger = logging.getLogger(__name__)


def run_logit(df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
    dep_var = params["dependent_vars"][0]
    indep_vars = params.get("independent_vars", [])
    control_vars = params.get("control_vars", [])

    formula = build_formula(dep_var, indep_vars, control_vars)
    logger.info(f"Logit 公式: {formula}")

    model = smf.logit(formula=formula, data=df)
    results = model.fit()

    return extract_regression_results(results, "Logit", dep_var=dep_var)
