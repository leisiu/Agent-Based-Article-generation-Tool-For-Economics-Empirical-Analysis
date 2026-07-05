from .ols import run_ols
from .xtreg import run_xtreg
from .reghdfe import run_reghdfe
from .logit import run_logit
from .probit import run_probit
from .utils import build_formula, extract_regression_results

MODEL_REGISTRY = {
    "reg": ("OLS (reg)", run_ols),
    "xtreg": ("Panel (xtreg)", run_xtreg),
    "reghdfe": ("HDFE (reghdfe)", run_reghdfe),
    "logit": ("Logit", run_logit),
    "probit": ("Probit", run_probit),
}

def get_model_runner(model_type: str):
    if model_type not in MODEL_REGISTRY:
        return None
    label, runner = MODEL_REGISTRY[model_type]
    return label, runner
