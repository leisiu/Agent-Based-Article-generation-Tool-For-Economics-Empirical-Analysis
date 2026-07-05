import pandas as pd
import numpy as np
import statsmodels.api as sm
from scipy import stats
from typing import Dict, Any, List, Optional
import logging

from .models import get_model_runner
from .robustness import get_robustness_runner


def _merge_baseline_to_params(params: Dict[str, Any], bm: Dict[str, Any]) -> Dict[str, Any]:
    """把 baseline model 配置合并到 params（用于让现有 runner 直接使用）"""
    merged = dict(params)
    if bm.get("dependent_var"):
        merged["dependent_vars"] = [bm["dependent_var"]]
    if "independent_vars" in bm:
        merged["independent_vars"] = list(bm.get("independent_vars") or [])
    if "control_vars" in bm:
        merged["control_vars"] = list(bm.get("control_vars") or [])
    if "fixed_effects" in bm:
        merged["fixed_effects"] = dict(bm.get("fixed_effects") or {})
    if "entity_col" in bm:
        merged["entity_col"] = bm.get("entity_col")
    if "time_col" in bm:
        merged["time_col"] = bm.get("time_col")
    if "effect_type" in bm:
        merged["effect_type"] = bm.get("effect_type")
    if "cluster_var" in bm:
        merged["cluster_var"] = bm.get("cluster_var")
    if bm.get("regression_methods"):
        # 暂存到 merged['regression_methods']，由外层循环
        merged["_baseline_regression_methods"] = list(bm.get("regression_methods") or [])
    if bm.get("name"):
        merged["_baseline_name"] = bm.get("name")
    return merged

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmpiricalEngine:
    def __init__(self):
        self.results = {}

    def run_all_tests(self, df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        self.results = {}

        try:
            if params.get("test_types"):
                if "descriptive" in params["test_types"]:
                    self.results["descriptive"] = self._descriptive_statistics(df, params)

                if "regression" in params["test_types"]:
                    self.results["regression"] = self._run_regression_by_selection(df, params)

                if "heterogeneity" in params["test_types"]:
                    self.results["heterogeneity"] = self._heterogeneity_analysis(df, params)

                if "robustness" in params["test_types"]:
                    self.results["robustness"] = self._run_robustness_by_selection(df, params)

                if "moderation" in params["test_types"]:
                    self.results["moderation"] = self._moderation_analysis(df, params)

                if "mechanism" in params["test_types"]:
                    self.results["mechanism"] = self._mechanism_test(df, params)

            logger.info("所有实证检验完成")
            # 终极保险：清洗所有结果中的 nan/inf 为 None（保证 JSON 可序列化）
            return self._clean_nan_inf(self.results)

        except Exception as e:
            logger.error(f"实证检验失败: {str(e)}")
            raise
    def _clean_nan_inf(self, obj):
        """递归清洗字典/列表/基本类型中的 nan/inf → None"""
        if isinstance(obj, dict):
            return {k: self._clean_nan_inf(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._clean_nan_inf(v) for v in obj]
        if isinstance(obj, tuple):
            return tuple(self._clean_nan_inf(v) for v in obj)
        if isinstance(obj, float):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return obj
        # numpy scalar 类型也要转
        if hasattr(obj, "item") and not isinstance(obj, (str, bytes, int, bool)):
            try:
                v = obj.item()
                if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                    return None
                return v
            except Exception:
                return obj
        return obj

    def _run_regression_by_selection(self, df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        基准回归：支持多模型（每个模型独立变量配置）。

        新结构（来自前端 VariableSelector 的 baseline_models 列表）：
        params["baseline_models"] = [
            {
                "name": "模型1",
                "dependent_var": "Y",
                "independent_vars": ["X1","X2"],
                "control_vars": ["C1"],
                "fixed_effects": {"个体": "true", "时间": "true"},
                "cluster_var": "个体",
                "regression_methods": ["fe", "ols"],
                "missing_method": "drop"
            },
            ...
        ]

        旧结构（向后兼容）：params["regression_models"] = ["fe","ols"]
        此时使用 params 顶层的 dependent_vars / independent_vars / control_vars。
        """
        baseline_models = params.get("baseline_models") or []
        results = {}

        # ====== 新结构：每个模型独立配置 ======
        if baseline_models and isinstance(baseline_models, list):
            for model_cfg in baseline_models:
                model_name = model_cfg.get("name") or f"模型{len(results) + 1}"
                dep_var = model_cfg.get("dependent_var")
                if not dep_var:
                    logger.warning(f"[{model_name}] 缺少被解释变量，跳过")
                    results[model_name] = {"model_name": model_name, "error": "缺少被解释变量"}
                    continue

                # 构造该模型专属的 params 子集
                sub_params = {
                    "dependent_vars": [dep_var],
                    "independent_vars": model_cfg.get("independent_vars") or [],
                    "control_vars": model_cfg.get("control_vars") or [],
                    "fixed_effects": model_cfg.get("fixed_effects") or {},
                    "entity_col": model_cfg.get("entity_col") or None,
                    "time_col": model_cfg.get("time_col") or None,
                    "effect_type": model_cfg.get("effect_type") or "fe",
                    "cluster_var": model_cfg.get("cluster_var") or None,
                    "model_type": (model_cfg.get("regression_methods") or [model_cfg.get("model") or "reg"])[0],
                    "missing_method": model_cfg.get("missing_method") or "drop",
                }

                methods = model_cfg.get("regression_methods") or [sub_params["model_type"]]
                if isinstance(methods, str):
                    methods = [methods]

                model_result = {"model_name": model_name, "methods": {}}
                has_error = False
                for mt in methods:
                    sub_params["model_type"] = mt
                    entry = get_model_runner(mt)
                    if not entry:
                        logger.warning(f"[{model_name}] 不支持的模型类型: {mt}")
                        model_result["methods"][mt] = {"model_name": mt, "error": f"不支持的模型类型: {mt}"}
                        has_error = True
                        continue
                    label, runner = entry
                    try:
                        model_result["methods"][mt] = runner(df, sub_params)
                        logger.info(f"[{model_name}][{label}] 完成")
                    except Exception as e:
                        logger.error(f"[{model_name}][{label}] 失败: {str(e)}")
                        model_result["methods"][mt] = {"model_name": label, "error": str(e)}
                        has_error = True

                if has_error and not model_result["methods"]:
                    model_result["error"] = "所有方法均执行失败"

                results[model_name] = model_result

            return results

        # ====== 旧结构（兼容老 payload）======
        model_types = params.get("regression_models", [params.get("model_type", "ols")])
        if isinstance(model_types, str):
            model_types = [model_types]

        for mt in model_types:
            entry = get_model_runner(mt)
            if not entry:
                logger.warning(f"不支持的模型类型: {mt}")
                continue
            label, runner = entry
            try:
                result = runner(df, params)
                results[mt] = result
                logger.info(f"基准回归 [{label}] 完成")
            except Exception as e:
                logger.error(f"基准回归 [{label}] 失败: {str(e)}")
                results[mt] = {"model_name": label, "error": str(e)}

        return results

    def _run_robustness_by_selection(self, df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据用户选择运行稳健性检验，每种检验对应独立模块。
        params["robustness_tests"] = [
            {
              "type": "replace_dep_var",
              "config": {"new_dep_var": "xxx"},
              "applied_baseline_models": [{name, dependent_var, ...}, ...]   # 参与本检验的 baseline models
            },
            ...
        ]
        循环维度: (test_type, baseline, regression_method)
        结果结构: {test_type: {label, baselines: {bm_name: {name, methods: {mt: result}}}}}
        """
        results = {}
        test_list = params.get("robustness_tests", [])

        if not test_list:
            logger.info("未选择稳健性检验，跳过")
            return {}

        for test_cfg in test_list:
            test_type = test_cfg.get("type", "")
            config = test_cfg.get("config", {})

            entry = get_robustness_runner(test_type)
            if not entry:
                logger.warning(f"不支持的稳健性检验类型: {test_type}")
                continue

            label, runner = entry

            # 当前 test 的"参与 baselines"
            applied = test_cfg.get("applied_baseline_models") or params.get("baseline_models") or []
            if not applied:
                first_bm = (params.get("baseline_models") or [{}])[0]
                applied = [first_bm]

            test_payload = {"label": label, "baselines": {}}
            for bm in applied:
                merged_params = _merge_baseline_to_params(params, bm)
                bm_name = bm.get("name") or f"baseline{len(test_payload['baselines']) + 1}"
                methods = bm.get("regression_methods") or [merged_params.get("model_type", "ols")]
                if isinstance(methods, str):
                    methods = [methods]

                method_results = {}
                for mt in methods:
                    merged_params["model_type"] = mt
                    try:
                        r = runner(df, merged_params, config)
                        method_results[mt] = r
                    except Exception as e:
                        logger.error(f"稳健性 [{label}] [{bm_name}] [{mt}] 失败: {e}")
                        method_results[mt] = {"model_name": f"{label} - {bm_name} - {mt}", "error": str(e)}
                test_payload["baselines"][bm_name] = {
                    "name": bm_name,
                    "methods": method_results,
                }

            results[test_type] = test_payload
            logger.info(f"稳健性检验 [{label}] 完成（{len(applied)} 个 baseline）")

        return results

    def _collect_all_variables(self, params: Dict[str, Any]) -> Dict[str, list]:
        """
        从多种结构中汇总被解释/解释/控制/中介/分组/调节变量：
          - 旧结构：params 顶层 dependent_vars / independent_vars / control_vars
          - 新结构：params["baseline_models"] 内各模型的变量
                    + heterogeneity_methods 内的 group_var
                    + mechanism_methods 内的 mediator_var
        """
        dep = list(params.get("dependent_vars", []))
        indep = list(params.get("independent_vars", []))
        ctrl = list(params.get("control_vars", []))
        extra = []  # 异质性 group / 机制 mediator（用于描述/相关性）

        # 新结构：基准模型
        for m in params.get("baseline_models", []) or []:
            dv = m.get("dependent_var")
            if dv and dv not in dep:
                dep.append(dv)
            for v in m.get("independent_vars", []) or []:
                if v not in indep:
                    indep.append(v)
            for v in m.get("control_vars", []) or []:
                if v not in ctrl:
                    ctrl.append(v)

        # 新结构：异质性方法（提取 group_var / group_vars）
        for m in params.get("heterogeneity_methods", []) or []:
            gv = m.get("group_var")
            gvs = m.get("group_vars")
            if gvs:
                for v in gvs:
                    if v and v not in extra:
                        extra.append(v)
            elif gv:
                if gv not in extra:
                    extra.append(gv)
            dv = m.get("dependent_var")
            if dv and dv not in dep:
                dep.append(dv)
            for v in m.get("independent_vars", []) or []:
                if v not in indep:
                    indep.append(v)
            for v in m.get("control_vars", []) or []:
                if v not in ctrl:
                    ctrl.append(v)

        # 新结构：机制方法（提取 mediator_var / mediator_vars）
        for m in params.get("mechanism_methods", []) or []:
            mv = m.get("mediator_var")
            mvs = m.get("mediator_vars")
            if mvs:
                for v in mvs:
                    if v and v not in extra:
                        extra.append(v)
            elif mv:
                if mv not in extra:
                    extra.append(mv)
            dv = m.get("dependent_var")
            if dv and dv not in dep:
                dep.append(dv)
            for v in m.get("independent_vars", []) or []:
                if v not in indep:
                    indep.append(v)
            for v in m.get("control_vars", []) or []:
                if v not in ctrl:
                    ctrl.append(v)

        # 新结构：调节方法（提取 moderator_var / moderator_vars）
        for m in params.get("moderation_methods", []) or []:
            mv = m.get("moderator_var") or m.get("moderation_var")
            mvs = m.get("moderator_vars")
            if mvs:
                for v in mvs:
                    if v and v not in extra:
                        extra.append(v)
            elif mv:
                if mv not in extra:
                    extra.append(mv)

        return {
            "dependent_vars": dep,
            "independent_vars": indep,
            "control_vars": ctrl,
            "extra_vars": extra,
        }

    def _descriptive_statistics(self, df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        collected = self._collect_all_variables(params)
        vars_to_analyze = (
            collected["dependent_vars"]
            + collected["independent_vars"]
            + collected["control_vars"]
            + collected.get("extra_vars", [])
        )
        vars_to_analyze = list(set(vars_to_analyze))

        existing_vars = [v for v in vars_to_analyze if v in df.columns]
        if not existing_vars:
            logger.warning("没有有效的变量进行分析")
            return {"variables": {}, "sample_size": len(df), "variable_count": 0}

        numeric_df = df[existing_vars].select_dtypes(include=[np.number])

        desc = numeric_df.describe().T
        desc["median"] = numeric_df.median()
        desc["skew"] = numeric_df.skew()
        desc["kurtosis"] = numeric_df.kurtosis()
        desc["count"] = numeric_df.count()
        desc["missing"] = numeric_df.isnull().sum()

        desc = desc[["count", "missing", "mean", "std", "min", "25%", "50%", "75%", "max", "median", "skew", "kurtosis"]]

        # 清理非法值：nan/inf/-inf 等非 JSON 兼容值统一替换为 None
        desc = desc.replace([np.inf, -np.inf], np.nan)
        variables_dict = desc.to_dict('index')
        for var_name, var_stats in variables_dict.items():
            for key, value in list(var_stats.items()):
                if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
                    var_stats[key] = None

        result = {
            "variables": variables_dict,
            "sample_size": len(df),
            "variable_count": len(numeric_df.columns)
        }

        logger.info("描述性统计完成")
        return result

    def _correlation_analysis(self, df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        # 兼容新旧结构：从 baseline_models / heterogeneity_methods / mechanism_methods
        # 以及顶层 dependent_vars / independent_vars / control_vars 汇总变量
        collected = self._collect_all_variables(params)
        vars_to_analyze = (
            collected["dependent_vars"]
            + collected["independent_vars"]
            + collected["control_vars"]
            + collected.get("extra_vars", [])
        )
        vars_to_analyze = list(set(vars_to_analyze))

        existing_vars = [v for v in vars_to_analyze if v in df.columns]
        if len(existing_vars) < 2:
            logger.warning("变量数量不足，无法进行相关性分析")
            return {"pearson": {}, "spearman": {}, "variable_count": 0}

        numeric_df = df[existing_vars].select_dtypes(include=[np.number])
        # 剔除常数列（std=0）以避免产生 nan
        std = numeric_df.std()
        numeric_df = numeric_df.loc[:, std > 0]

        if numeric_df.shape[1] < 2:
            logger.warning("剔除常数列后变量数 < 2，跳过相关性分析")
            return {"pearson": {}, "spearman": {}, "variable_count": 0}

        corr_matrix = numeric_df.corr(method='pearson')
        p_values = self._calculate_correlation_pvalues(numeric_df)
        spearman_corr = numeric_df.corr(method='spearman')

        # 统一清洗 nan/inf 为 None（保证 JSON 可序列化）
        def _clean(obj):
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()}
            if isinstance(obj, float):
                if np.isnan(obj) or np.isinf(obj):
                    return None
                return obj
            return obj

        result = {
            "pearson": _clean(corr_matrix.to_dict()),
            "p_values": _clean(p_values.to_dict()),
            "spearman": _clean(spearman_corr.to_dict()),
            "variable_count": int(numeric_df.shape[1])
        }

        logger.info("相关性分析完成")
        return result

    def _calculate_correlation_pvalues(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.dropna()._get_numeric_data()
        cols = df.columns
        p_values = pd.DataFrame(np.ones((len(cols), len(cols))), index=cols, columns=cols)

        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                corr, p = stats.pearsonr(df[cols[i]], df[cols[j]])
                p_values.loc[cols[i], cols[j]] = p
                p_values.loc[cols[j], cols[i]] = p

        return p_values

    def _vif_test(self, df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        # 兼容新旧结构：从 baseline_models / heterogeneity_methods / mechanism_methods
        # 以及顶层字段汇总参与多重共线性检验的解释变量和控制变量
        collected = self._collect_all_variables(params)
        independent_vars = collected["independent_vars"] + collected["control_vars"]
        independent_vars = list(set(independent_vars))

        numeric_df = df[independent_vars].select_dtypes(include=[np.number])

        X = sm.add_constant(numeric_df)

        vif_data = pd.DataFrame()
        vif_data["variable"] = X.columns
        vif_data["VIF"] = [1 / (1 - sm.OLS(X[col], X.drop(col, axis=1)).fit().rsquared) for col in X.columns]

        vif_data = vif_data[vif_data["variable"] != "const"]
        vif_data = vif_data.sort_values(by="VIF", ascending=False)

        result = {
            "vif_values": vif_data.set_index("variable")["VIF"].to_dict(),
            "mean_vif": vif_data["VIF"].mean(),
            "max_vif": vif_data["VIF"].max(),
            "high_vif_vars": vif_data[vif_data["VIF"] > 10]["variable"].tolist()
        }

        logger.info("VIF检验完成")
        return result

    def _heterogeneity_analysis(self, df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        异质性分析：支持多种方法，每种方法独立变量配置。

        新结构（来自前端 heterogeneity_methods 列表）：
        params["heterogeneity_methods"] = [
            {
                "method": "subgroup" | "median_split" | "interaction",
                "group_var": "...",
                "dependent_var": "Y",
                "independent_vars": ["X1"],
                "control_vars": [...],
                "fixed_effects": {...},
                "cluster_var": "...",
                "regression_methods": ["fe"],
                "model": "fe"
            },
            ...
        ]

        旧结构（兼容）：params["heterogeneity_var"] 单分组变量 + 顶层 dependent_vars。
        """
        het_methods = params.get("heterogeneity_methods")
        results = {"methods": {}, "count": 0}

        if het_methods is not None and isinstance(het_methods, list):
            for mcfg in het_methods:
                method = mcfg.get("method", "subgroup")
                _gv = mcfg.get("group_vars")
                group_vars_list = _gv if isinstance(_gv, list) and len(_gv) > 0 else [mcfg.get("group_var")]
                method_label_map = {
                    "subgroup": "分组回归",
                    "median_split": "中位数分组",
                    "interaction": "交互项模型",
                }
                method_label = method_label_map.get(method, method)

                # 构造本方法专属的子 params（与 group_var 无关部分）
                dep_var = mcfg.get("dependent_var") or (
                    params.get("dependent_vars", [None])[0] if params.get("dependent_vars") else None
                )
                if not dep_var:
                    first_gv = next((g for g in group_vars_list if g), "")
                    method_key = f"{method_label}({first_gv})" if first_gv else method_label
                    results["methods"][method_key] = {"method": method, "error": "缺少被解释变量"}
                    continue

                sub_params = {
                    "dependent_vars": [dep_var],
                    "independent_vars": mcfg.get("independent_vars") or [],
                    "control_vars": mcfg.get("control_vars") or [],
                    "fixed_effects": mcfg.get("fixed_effects") or {},
                    "entity_col": mcfg.get("entity_col") or None,
                    "time_col": mcfg.get("time_col") or None,
                    "effect_type": mcfg.get("effect_type") or "fe",
                    "cluster_var": mcfg.get("cluster_var") or None,
                    "model_type": (mcfg.get("regression_methods") or [mcfg.get("model") or "reg"])[0],
                }

                for group_var in group_vars_list:
                    if not group_var:
                        continue
                    method_key = f"{method_label}({group_var})"

                    if group_var not in df.columns:
                        results["methods"][method_key] = {
                            "method": method,
                            "group_var": group_var,
                            "error": f"分组变量 '{group_var}' 不在数据中或未指定",
                        }
                        continue

                    # 参与本检验的 baseline models
                    applied_baselines = mcfg.get("applied_baseline_models") or []
                    if not applied_baselines:
                        first_bm = (params.get("baseline_models") or [{}])[0]
                        if first_bm.get("dependent_var"):
                            applied_baselines = [first_bm]

                    # 依据 method 路由到不同实现
                    if method == "subgroup":
                        res = self._het_subgroup_multi(df, sub_params, group_var, method_label, applied_baselines)
                    elif method == "median_split":
                        res = self._het_median_split_multi(df, sub_params, group_var, method_label, applied_baselines)
                    elif method == "interaction":
                        res = self._het_interaction_multi(df, sub_params, group_var, method_label, applied_baselines)
                    else:
                        res = {"method": method, "error": f"不支持的异质性方法: {method}"}

                    results["methods"][method_key] = res

            results["count"] = len([k for k, v in results["methods"].items() if not v.get("error")])
            return results

        # ====== 旧结构（兼容） ======
        group_var = params.get("heterogeneity_var", params.get("group_var", ""))
        if not group_var or group_var not in df.columns:
            logger.info(f"未指定有效的分组变量 '{group_var}'，跳过异质性分析")
            return {"tests": [], "count": 0, "note": "未指定分组变量或分组变量不在数据中"}

        groups = df[group_var].dropna().unique()
        logger.info(f"异质性分析: 按 {group_var} 分组，共 {len(groups)} 组")

        legacy_results = {}
        for group_val in groups:
            group_df = df[df[group_var] == group_val]
            if len(group_df) < 30:
                logger.info(f"组 {group_var}={group_val} 样本量 {len(group_df)} < 30，跳过")
                continue
            group_result = self._run_regression_by_selection(group_df, params)
            legacy_results[f"{group_var}_{group_val}"] = group_result
            logger.info(f"异质性分析: {group_var}={group_val} 完成")

        if not legacy_results:
            return {"tests": [], "count": 0, "note": "分组后无有效样本（每组至少需要30条）"}
        return {"tests": legacy_results, "count": len(legacy_results), "group_var": group_var}

    def _het_subgroup(self, df: pd.DataFrame, sub_params: Dict, group_var: str, method_label: str) -> Dict[str, Any]:
        """分组回归：按分类变量分样本回归"""
        groups = df[group_var].dropna().unique()
        logger.info(f"[{method_label}] 按 {group_var} 分组，共 {len(groups)} 组")
        tests = {}
        for gv in groups:
            sub_df = df[df[group_var] == gv]
            if len(sub_df) < 30:
                logger.info(f"[{method_label}] 组 {group_var}={gv} 样本量 {len(sub_df)} < 30，跳过")
                continue
            group_result = self._run_regression_by_selection(sub_df, sub_params)
            tests[f"{group_var}_{gv}"] = group_result
        return {
            "method": "subgroup",
            "method_label": method_label,
            "group_var": group_var,
            "tests": tests,
            "count": len(tests),
        }

    def _het_median_split(self, df: pd.DataFrame, sub_params: Dict, group_var: str, method_label: str) -> Dict[str, Any]:
        """
        中位数分组：连续变量按中位数切分为高/低两组
        新增 group_var_high / group_var_low 两个子样本
        """
        if not pd.api.types.is_numeric_dtype(df[group_var]):
            return {
                "method": "median_split",
                "method_label": method_label,
                "group_var": group_var,
                "error": f"中位数分组要求连续变量，'{group_var}' 不是数值型",
            }
        median_val = df[group_var].median()
        high_df = df[df[group_var] >= median_val].copy()
        low_df = df[df[group_var] < median_val].copy()
        tests = {}
        for label, sub_df in [("high", high_df), ("low", low_df)]:
            if len(sub_df) < 30:
                logger.info(f"[{method_label}] {label} 组样本量 {len(sub_df)} < 30，跳过")
                continue
            tests[f"{group_var}_{label}"] = self._run_regression_by_selection(sub_df, sub_params)
        return {
            "method": "median_split",
            "method_label": method_label,
            "group_var": group_var,
            "median": float(median_val) if pd.notna(median_val) else None,
            "tests": tests,
            "count": len(tests),
        }

    def _het_interaction(self, df: pd.DataFrame, sub_params: Dict, group_var: str, method_label: str) -> Dict[str, Any]:
        """
        交互项模型：构建 X × M 检验调节效应
        对每个 X 与 group_var 构建交互项（中心化）
        """
        original_independent = list(sub_params.get("independent_vars", []))
        if not original_independent:
            return {
                "method": "interaction",
                "method_label": method_label,
                "group_var": group_var,
                "error": "无解释变量，无法构建交互项",
            }
        if group_var not in df.columns:
            return {
                "method": "interaction",
                "method_label": method_label,
                "group_var": group_var,
                "error": f"调节变量 '{group_var}' 不在数据中",
            }

        interaction_tests = {}
        for x_var in original_independent:
            if x_var not in df.columns:
                continue
            interaction_col = f"{x_var}_x_{group_var}"
            try:
                df_temp = df.copy()
                x_centered = df_temp[x_var] - df_temp[x_var].mean()
                m_centered = df_temp[group_var] - df_temp[group_var].mean()
                df_temp[interaction_col] = x_centered * m_centered

                mod_params = dict(sub_params)
                mod_params["independent_vars"] = list(original_independent) + [group_var, interaction_col]

                entry = get_model_runner(sub_params.get("model_type", "ols"))
                if not entry:
                    continue
                _, runner = entry
                result = runner(df_temp, mod_params)
                interaction_tests[x_var] = {
                    "moderator": group_var,
                    "interaction_term": interaction_col,
                    "result": result,
                }
                logger.info(f"[{method_label}] {x_var} × {group_var} 完成")
            except Exception as e:
                logger.error(f"[{method_label}] {x_var} × {group_var} 失败: {str(e)}")
                interaction_tests[x_var] = {"moderator": group_var, "error": str(e)}

        return {
            "method": "interaction",
            "method_label": method_label,
            "group_var": group_var,
            "tests": interaction_tests,
            "count": len(interaction_tests),
        }

    # ==================== 异质性：多 baseline 版本 ====================
    def _het_subgroup_multi(self, df, sub_params, group_var, method_label, applied_baselines):
        """分组回归：多 baseline，每个 baseline 在每个分组下回归"""
        groups = df[group_var].dropna().unique()
        logger.info(f"[{method_label}] 按 {group_var} 分组，共 {len(groups)} 组 × {len(applied_baselines)} 个 baseline")
        tests = {}
        for bm in applied_baselines:
            bm_merged = _merge_baseline_to_params(sub_params, bm)
            bm_name = bm.get("name") or f"baseline{len(tests) + 1}"
            methods = bm.get("regression_methods") or [bm_merged.get("model_type", "ols")]
            if isinstance(methods, str):
                methods = [methods]
            bm_tests = {}
            for gv in groups:
                sub_df = df[df[group_var] == gv]
                if len(sub_df) < 30:
                    continue
                mt_results = {}
                for mt in methods:
                    bm_merged["model_type"] = mt
                    try:
                        entry = get_model_runner(mt)
                        if not entry:
                            continue
                        _, runner = entry
                        mt_results[mt] = runner(sub_df, bm_merged)
                    except Exception as e:
                        logger.error(f"[{method_label}][{bm_name}][{gv}][{mt}] 失败: {e}")
                        mt_results[mt] = {"model_name": mt, "error": str(e)}
                if mt_results:
                    bm_tests[f"{group_var}_{gv}"] = mt_results
            if bm_tests:
                tests[bm_name] = bm_tests
        return {
            "method": "subgroup",
            "method_label": method_label,
            "group_var": group_var,
            "tests": tests,
            "count": sum(len(v) for v in tests.values()),
        }

    def _het_median_split_multi(self, df, sub_params, group_var, method_label, applied_baselines):
        """中位数分组：多 baseline"""
        if not pd.api.types.is_numeric_dtype(df[group_var]):
            return {
                "method": "median_split",
                "method_label": method_label,
                "group_var": group_var,
                "error": f"中位数分组要求连续变量，'{group_var}' 不是数值型",
            }
        median_val = df[group_var].median()
        high_df = df[df[group_var] >= median_val].copy()
        low_df = df[df[group_var] < median_val].copy()
        tests = {}
        for bm in applied_baselines:
            bm_merged = _merge_baseline_to_params(sub_params, bm)
            bm_name = bm.get("name") or f"baseline{len(tests) + 1}"
            methods = bm.get("regression_methods") or [bm_merged.get("model_type", "ols")]
            if isinstance(methods, str):
                methods = [methods]
            bm_tests = {}
            for label, sub_df in [("high", high_df), ("low", low_df)]:
                if len(sub_df) < 30:
                    continue
                mt_results = {}
                for mt in methods:
                    bm_merged["model_type"] = mt
                    try:
                        entry = get_model_runner(mt)
                        if not entry:
                            continue
                        _, runner = entry
                        mt_results[mt] = runner(sub_df, bm_merged)
                    except Exception as e:
                        logger.error(f"[{method_label}][{bm_name}][{label}][{mt}] 失败: {e}")
                        mt_results[mt] = {"model_name": mt, "error": str(e)}
                if mt_results:
                    bm_tests[f"{group_var}_{label}"] = mt_results
            if bm_tests:
                tests[bm_name] = bm_tests
        return {
            "method": "median_split",
            "method_label": method_label,
            "group_var": group_var,
            "median": float(median_val) if pd.notna(median_val) else None,
            "tests": tests,
            "count": sum(len(v) for v in tests.values()),
        }

    def _het_interaction_multi(self, df, sub_params, group_var, method_label, applied_baselines):
        """交互项模型：多 baseline"""
        if group_var not in df.columns:
            return {
                "method": "interaction",
                "method_label": method_label,
                "group_var": group_var,
                "error": f"调节变量 '{group_var}' 不在数据中",
            }
        tests = {}
        for bm in applied_baselines:
            bm_merged = _merge_baseline_to_params(sub_params, bm)
            bm_name = bm.get("name") or f"baseline{len(tests) + 1}"
            original_independent = list(bm_merged.get("independent_vars") or [])
            if not original_independent:
                continue
            methods = bm.get("regression_methods") or [bm_merged.get("model_type", "ols")]
            if isinstance(methods, str):
                methods = [methods]
            bm_tests = {}
            for mt in methods:
                bm_merged["model_type"] = mt
                entry = get_model_runner(mt)
                if not entry:
                    continue
                _, runner = entry
                interaction_results = {}
                for x_var in original_independent:
                    if x_var not in df.columns:
                        continue
                    interaction_col = f"{x_var}_x_{group_var}"
                    try:
                        df_temp = df.copy()
                        df_temp[interaction_col] = df_temp[x_var] * df_temp[group_var]
                        mod_params = dict(bm_merged)
                        mod_params["independent_vars"] = list(original_independent) + [group_var, interaction_col]
                        interaction_results[x_var] = {
                            "moderator": group_var,
                            "interaction_term": interaction_col,
                            "result": runner(df_temp, mod_params),
                        }
                    except Exception as e:
                        logger.error(f"[{method_label}][{bm_name}][{mt}][{x_var}] 失败: {e}")
                        interaction_results[x_var] = {"moderator": group_var, "error": str(e)}
                if interaction_results:
                    bm_tests[mt] = interaction_results
            if bm_tests:
                tests[bm_name] = bm_tests
        return {
            "method": "interaction",
            "method_label": method_label,
            "group_var": group_var,
            "tests": tests,
            "count": sum(len(v) for v in tests.values()),
        }

    # ==================== 调节效应：多 baseline 版本 ====================
    def _moderation_multi(self, df, moderator, applied_baselines):
        """调节效应：多 baseline（每个 baseline 构建 X×M 交互项）"""
        results = {}
        for bm in applied_baselines:
            bm_merged = _merge_baseline_to_params(
                {"model_type": bm.get("model") or "ols"}, bm
            )
            bm_name = bm.get("name") or f"baseline{len(results) + 1}"
            original_independent = list(bm.get("independent_vars") or [])
            if not original_independent:
                results[bm_name] = {"moderator": moderator, "error": "无解释变量，无法构建交互项"}
                continue
            methods = bm.get("regression_methods") or [bm_merged.get("model_type", "ols")]
            if isinstance(methods, str):
                methods = [methods]
            bm_results = {}
            for mt in methods:
                bm_merged["model_type"] = mt
                entry = get_model_runner(mt)
                if not entry:
                    continue
                _, runner = entry
                interaction_results = {}
                for x_var in original_independent:
                    if x_var not in df.columns or moderator not in df.columns:
                        continue
                    interaction_col = f"{x_var}_x_{moderator}"
                    try:
                        df_temp = df.copy()
                        x_centered = df_temp[x_var] - df_temp[x_var].mean()
                        m_centered = df_temp[moderator] - df_temp[moderator].mean()
                        df_temp[interaction_col] = x_centered * m_centered
                        mod_params = dict(bm_merged)
                        mod_params["independent_vars"] = list(original_independent) + [moderator, interaction_col]
                        interaction_results[x_var] = {
                            "moderator": moderator,
                            "interaction_term": interaction_col,
                            "result": runner(df_temp, mod_params),
                        }
                    except Exception as e:
                        logger.error(f"[moderation][{bm_name}][{mt}][{x_var}] 失败: {e}")
                        interaction_results[x_var] = {"moderator": moderator, "error": str(e)}
                if interaction_results:
                    bm_results[mt] = interaction_results
            if bm_results:
                results[bm_name] = {
                    "moderator": moderator,
                    "methods": bm_results,
                    "count": sum(len(v) for v in bm_results.values()),
                }
            else:
                results[bm_name] = {"moderator": moderator, "error": "未生成有效结果"}
        return results

    def _moderation_analysis(self, df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        调节效应检验：构建交互项进行回归。
        新结构（支持多 baseline）：
          params["moderation_methods"] = [
              {"method": "interaction", "moderator_var": "M", "applied_baseline_models": [...], ...}
          ]
        旧结构（兼容）：params["moderation_var"] + 顶层 independent_vars
        """
        # ====== 新结构：moderation_methods 多 baseline ======
        mod_methods = params.get("moderation_methods") or []
        if mod_methods and isinstance(mod_methods, list):
            results = {"methods": {}, "count": 0}
            for mcfg in mod_methods:
                _mvs = mcfg.get("moderator_vars")
                moderators_list = _mvs if isinstance(_mvs, list) and len(_mvs) > 0 else [mcfg.get("moderator_var") or mcfg.get("moderation_var") or ""]
                for moderator in moderators_list:
                    if not moderator or moderator not in df.columns:
                        results["methods"][f"调节效应({moderator})"] = {
                            "moderator": moderator, "error": f"调节变量 '{moderator}' 不在数据中"
                        }
                        continue
                    applied = mcfg.get("applied_baseline_models") or []
                    if not applied:
                        first_bm = (params.get("baseline_models") or [{}])[0]
                        if first_bm.get("dependent_var"):
                            applied = [first_bm]
                    method_label = f"调节效应({moderator})"
                    baseline_results = self._moderation_multi(df, moderator, applied)
                    results["methods"][method_label] = {
                        "method": "interaction",
                        "method_label": method_label,
                        "moderator": moderator,
                        "baselines": baseline_results,
                        "count": sum(v.get("count", 0) for v in baseline_results.values() if isinstance(v, dict)),
                    }
            results["count"] = sum(
                v.get("count", 0) for v in results["methods"].values() if isinstance(v, dict)
            )
            return results

        # ====== 旧结构（兼容）======
        results = {}
        moderator = params.get("moderation_var", "")
        if not moderator or moderator not in df.columns:
            logger.info(f"未指定有效的调节变量 '{moderator}'，跳过调节效应检验")
            return {"tests": [], "count": 0, "note": "未指定调节变量或调节变量不在数据中"}

        # 复制 params 并添加交互项
        mod_params = dict(params)
        original_independent = list(params.get("independent_vars", []))
        if not original_independent:
            return {"tests": [], "count": 0, "note": "无解释变量，无法构建交互项"}

        # 对每个解释变量构建交互项：X * M
        interaction_results = {}
        for x_var in original_independent:
            if x_var not in df.columns or moderator not in df.columns:
                continue
            # 构建交互项列名
            interaction_col = f"{x_var}_x_{moderator}"
            try:
                df_temp = df.copy()
                # 中心化处理
                x_centered = df_temp[x_var] - df_temp[x_var].mean()
                m_centered = df_temp[moderator] - df_temp[moderator].mean()
                df_temp[interaction_col] = x_centered * m_centered

                # 将交互项加入独立变量
                mod_vars = list(original_independent) + [moderator, interaction_col]
                mod_params["independent_vars"] = mod_vars

                # 运行回归
                entry = get_model_runner(params.get("model_type", "ols"))
                if entry:
                    _, runner = entry
                    result = runner(df_temp, mod_params)
                    interaction_results[x_var] = {
                        "moderator": moderator,
                        "interaction_term": interaction_col,
                        "result": result,
                    }
                    logger.info(f"调节效应检验: {x_var} × {moderator} 完成")
            except Exception as e:
                logger.error(f"调节效应检验 [{x_var} × {moderator}] 失败: {str(e)}")
                interaction_results[x_var] = {"moderator": moderator, "error": str(e)}

        return {"tests": interaction_results, "count": len(interaction_results), "moderator": moderator}

    def _mechanism_test(self, df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        机制检验：支持多种方法（baron_kenny / jiang_ting），每种方法独立变量配置。

        新结构：
        params["mechanism_methods"] = [
            {
                "method": "baron_kenny" | "jiang_ting",
                "mediator_var": "M",
                "dependent_var": "Y",
                "independent_vars": ["X1"],
                "control_vars": [...],
                "fixed_effects": {...},
                "cluster_var": "...",
                "regression_methods": [...],
                "model": "fe"
            },
            ...
        ]
        """
        mech_methods = params.get("mechanism_methods")
        results = {"methods": {}, "count": 0}

        if mech_methods is not None and isinstance(mech_methods, list):
            for mcfg in mech_methods:
                method = mcfg.get("method", "baron_kenny")
                _mvs2 = mcfg.get("mediator_vars")
                mediators_list = _mvs2 if isinstance(_mvs2, list) and len(_mvs2) > 0 else [mcfg.get("mediator_var")]
                method_label_map = {
                    "baron_kenny": "逐步回归法",
                    "jiang_ting": "两步法",
                }
                method_label = method_label_map.get(method, method)

                dep_var = mcfg.get("dependent_var") or (
                    params.get("dependent_vars", [None])[0] if params.get("dependent_vars") else None
                )
                if not dep_var:
                    first_mv = next((m for m in mediators_list if m), "")
                    method_key = f"{method_label}({first_mv})" if first_mv else method_label
                    results["methods"][method_key] = {"method": method, "error": "缺少被解释变量"}
                    continue

                sub_params = {
                    "dependent_vars": [dep_var],
                    "independent_vars": mcfg.get("independent_vars") or [],
                    "control_vars": mcfg.get("control_vars") or [],
                    "fixed_effects": mcfg.get("fixed_effects") or {},
                    "entity_col": mcfg.get("entity_col") or None,
                    "time_col": mcfg.get("time_col") or None,
                    "effect_type": mcfg.get("effect_type") or "fe",
                    "cluster_var": mcfg.get("cluster_var") or None,
                    "model_type": (mcfg.get("regression_methods") or [mcfg.get("model") or "reg"])[0],
                }

                for mediator in mediators_list:
                    if not mediator:
                        continue
                    method_key = f"{method_label}({mediator})"

                    if mediator not in df.columns:
                        results["methods"][method_key] = {
                            "method": method,
                            "mediator": mediator,
                            "error": f"中介变量 '{mediator}' 不在数据中或未指定",
                        }
                        continue

                    # 参与本检验的 baseline models
                    applied_baselines = mcfg.get("applied_baseline_models") or []
                    if not applied_baselines:
                        first_bm = (params.get("baseline_models") or [{}])[0]
                        if first_bm.get("dependent_var"):
                            applied_baselines = [first_bm]

                    # 如果没有 applied_baseline_models，按旧逻辑单次执行；否则对每个 baseline 各执行一次
                    if not applied_baselines:
                        if method == "baron_kenny":
                            res = self._mech_baron_kenny(df, sub_params, mediator, method_label)
                        elif method == "jiang_ting":
                            res = self._mech_jiang_ting(df, sub_params, mediator, method_label)
                        else:
                            res = {"method": method, "error": f"不支持的机制方法: {method}"}
                        results["methods"][method_key] = res
                    else:
                        baselines_res = {}
                        for bm in applied_baselines:
                            bm_merged = _merge_baseline_to_params(sub_params, bm)
                            bm_name = bm.get("name") or f"baseline{len(baselines_res) + 1}"
                            methods = bm.get("regression_methods") or [bm_merged.get("model_type", "ols")]
                            if isinstance(methods, str):
                                methods = [methods]
                            bm_method_res = {}
                            for mt in methods:
                                bm_merged["model_type"] = mt
                                try:
                                    if method == "baron_kenny":
                                        one_res = self._mech_baron_kenny(df, bm_merged, mediator, f"{method_label}-{bm_name}-{mt}")
                                    elif method == "jiang_ting":
                                        one_res = self._mech_jiang_ting(df, bm_merged, mediator, f"{method_label}-{bm_name}-{mt}")
                                    else:
                                        one_res = {"method": method, "error": f"不支持的机制方法: {method}"}
                                    bm_method_res[mt] = one_res
                                except Exception as e:
                                    logger.error(f"[{method_label}][{bm_name}][{mt}] 失败: {e}")
                                    bm_method_res[mt] = {"method": method, "error": str(e)}
                            baselines_res[bm_name] = {"methods": bm_method_res}
                        results["methods"][method_key] = {
                            "method": method,
                            "method_label": method_label,
                            "mediator": mediator,
                            "baselines": baselines_res,
                        }

            results["count"] = len([k for k, v in results["methods"].items() if not v.get("error")])
            return results

        # ====== 旧结构（兼容） ======
        mediator = params.get("mechanism_var", "")
        if not mediator or mediator not in df.columns:
            logger.info(f"未指定有效的机制变量 '{mediator}'，跳过机制检验")
            return {"tests": [], "count": 0, "note": "未指定机制变量或机制变量不在数据中"}

        original_independent = list(params.get("independent_vars", []))
        if not original_independent:
            return {"tests": [], "count": 0, "note": "无解释变量"}

        legacy_results = {}
        for x_var in original_independent:
            if x_var not in df.columns:
                continue
            try:
                step2_vars = [x_var] + params.get("control_vars", [])
                step2_params = dict(params)
                step2_params["independent_vars"] = step2_vars
                step2_params["dependent_vars"] = [mediator]
                entry = get_model_runner(params.get("model_type", "ols"))
                if not entry:
                    continue
                _, runner = entry
                step2_result = runner(df, step2_params)

                step3_vars = [x_var, mediator] + params.get("control_vars", [])
                step3_params = dict(params)
                step3_params["independent_vars"] = step3_vars
                step3_params["dependent_vars"] = params.get("dependent_vars", [])
                step3_result = runner(df, step3_params)

                legacy_results[x_var] = {
                    "mediator": mediator,
                    "step2_X_to_M": step2_result,
                    "step3_X_and_M_to_Y": step3_result,
                }
            except Exception as e:
                legacy_results[x_var] = {"mediator": mediator, "error": str(e)}

        return {"tests": legacy_results, "count": len(legacy_results), "mediator": mediator}

    def _mech_baron_kenny(self, df: pd.DataFrame, sub_params: Dict, mediator: str, method_label: str) -> Dict[str, Any]:
        """
        Baron & Kenny 三步法：
          Step 1: Y = aX + controls       (用户可结合基准回归结果)
          Step 2: M = bX + controls
          Step 3: Y = c'X + dM + controls
        """
        original_independent = list(sub_params.get("independent_vars", []))
        if not original_independent:
            return {
                "method": "baron_kenny",
                "method_label": method_label,
                "mediator": mediator,
                "error": "无解释变量",
            }
        model_type = sub_params.get("model_type", "ols")
        entry = get_model_runner(model_type)
        if not entry:
            return {
                "method": "baron_kenny",
                "method_label": method_label,
                "mediator": mediator,
                "error": f"不支持的模型类型: {model_type}",
            }
        _, runner = entry
        dep_var = sub_params["dependent_vars"][0]
        control_vars = sub_params.get("control_vars", [])

        mech_results = {}
        for x_var in original_independent:
            if x_var not in df.columns or mediator not in df.columns:
                continue
            try:
                # Step 2: M = bX + controls
                # 注意：sub_params 里已经有 control_vars，这里 step2_vars 已经包含了 controls
                # 避免与 control_vars 重复，必须清空 control_vars 字段
                step2_vars = [x_var] + control_vars
                step2_params = dict(sub_params)
                step2_params["independent_vars"] = step2_vars
                step2_params["control_vars"] = []  # 防止变量重复出现在公式
                step2_params["dependent_vars"] = [mediator]
                step2_result = runner(df, step2_params)

                # Step 3: Y = c'X + dM + controls
                step3_vars = [x_var, mediator] + control_vars
                step3_params = dict(sub_params)
                step3_params["independent_vars"] = step3_vars
                step3_params["control_vars"] = []  # 防止变量重复出现在公式
                step3_params["dependent_vars"] = [dep_var]
                step3_result = runner(df, step3_params)

                mech_results[x_var] = {
                    "mediator": mediator,
                    "step2_X_to_M": step2_result,
                    "step3_X_and_M_to_Y": step3_result,
                }
                logger.info(f"[{method_label}] {x_var} → {mediator} → Y 完成")
            except Exception as e:
                logger.error(f"[{method_label}] {x_var} → {mediator} 失败: {str(e)}")
                mech_results[x_var] = {"mediator": mediator, "error": str(e)}

        return {
            "method": "baron_kenny",
            "method_label": method_label,
            "mediator": mediator,
            "tests": mech_results,
            "count": len(mech_results),
        }

    def _mech_jiang_ting(self, df: pd.DataFrame, sub_params: Dict, mediator: str, method_label: str) -> Dict[str, Any]:
        """
        江艇 (2022) 两步法：省略第三步 Y~X+M
          Step 1: M = aX + controls        （核心）
          Step 2: Y = bX + cM + controls   （同时纳入 X 与 M）

        强调"两步"——只跑第一步（M~X）和第二步（Y~X+M），不跑第三步。
        """
        original_independent = list(sub_params.get("independent_vars", []))
        if not original_independent:
            return {
                "method": "jiang_ting",
                "method_label": method_label,
                "mediator": mediator,
                "error": "无解释变量",
            }
        model_type = sub_params.get("model_type", "ols")
        entry = get_model_runner(model_type)
        if not entry:
            return {
                "method": "jiang_ting",
                "method_label": method_label,
                "mediator": mediator,
                "error": f"不支持的模型类型: {model_type}",
            }
        _, runner = entry
        dep_var = sub_params["dependent_vars"][0]
        control_vars = sub_params.get("control_vars", [])

        mech_results = {}
        for x_var in original_independent:
            if x_var not in df.columns or mediator not in df.columns:
                continue
            try:
                # Step 1: M = aX + controls
                # 注意：sub_params 里已经有 control_vars，这里 step1_vars 已经包含了 controls
                # 避免与 control_vars 重复，必须清空 control_vars 字段
                step1_vars = [x_var] + control_vars
                step1_params = dict(sub_params)
                step1_params["independent_vars"] = step1_vars
                step1_params["control_vars"] = []  # 防止变量重复出现在公式
                step1_params["dependent_vars"] = [mediator]
                step1_result = runner(df, step1_params)

                # Step 2: Y = bX + cM + controls
                step2_vars = [x_var, mediator] + control_vars
                step2_params = dict(sub_params)
                step2_params["independent_vars"] = step2_vars
                step2_params["control_vars"] = []  # 防止变量重复出现在公式
                step2_params["dependent_vars"] = [dep_var]
                step2_result = runner(df, step2_params)

                mech_results[x_var] = {
                    "mediator": mediator,
                    "step1_X_to_M": step1_result,
                    "step2_X_and_M_to_Y": step2_result,
                }
                logger.info(f"[{method_label}] 两步法 {x_var} → {mediator} → Y 完成")
            except Exception as e:
                logger.error(f"[{method_label}] 两步法 {x_var} → {mediator} 失败: {str(e)}")
                mech_results[x_var] = {"mediator": mediator, "error": str(e)}

        return {
            "method": "jiang_ting",
            "method_label": method_label,
            "mediator": mediator,
            "tests": mech_results,
            "count": len(mech_results),
        }
