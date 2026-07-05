import pandas as pd
from typing import Dict, Any, List


def escape_var(var_name: str) -> str:
    """
    包裹变量名给 Patsy formula 使用。
    - 纯 ASCII 标识符（字母/数字/下划线，且不以数字开头）：直接返回
    - 其他情况（含中文/空格/特殊字符）：用 Patsy 的 Q("...") 语法
    """
    if not var_name:
        return var_name
    # 判断是否合法 Python 标识符（也即 Patsy 无需 quote 的形式）
    if var_name.isidentifier():
        return var_name
    # 避免双引号转义问题，统一用 Q("...") 包裹
    safe = str(var_name).replace('"', '\\"')
    return f'Q("{safe}")'


def build_formula(dep_var: str, indep_vars: list, control_vars: list = None) -> str:
    rhs = [escape_var(v) for v in indep_vars]
    if control_vars:
        rhs += [escape_var(v) for v in control_vars]
    return f"{escape_var(dep_var)} ~ {' + '.join(rhs)}"


def extract_regression_results(results, model_name: str, fe_info: Dict[str, str] = None, dep_var: str = None, fixed_effects: Dict[str, Any] = None) -> Dict[str, Any]:
    coef_df = results.params.to_frame("coef")

    if hasattr(results, 'std_errors'):
        coef_df["std_err"] = results.std_errors
    elif hasattr(results, 'bse'):
        coef_df["std_err"] = results.bse
    else:
        coef_df["std_err"] = None

    if hasattr(results, 'tstats'):
        coef_df["t_value"] = results.tstats
    elif hasattr(results, 'tvalues'):
        coef_df["t_value"] = results.tvalues
    else:
        coef_df["t_value"] = None

    if hasattr(results, 'pvalues'):
        coef_df["p_value"] = results.pvalues
    else:
        coef_df["p_value"] = None

    def get_significance(p):
        if p is None:
            return ""
        if p < 0.01:
            return "***"
        elif p < 0.05:
            return "**"
        elif p < 0.1:
            return "*"
        else:
            return ""

    coef_df["significance"] = coef_df["p_value"].apply(get_significance)

    model_stats = {
        "r_squared": results.rsquared if hasattr(results, 'rsquared') else (
            results.rsquared_included if hasattr(results, 'rsquared_included') else None),
        "adj_r_squared": results.rsquared_adj if hasattr(results, 'rsquared_adj') else None,
        "f_statistic": results.fvalue if hasattr(results, 'fvalue') else None,
        "f_pvalue": results.f_pvalue if hasattr(results, 'f_pvalue') else None,
        "log_likelihood": results.llf if hasattr(results, 'llf') else None,
        "aic": results.aic if hasattr(results, 'aic') else None,
        "bic": results.bic if hasattr(results, 'bic') else None,
        "n_obs": results.nobs if hasattr(results, 'nobs') else (
            results.df_model[0] if hasattr(results, 'df_model') else None)
    }

    # 存储固定效应信息（按用户传入的 fixed_effects 字典的 key 直接作为 FE 项）
    fe_info = _normalize_fe_info(fixed_effects) if fe_info is None else fe_info
    if fe_info:
        model_stats["fe_info"] = fe_info

    # 清理 Q("...") 包裹的变量名 → 还原为原始变量名
    def clean_var_name(name):
        if not isinstance(name, str):
            return name
        if name.startswith('Q("') and name.endswith('")'):
            return name[3:-2]
        return name

    # 把 index 转换回字符串并清理
    coef_df.index = [clean_var_name(str(idx)) for idx in coef_df.index]
    # 把 columns 也清理一遍（理论上不变）
    coef_df.columns = [clean_var_name(str(c)) for c in coef_df.columns]

    return {
        "model_name": model_name,
        "dependent_var": dep_var,
        "coefficients": coef_df.to_dict('index'),
        "model_stats": model_stats,
        "summary": _safe_summary(results),
    }


def _safe_summary(results) -> str:
    """安全地获取回归结果的 summary 文本，支持 statsmodels 和 linearmodels"""
    try:
        # 优先尝试 statsmodels 风格: results.summary.as_text()
        summary_attr = getattr(results, "summary", None)
        if summary_attr is None:
            return str(results)
        # callable -> 调用
        if callable(summary_attr):
            s = summary_attr()
        else:
            s = summary_attr
        # 字符串 -> 直接返回
        if isinstance(s, str):
            return s
        # 有 as_text 方法 (statsmodels)
        if hasattr(s, "as_text"):
            return s.as_text()
        # 本身就是 Summary 对象 -> str()
        return str(s)
    except Exception as e:
        return f"（summary 生成失败: {e}）"


def _normalize_fe_info(fixed_effects):
    """
    把用户传入的 fixed_effects (例如 {"stkid": "true", "year": "true"})
    转为 fe_info 字典: {key: bool, ...}
    """
    out = {}
    if not isinstance(fixed_effects, dict):
        return out
    for k, v in fixed_effects.items():
        if isinstance(v, str) and v.lower() in ('true', '1', 'yes', '是'):
            out[k] = True
        elif v is True or v == 1:
            out[k] = True
        else:
            out[k] = False
    return out


def get_user_selected_fe(fixed_effects: Dict[str, Any]) -> List[str]:
    """
    从用户传入的 fixed_effects 字典中提取**用户实际选中的固定效应列名**（按传入顺序）。

    支持两种结构：
      新结构（新前端传入）：{"Year": "true", "Stkcd": "true"}   → 提取 ["Year", "Stkcd"]
      旧结构（命令解析器）：{"individual": "Stkcd", "time": "Year"} → 提取 ["Stkcd", "Year"]

    返回的列名顺序与用户在前端勾选/输入的顺序保持一致。
    后续的回归器直接用这些列构建虚拟变量（LSDV），不再区分 entity/time。
    """
    if not fixed_effects or not isinstance(fixed_effects, dict):
        return []

    # 旧结构优先（如果存在 individual/time 字段）
    legacy_individual = fixed_effects.get("individual")
    legacy_time = fixed_effects.get("time")
    if legacy_individual or legacy_time:
        out = []
        if isinstance(legacy_individual, str) and legacy_individual:
            out.append(legacy_individual)
        if isinstance(legacy_time, str) and legacy_time:
            out.append(legacy_time)
        return out

    # 新结构：抽取所有 value == true 的 key（保持 dict 插入顺序）
    true_keys = []
    for k, v in fixed_effects.items():
        if (isinstance(v, str) and v.lower() in ('true', '1', 'yes', '是')) or v is True or v == 1:
            true_keys.append(k)
    return true_keys


def detect_panel_vars(df: pd.DataFrame, fixed_effects: Dict[str, str] = None):
    """
    从 fixed_effects 配置中检测面板变量（个体和时间）
    
    支持两种格式：
    1. 旧格式：{"individual": "列名", "time": "列名"}
    2. 新格式：{"列名": "true", "列名": "true"}
    
    参数:
        df: 数据框
        fixed_effects: 固定效应配置
    
    返回:
        (entity_var, time_var) 元组
    """
    if fixed_effects is None:
        fixed_effects = {}
    
    # 先尝试旧格式
    entity_var = fixed_effects.get("individual", "")
    time_var = fixed_effects.get("time", "")
    
    entity_var = entity_var if entity_var and entity_var in df.columns else None
    time_var = time_var if time_var and time_var in df.columns else None
    
    # 如果旧格式没有，尝试新格式
    if not entity_var and not time_var:
        # 提取所有 value == "true" 的列
        selected_cols = []
        for col, val in fixed_effects.items():
            if isinstance(val, str) and val.lower() in ('true', '1', 'yes', '是'):
                selected_cols.append(col)
            elif val is True or val == 1:
                selected_cols.append(col)
        
        # 智能识别个体和时间变量
        time_keywords = ["年度", "年份", "时间", "year", "date", "日期", "月份", "季度"]
        entity_keywords = ["企业代码", "公司代码", "股票代码", "证券代码", 
                          "entity_id", "firm_id", "company_id", "company", "firm",
                          "企业编号", "公司编号", "股票编号"]
        
        for col in selected_cols:
            # 检查是否是时间变量
            if any(kw in col for kw in time_keywords):
                time_var = col
            # 检查是否是个体变量
            elif any(kw in col for kw in entity_keywords):
                entity_var = col
        
        # 如果还没识别出来，用基数判断
        if not time_var and not entity_var and len(selected_cols) >= 2:
            # 唯一值少的作为时间变量，多的作为个体变量
            nunique = [(col, df[col].nunique()) for col in selected_cols if col in df.columns]
            nunique.sort(key=lambda x: x[1])
            if len(nunique) >= 2:
                time_var = nunique[0][0]
                entity_var = nunique[-1][0]
        elif not time_var and len(selected_cols) == 1:
            # 只有一个变量，判断是时间还是个体
            col = selected_cols[0]
            nunique = df[col].nunique()
            if nunique <= 50:  # 时间变量通常唯一值较少
                time_var = col
            else:
                entity_var = col
    
    # 最终兜底：使用预设关键词
    if not entity_var and not time_var:
        possible_entity = ["企业代码", "公司代码", "股票代码", "证券代码",
                          "entity_id", "firm_id", "company_id", "company", "firm",
                          "企业编号", "公司编号", "股票编号"]
        possible_time = ["年度", "年份", "时间", "year", "date", "日期"]
        
        for col in possible_entity:
            if col in df.columns:
                entity_var = col
                break
        for col in possible_time:
            if col in df.columns:
                time_var = col
                break
    
    return entity_var, time_var
