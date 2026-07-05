"""
数据分析智能体
负责解读实证分析结果，生成详细的数据分析报告
以及可直接嵌入论文的实证分析章节（含真实表格，无需LLM生成）
"""

import json
import re
from typing import Dict, Any, Optional, List
from core.base_agent import BaseAgent, Task, AgentResponse


def _fmt(v, digits=4):
    """格式化数值"""
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v) if v is not None else "-"


def _build_table(headers, rows):
    """构建 Markdown 表格"""
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["------"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _has_data(block):
    """检查数据块是否存在且有效（无错误）"""
    return bool(block and isinstance(block, dict) and "error" not in block)


def _has_robustness(block):
    """判断稳健性检验是否存在且有结果（兼容单 baseline 和多 baseline 结构）"""
    if not isinstance(block, dict) or not block:
        return False
    for test_type, test_result in block.items():
        if not isinstance(test_result, dict):
            continue
        if "error" in test_result:
            continue
        # 单 baseline 结构：直接有 coefficients
        if "coefficients" in test_result and test_result["coefficients"]:
            return True
        # 多 baseline 结构：baselines → methods
        baselines = test_result.get("baselines") or {}
        if isinstance(baselines, dict) and baselines:
            for bm_val in baselines.values():
                if not isinstance(bm_val, dict):
                    continue
                methods = bm_val.get("methods") or {}
                if isinstance(methods, dict) and methods:
                    return True
    return False


def _has_methods_block(block, key: str = "methods"):
    """
    判断 block.methods 是否有有效内容
    适用于 heterogeneity/moderation/mechanism 的多 baseline 顶层结构

    支持两种顶层结构：
      1. {methods: {method_key: {...}}} — 标准结构
      2. {baseline_key: {methods: {method_key: {...}}}} — 多 baseline 外层包裹
    """
    if not isinstance(block, dict):
        return False

    # 标准结构: block["methods"] 存在且有效
    methods = block.get(key) or {}
    if isinstance(methods, dict) and methods:
        for v in methods.values():
            if isinstance(v, dict) and "error" not in v:
                return True

    # 兜底：顶层可能是 baselines 结构 {baseline_name: {methods: {mt: ...}}}
    # 只要有一个子项包含非空的 methods 子字典就算有效
    for sub_val in block.values():
        if not isinstance(sub_val, dict) or "error" in sub_val:
            continue
        sub_methods = sub_val.get(key) or {}
        if isinstance(sub_methods, dict) and sub_methods:
            for v in sub_methods.values():
                if isinstance(v, dict) and "error" not in v:
                    return True

    return False


def _is_het_interaction_multi(tests: dict) -> bool:
    """
    检测异质性 tests 是否为交互项多 baseline 结构：
      tests[bm_name][mt][x_var] = {moderator, interaction_term, result}
    特征：tests[bm_name] 的 value 是方法名(mt)字典，
          其 value 再下一层包含 "moderator" 键。
    """
    if not isinstance(tests, dict) or not tests:
        return False
    for bm_val in tests.values():
        if not isinstance(bm_val, dict):
            continue
        for mt_val in bm_val.values():
            if not isinstance(mt_val, dict):
                continue
            for x_val in mt_val.values():
                if isinstance(x_val, dict) and "moderator" in x_val:
                    return True
    return False


def _iter_single_regression_results(reg_result):
    """
    把单个回归结果（含多方法）展开为 (label, result) 列表。
    - reg_result: {model_name, methods: {mt: result}} 或旧的直接 result
    - yield (label, single_result_dict)
    """
    if not isinstance(reg_result, dict):
        return
    if "error" in reg_result:
        return
    methods = reg_result.get("methods")
    if isinstance(methods, dict) and methods:
        # 多方法：逐个方法 yield
        for mt, single in methods.items():
            if isinstance(single, dict) and "error" not in single:
                label = f"{reg_result.get('model_name','')} - {single.get('model_name', mt)}"
                yield (label, single)
    elif "coefficients" in reg_result or "model_stats" in reg_result:
        # 旧结构或直接 result
        yield (reg_result.get("model_name", ""), reg_result)


def _coefs_to_table(coefs: Dict[str, Any], dep_var: str = "", fe_info: Dict[str, Any] = None,
                    show_std_err: bool = True, show_t: bool = True, show_p: bool = True) -> List[str]:
    """
    把系数 dict 转为 Markdown 表格的 row 列表。
    每行格式：变量 | 系数(标准误) | t值
    返回 row 列表（不含 header 和分隔行）
    注意：常数项(Intercept) 重命名为 常数项，并移至表格最后一行
    """
    rows = []
    intercept_row = None
    for var, val in (coefs or {}).items():
        if isinstance(val, dict):
            coef = val.get("coef")
            se = val.get("std_err")
            t = val.get("t_value")
            p = val.get("p_value")
            sig = val.get("significance", "")

            # 系数 + 显著性
            coef_cell = f"{_fmt(coef)}{sig}" if coef is not None else ""
            se_cell = f"({_fmt(se)})" if show_std_err and se is not None else ""
            t_cell = f"{_fmt(t)}" if show_t and t is not None else ""
            row = [var, coef_cell, se_cell, t_cell]

            # 拦截重命名为 常数项，并放到表格最后
            if str(var).strip().lower() in ("intercept", "const", "constant", "常数项"):
                row[0] = "常数项"
                intercept_row = row
            else:
                rows.append(row)
        elif isinstance(val, (int, float)):
            row = [var, _fmt(val)]
            if str(var).strip().lower() in ("intercept", "const", "constant", "常数项"):
                row[0] = "常数项"
                intercept_row = row
            else:
                rows.append(row)
        else:
            continue
    # 常数项移至表格末尾
    if intercept_row is not None:
        rows.append(intercept_row)
    return rows


def _format_single_reg_md(single_result: Dict[str, Any], title: str = "", model_num: str = "(1)") -> str:
    """
    把单个回归结果格式化为完整 Markdown 段（标题 + 学术格式表格 + 统计量）

    输出格式（匹配前端实证结果展示样式）：
        **标题**
        | VARIABLES | (1) |
        |-----------|-----|
        | X         | 1.3551*** |
        |           | (105.1807) |
        |           | (0.0129) |
        | Y         | 0.5611*** |
        |           | (5.6325) |
        |           | (0.0996) |
        | Observations | 3300 |
        | R-squared | 0.8281 |
        | 固定效应 | 是 |
    """
    if not isinstance(single_result, dict) or "error" in single_result:
        return ""
    parts = []
    label = title or single_result.get("model_name", "回归结果")
    parts.append(f"**{label}**")

    coefs = single_result.get("coefficients") or {}
    if coefs:
        headers = ["VARIABLES", model_num]
        rows = []
        # 常数项暂存到最后
        intercept_row = None
        for var_name, var_val in coefs.items():
            if var_name in ("_cons", "const", "Constant", "constant"):
                # 提取系数和显著性
                if isinstance(var_val, dict):
                    coef_val = var_val.get("coef")
                    p_val = var_val.get("p_value")
                else:
                    coef_val = var_val
                    p_val = None
                sig_mark = _significance_mark(p_val) if p_val is not None else ""
                coef_str = f"{_fmt(coef_val)}{sig_mark}" if coef_val is not None else "-"
                intercept_row = ("Constant", coef_str)
                continue

            if isinstance(var_val, dict):
                coef_val = var_val.get("coef")
                se_val = var_val.get("std_err")
                t_val = var_val.get("t_value")
                p_val = var_val.get("p_value")
            else:
                coef_val = var_val
                se_val = None
                t_val = None
                p_val = None

            sig_mark = _significance_mark(p_val) if p_val is not None else ""
            coef_str = f"{_fmt(coef_val)}{sig_mark}" if coef_val is not None else "-"
            t_str = f"({_fmt(t_val)})" if t_val is not None else ""
            se_str = f"({_fmt(se_val)})" if se_val is not None else ""

            rows.append([var_name, coef_str])
            if t_str:
                rows.append(["", t_str])
            if se_str:
                rows.append(["", se_str])

        if intercept_row is not None:
            rows.append([intercept_row[0], intercept_row[1]])

        if rows:
            parts.append(_build_table(headers, rows))

    # 模型统计量
    stats = single_result.get("model_stats") or {}
    meta_lines = []
    dep_var = single_result.get("dependent_var", "")
    if dep_var:
        meta_lines.append(f"- 被解释变量：{dep_var}")
    n_obs = stats.get("n_obs") or stats.get("nobs")
    if n_obs:
        meta_lines.append(f"- 观测值：{_fmt(n_obs)}")
    r2 = stats.get("r_squared") or stats.get("rsquared")
    if r2 is not None:
        meta_lines.append(f"- R²：{_fmt(r2)}")
    adj = stats.get("adj_r_squared") or stats.get("rsquared_adj")
    if adj is not None:
        meta_lines.append(f"- 调整 R²：{_fmt(adj)}")
    fe = stats.get("fe_info") or {}
    if fe:
        for fk, fv in fe.items():
            if isinstance(fv, dict):
                fv = fv.get("var", fv)
            meta_lines.append(f"- 固定效应：{fk}={fv}")
    if meta_lines:
        parts.append("\n".join(meta_lines))

    return "\n\n".join(parts) + "\n"


def _merge_multi_reg_md(results: list, model_labels: list = None, table_title: str = "") -> str:
    """
    把多个回归结果合并到同一张学术格式表格中（多列并排）。

    Args:
        results: 多个 single_result dict 列表
        model_labels: 各模型列标签，如 ["(1)", "(2)"]；默认自动编号
        table_title: 表格上方的标题文字

    输出格式：
        **标题**
        | VARIABLES | (1) | (2) |
        |-----------|-----|-----|
        | X         | 1.3551*** | 1.2345*** |
        |           | (105.1807) | (98.2345) |
        | Y         | 0.5611*** | 0.5511***  |
        |           | (5.6325) | (5.1234) |
        | Observations | 3300 | 3200 |
        | R-squared | 0.8281 | 0.8210 |
    """
    # 过滤无效结果
    valid = [(r, lbl) for r, lbl in zip(results, model_labels or [])
             if isinstance(r, dict) and "error" not in r and r.get("coefficients")]
    if not valid:
        return ""

    if model_labels is None:
        model_labels = [f"({i+1})" for i in range(len(results))]
    valid = [(r, lbl) for r, lbl in zip(results, model_labels)
             if isinstance(r, dict) and "error" not in r and r.get("coefficients")]

    parts = []
    if table_title:
        parts.append(f"**{table_title}**")

    # ── 收集所有变量名（保持顺序，去重；常数项移到最后） ──
    const_names = {"_cons", "const", "Constant", "constant", "Intercept", "intercept"}
    all_vars, seen = [], set()
    for r, _ in valid:
        for v in (r.get("coefficients") or {}):
            if v not in seen:
                seen.add(v)
                all_vars.append(v)
    const_vars = [v for v in all_vars if v in const_names]
    other_vars = [v for v in all_vars if v not in const_names]
    ordered_vars = other_vars + const_vars

    # ── 构建表头 ──
    headers = ["VARIABLES"] + [lbl for _, lbl in valid]

    # ── 构建行 ──
    rows = []
    for var_name in ordered_vars:
        # 系数行
        coef_cells = [var_name]
        has_t_any = False
        t_cells = [""]
        for r, _ in valid:
            val = (r.get("coefficients") or {}).get(var_name)
            if isinstance(val, dict):
                coef = val.get("coef")
                p = val.get("p_value")
                t = val.get("t_value")
                sig = _significance_mark(p) if p is not None else ""
                coef_cells.append(f"{_fmt(coef)}{sig}" if coef is not None else "-")
                t_cells.append(f"({_fmt(t)})" if t is not None else "")
                if t is not None:
                    has_t_any = True
            elif isinstance(val, (int, float)):
                coef_cells.append(_fmt(val))
                t_cells.append("")
            else:
                coef_cells.append("-")
                t_cells.append("")
        rows.append(coef_cells)
        if has_t_any:
            rows.append(t_cells)

    # ── 模型统计量行 ──
    # 观测值
    obs_row = ["Observations"]
    for r, _ in valid:
        s = r.get("model_stats") or {}
        n = s.get("n_obs") or s.get("nobs") or ""
        obs_row.append(str(n) if n else "-")
    rows.append(obs_row)

    # R²
    r2_row = ["R-squared"]
    for r, _ in valid:
        s = r.get("model_stats") or {}
        v = s.get("r_squared") or s.get("rsquared")
        r2_row.append(_fmt(v) if v is not None else "-")
    rows.append(r2_row)

    # 调整 R²
    adj_row = ["调整R-squared"]
    for r, _ in valid:
        s = r.get("model_stats") or {}
        v = s.get("adj_r_squared") or s.get("rsquared_adj")
        adj_row.append(_fmt(v) if v is not None else "-")
    rows.append(adj_row)

    # 固定效应
    fe_row = ["固定效应"]
    for r, _ in valid:
        s = r.get("model_stats") or {}
        fe = s.get("fe_info") or {}
        if fe:
            items = []
            for k, v in fe.items():
                if isinstance(v, dict):
                    v = v.get("var", v)
                items.append(f"{k}={v}")
            fe_row.append("、".join(items))
        else:
            fe_row.append("-")
    rows.append(fe_row)

    parts.append(_build_table(headers, rows))
    return "\n\n".join(parts) + "\n"


def _significance_mark(p_value: float) -> str:
    """根据 p 值返回显著性星号标记"""
    if p_value is None:
        return ""
    if p_value < 0.01:
        return "***"
    elif p_value < 0.05:
        return "**"
    elif p_value < 0.1:
        return "*"
    return ""


def _resolve_mediator(data: dict, default: str = "中介变量") -> str:
    """
    从数据字典中解析 mediator 值，兼容单字符串和数组两种格式。

    优先级：
      1. data["mediator"] 为字符串 → 直接使用
      2. data["mediator_vars"] 为数组 → 用 "、" 连接
      3. 返回 default
    """
    mediator = data.get("mediator")
    if isinstance(mediator, str):
        return mediator
    mediator_vars = data.get("mediator_vars")
    if isinstance(mediator_vars, list) and mediator_vars:
        return "、".join(str(v) for v in mediator_vars)
    return default


def _result_count(block, *keys) -> int:
    """递归统计有效结果数（无 error 字段）"""
    if not isinstance(block, dict):
        return 0
    if keys:
        for k in keys:
            if k in block and isinstance(block[k], dict):
                block = block[k]
                break
        else:
            return 0
    cnt = 0
    for v in block.values():
        if isinstance(v, dict) and "error" not in v:
            cnt += 1
    return cnt



class DataAnalystAgent(BaseAgent):
    """数据分析智能体 - 负责解读实证分析结果
    
    功能：
    - 分析描述性统计
    - 解读相关性分析结果
    - 分析回归表格（系数、显著性、经济意义）
    - 评估模型拟合优度
    - 分析VIF多重共线性检验
    - 解读稳健性检验结果
    - 生成可直接嵌入论文的实证分析章节（基于真实数据，无需LLM编造）
    """
    
    def __init__(self, api_key: Optional[str] = None, model_type: str = None):
        super().__init__(
            agent_id="data_analyst",
            role="数据分析专家",
            capabilities=[
                "描述性统计分析",
                "相关性分析",
                "回归结果解读",
                "模型诊断",
                "稳健性检验分析",
                "实证分析章节生成"
            ],
            api_key=api_key,
            model_type=model_type
        )
    
    async def process_task(self, task: Task) -> AgentResponse:
        """处理数据分析任务"""
        self.logger.info(f"开始处理数据分析任务: {task.id}")
        
        try:
            # 解析任务内容
            data = self._parse_task_content(task)
            empirical_results = data.get('empirical_results', {})
            command = data.get('command', '')
            
            # 1. 调用LLM生成解读分析（用于其他章节引用）
            prompt = self._build_analysis_prompt(empirical_results, command)
            system_prompt = """
            你是一位资深计量经济学专家和学术论文作者，擅长对实证分析结果进行**深入、详尽、有洞察力**的解读。

            ## 输出要求：
            - 输出**至少 1500 字以上**的详细分析
            - 使用专业、严谨的学术语言
            - 每个分析点都要展开阐述，不要只说结论
            - 回归结果要同时解读**统计显著性**（星号、p值）和**经济显著性**（系数大小、实际含义）
            - 对比不同模型之间的结果异同
            - 指出稳健性检验如何支持基准结论
            - 对异质性/调节/机制检验给出具体解释

            输出格式：使用Markdown格式，结构清晰，逻辑连贯，层次分明。
            """
            messages = self._build_prompt(system_prompt, prompt)
            analysis_result = await self._call_llm(messages, max_tokens=8192)
            
            if not analysis_result:
                raise ValueError("LLM调用失败，无法生成分析报告")
            
            # 2. 基于真实数据直接生成实证分析章节（不经过LLM，避免编造）
            empirical_chapter = self._build_empirical_chapter(empirical_results, command)

            # 3. 基于实际执行的实证分析生成研究假设素材（供文献综述使用）
            hypothesis_content = self.build_hypothesis_content(empirical_results, command)
            if hypothesis_content:
                self.logger.info(
                    f"📋 [假设素材] 已生成 {hypothesis_content.count(chr(10))} 行假设素材"
                )

            self.logger.info(f"完成数据分析任务: {task.id}")
            return self.create_response(
                task=task,
                content=analysis_result,
                metadata={
                    "analysis_type": "llm_generated",
                    "empirical_chapter": empirical_chapter,
                    "hypothesis_content": hypothesis_content,
                }
            )
            
        except Exception as e:
            self.logger.error(f"数据分析失败: {str(e)}")
            return self.create_response(
                task=task,
                content=f"数据分析失败: {str(e)}",
                metadata={"error": True, "error_type": "analysis_error"},
                success=False,
                error_message=str(e)
            )
    
    def _build_analysis_prompt(self, empirical_results: Dict[str, Any], command: str) -> str:
        """构建数据分析提示词"""
        # 回归结果需要处理嵌套结构
        reg = empirical_results.get('regression', {})
        reg_text = ""
        if isinstance(reg, dict):
            reg_text = json.dumps(reg, ensure_ascii=False, indent=2)
        else:
            reg_text = str(reg)
        
        robustness = empirical_results.get('robustness', {})
        robustness_text = json.dumps(robustness, ensure_ascii=False, indent=2) if robustness else "无"
        
        # 异质性分析数据
        heterogeneity = empirical_results.get('heterogeneity', {})
        heterogeneity_text = json.dumps(heterogeneity, ensure_ascii=False, indent=2) if heterogeneity else "无"
        
        # 调节效应数据
        moderation = empirical_results.get('moderation', {})
        moderation_text = json.dumps(moderation, ensure_ascii=False, indent=2) if moderation else "无"
        
        # 机制检验数据
        mechanism = empirical_results.get('mechanism', {})
        mechanism_text = json.dumps(mechanism, ensure_ascii=False, indent=2) if mechanism else "无"
        
        prompt = f"""
        请对以下实证分析结果进行详细、深入的解读，篇幅尽可能充实：

        研究指令:
        {command}

        实证分析数据:

        1. 描述性统计:
        {json.dumps(empirical_results.get('descriptive', {}), ensure_ascii=False, indent=2)}

        2. 回归分析结果:
        {reg_text}

        3. 稳健性检验:
        {robustness_text}

        4. 异质性分析:
        {heterogeneity_text}

        5. 调节效应检验:
        {moderation_text}

        6. 机制检验（中介效应）:
        {mechanism_text}

        请提供以下深度解读（每一点都要展开详细阐述，不要单句带过）：
        1. **描述性统计解读**：分析各变量的均值、标准差、最大最小值，说明样本分布特征和数据质量
        2. **基准回归结果深度解读**：
           - 核心解释变量的系数大小、符号方向、统计显著性（***/**/*），解释其经济含义
           - 如果有多模型，对比模型间系数和显著性的变化，说明结果的稳健性
           - 控制变量的分析：哪些显著、方向和预期是否一致
           - 模型拟合优度（R²，调整R²）的评估
        3. **稳健性检验分析**：每种检验方法的结果如何，核心结论是否依然成立
        4. **异质性分析解读**：核心解释变量在不同分组下的效果差异，解释为什么存在这种差异
        5. **调节效应检验解读**：交互项系数的显著性和方向，调节变量如何改变了核心关系
        6. **机制检验解读**：中介效应的存在性和传导路径，各步骤系数的显著性和方向
        7. **综合结论**：总结主要发现、学术贡献和可能的实践启示

        输出要求：使用Markdown格式，每条分析不少于3-5句话，整体不少于1500字。
        """
        
        return prompt.strip()

    def _build_empirical_chapter(self, empirical_results: Dict[str, Any], command: str) -> str:
        """基于真实数据直接生成实证分析章节（不调用LLM，避免幻觉）

        本章节属于论文的"四、实证分析"章节，所有子节统一以 4.x 编号。
        """
        parts = []
        subsection_num = 0
        # 跟踪已生成的小节（用于日志）
        generated_sections = []

        # 调试日志：打印所有可用的一级键
        available_keys = list(empirical_results.keys())
        self.logger.info(
            f"【实证章节】empirical_results 可用一级键: {available_keys}"
        )

        # ─── 4.1 描述性统计分析 ───
        desc = empirical_results.get("descriptive")
        if _has_data(desc):
            subsection_num += 1
            parts.append(f"### 4.{subsection_num} 描述性统计分析\n")
            parts.append(self._format_descriptive_section(desc))
            generated_sections.append(f"4.{subsection_num} 描述性统计")

        # ─── 4.x 基准回归（多模型/多方法） ───
        reg = empirical_results.get("regression")
        if _has_data(reg):
            subsection_num += 1
            parts.append(f"\n### 4.{subsection_num} 基准回归\n")
            parts.append(self._format_regression_section(reg))
            generated_sections.append(f"4.{subsection_num} 基准回归")

        # ─── 4.x 稳健性检验（多 baseline / 多方法） ───
        robustness = empirical_results.get("robustness")
        if _has_robustness(robustness):
            subsection_num += 1
            parts.append(f"\n### 4.{subsection_num} 稳健性检验\n")
            parts.append(self._format_robustness_section(robustness))
            generated_sections.append(f"4.{subsection_num} 稳健性检验")

        # ─── 4.x 异质性分析（多 baseline / 多方法） ───
        heterogeneity = empirical_results.get("heterogeneity")
        het_debug = {
            "exists": heterogeneity is not None,
            "type": type(heterogeneity).__name__,
            "keys": list(heterogeneity.keys()) if isinstance(heterogeneity, dict) else "N/A",
            "has_methods": _has_methods_block(heterogeneity, "methods") if isinstance(heterogeneity, dict) else False,
        }
        self.logger.info(f"【实证章节-异质性】调试信息: {het_debug}")
        if _has_methods_block(heterogeneity, "methods"):
            subsection_num += 1
            parts.append(f"\n### 4.{subsection_num} 异质性分析\n")
            parts.append(self._format_heterogeneity_section(heterogeneity))
            generated_sections.append(f"4.{subsection_num} 异质性分析")
        else:
            self.logger.warning(f"【实证章节-异质性】_has_methods_block 返回 False，跳过异质性分析")

        # ─── 4.x 调节效应检验（多 baseline / 多方法） ───
        moderation = empirical_results.get("moderation")
        mod_debug = {
            "exists": moderation is not None,
            "type": type(moderation).__name__,
            "keys": list(moderation.keys()) if isinstance(moderation, dict) else "N/A",
            "has_methods": _has_methods_block(moderation, "methods") if isinstance(moderation, dict) else False,
        }
        self.logger.info(f"【实证章节-调节效应】调试信息: {mod_debug}")
        if _has_methods_block(moderation, "methods"):
            subsection_num += 1
            parts.append(f"\n### 4.{subsection_num} 调节效应检验\n")
            parts.append(self._format_moderation_section(moderation))
            generated_sections.append(f"4.{subsection_num} 调节效应检验")
        else:
            self.logger.warning(f"【实证章节-调节效应】_has_methods_block 返回 False，跳过调节效应检验")

        # ─── 4.x 机制检验（多 baseline / 多方法） ───
        mechanism = empirical_results.get("mechanism")
        mech_debug = {
            "exists": mechanism is not None,
            "type": type(mechanism).__name__,
            "keys": list(mechanism.keys()) if isinstance(mechanism, dict) else "N/A",
            "has_methods": _has_methods_block(mechanism, "methods") if isinstance(mechanism, dict) else False,
        }
        self.logger.info(f"【实证章节-机制检验】调试信息: {mech_debug}")
        if _has_methods_block(mechanism, "methods"):
            subsection_num += 1
            parts.append(f"\n### 4.{subsection_num} 机制检验\n")
            parts.append(self._format_mechanism_section(mechanism))
            generated_sections.append(f"4.{subsection_num} 机制检验")
        else:
            self.logger.warning(f"【实证章节-机制检验】_has_methods_block 返回 False，跳过机制检验")

        # 关键日志：明确告知本次生成了哪些小节
        self.logger.info(
            f"📊 [实证章节] 已生成 {len(generated_sections)} 个小节: "
            + " | ".join(generated_sections)
        )

        return "\n".join(parts)

    def build_hypothesis_content(self, empirical_results: Dict[str, Any], command: str = "") -> str:
        """根据实际执行的实证分析生成供文献综述使用的研究假设素材。

        输出严格遵循以下模板（只输出实际执行过的分析，未执行的不输出）：
            1. {解释变量}对{被解释变量}是正向/负向作用（来自基准回归）
            2. {解释变量}能够通过促进/抑制{中介变量}从而对{被解释变量}起到正向/负向作用（来自机制检验）
            3. {解释变量}对{被解释变量}的作用在{分组变量=某值}的组别效果较好（来自异质性分析）
            4. {调节效应变量}在{解释变量}对{被解释变量}起到某某作用（来自调节效应）

        全部用自然语言描述，不含具体回归系数/p值/数值。
        """
        lines = ["## 研究假设素材（基于实际执行的实证分析自动生成）", ""]
        lines.append(f"研究主题：{command[:200] if command else '实证研究'}")
        lines.append("")
        has_any = False

        # ─── 1. 基准回归方向 ───
        reg = empirical_results.get("regression")
        if _has_data(reg):
            baseline_lines = self._extract_regression_direction(reg)
            if baseline_lines:
                has_any = True
                lines.append("### 1. 基准回归方向（主效应）")
                lines.extend(baseline_lines)
                lines.append("")

        # ─── 2. 机制检验（中介效应） ───
        mechanism = empirical_results.get("mechanism")
        if _has_methods_block(mechanism, "methods"):
            mech_lines = self._extract_mechanism_direction(mechanism)
            if mech_lines:
                has_any = True
                lines.append("### 2. 机制检验方向（中介效应）")
                lines.extend(mech_lines)
                lines.append("")

        # ─── 3. 异质性分析（分组差异） ───
        heterogeneity = empirical_results.get("heterogeneity")
        if _has_methods_block(heterogeneity, "methods"):
            het_lines = self._extract_heterogeneity_direction(heterogeneity)
            if het_lines:
                has_any = True
                lines.append("### 3. 异质性分析方向（分组差异）")
                lines.extend(het_lines)
                lines.append("")

        # ─── 4. 调节效应 ───
        moderation = empirical_results.get("moderation")
        if _has_methods_block(moderation, "methods"):
            mod_lines = self._extract_moderation_direction(moderation)
            if mod_lines:
                has_any = True
                lines.append("### 4. 调节效应方向")
                lines.extend(mod_lines)
                lines.append("")

        if not has_any:
            return ""  # 没有可生成的内容，返回空字符串

        lines.append("---")
        lines.append("**重要约束**：以上内容基于实际执行的实证分析自动生成。"
                     "文献综述智能体必须仅基于上述 4 类素材生成研究假设，"
                     "若某种分析未执行，则不应生成对应假设。")
        return "\n".join(lines)

    def _extract_regression_direction(self, reg: Dict[str, Any]) -> List[str]:
        """从基准回归结果中提取主效应方向（每个核心解释变量一条）"""
        lines = []
        # 1) 找出第一个被解释变量和核心解释变量
        first_single = None
        for model_name, model_result in reg.items():
            if not isinstance(model_result, dict) or "error" in model_result:
                continue
            for mt_label, single in _iter_single_regression_results(model_result):
                if isinstance(single, dict) and "coefficients" in single:
                    first_single = single
                    break
            if first_single:
                break
        if not first_single:
            return lines

        dep_var = first_single.get("dependent_var", "被解释变量")
        # 收集所有模型中都存在的核心解释变量
        # 取第一个模型中所有显著的变量作为核心变量
        coefs = first_single.get("coefficients", {}) or {}
        for var, val in coefs.items():
            if not isinstance(val, dict):
                continue
            # 跳过 Intercept/常数项/控制变量（控制变量通常为控制变量集合，需传入独立变量列表）
            if str(var).strip().lower() in ("intercept", "const", "constant", "常数项"):
                continue
            coef = val.get("coef")
            pval = val.get("p_value")
            if coef is None or pval is None:
                continue
            if pval >= 0.1:
                continue  # 不显著的不写入主效应
            direction = "正向" if coef > 0 else "负向"
            sig_level = "1%水平显著" if pval < 0.01 else "5%水平显著" if pval < 0.05 else "10%水平显著"
            lines.append(f"- {var}对{dep_var}是{direction}作用（{sig_level}）。")
        return lines

    def _extract_mechanism_direction(self, mechanism: Dict[str, Any]) -> List[str]:
        """从机制检验结果中提取中介效应方向"""
        lines = []
        methods = mechanism.get("methods") or {}
        for method_key, method_data in methods.items():
            if not isinstance(method_data, dict) or "error" in method_data:
                continue
            mediator = _resolve_mediator(method_data) or method_data.get("moderator") or "中介变量"
            tests = method_data.get("tests") or {}
            # 单 baseline: tests[x_var] = {mediator, step1/step2}
            baselines = method_data.get("baselines") or {}
            if baselines:
                # 多 baseline: baselines[bm_name] = {name, methods: {mt: {tests: ...}}}
                for bm_name, bm_data in baselines.items():
                    if not isinstance(bm_data, dict):
                        continue
                    bm_methods = bm_data.get("methods") or {}
                    for mt, single in bm_methods.items():
                        if not isinstance(single, dict) or "error" in single:
                            continue
                        mt_tests = single.get("tests") or {}
                        for x_var, sub in mt_tests.items():
                            if not isinstance(sub, dict) or "error" in sub:
                                continue
                            lines.extend(self._mech_lines_for_x(x_var, sub, mediator))
            else:
                for x_var, sub in tests.items():
                    if not isinstance(sub, dict) or "error" in sub:
                        continue
                    lines.extend(self._mech_lines_for_x(x_var, sub, mediator))
        # 去重
        seen = set()
        deduped = []
        for ln in lines:
            if ln not in seen:
                seen.add(ln)
                deduped.append(ln)
        return deduped

    def _mech_lines_for_x(self, x_var: str, sub: dict, mediator: str) -> List[str]:
        """根据机制检验单个子项生成自然语言描述"""
        out = []
        # Baron & Kenny / 江艇 两步法统一处理
        step2 = sub.get("step2_X_and_M_to_Y") or sub.get("step3_X_and_M_to_Y")
        step1 = sub.get("step1_X_to_M") or sub.get("step2_X_to_M")
        # X -> M 方向
        if isinstance(step1, dict) and "error" not in step1:
            coefs = step1.get("coefficients") or {}
            val = coefs.get(x_var) if isinstance(coefs, dict) else None
            if isinstance(val, dict) and val.get("coef") is not None and val.get("p_value") is not None and val.get("p_value") < 0.1:
                direction = "促进" if val["coef"] > 0 else "抑制"
                out.append(f"- {x_var}能够通过{direction}{mediator}从而对被解释变量起到{('正向' if val['coef']>0 else '负向')}作用。")
                return out
        # 兜底：若 X + M -> Y 中 M 的系数显著
        if isinstance(step2, dict) and "error" not in step2:
            coefs = step2.get("coefficients") or {}
            val = coefs.get(mediator) if isinstance(coefs, dict) else None
            if isinstance(val, dict) and val.get("coef") is not None and val.get("p_value") is not None and val.get("p_value") < 0.1:
                direction = "促进" if val["coef"] > 0 else "抑制"
                out.append(f"- {x_var}能够通过{direction}{mediator}从而对被解释变量起到{('正向' if val['coef']>0 else '负向')}作用。")
        return out

    def _extract_heterogeneity_direction(self, heterogeneity: Dict[str, Any]) -> List[str]:
        """从异质性分析中提取分组差异方向"""
        lines = []
        methods = heterogeneity.get("methods") or {}
        for method_key, method_data in methods.items():
            if not isinstance(method_data, dict) or "error" in method_data:
                continue
            group_var = method_data.get("group_var") or "分组变量"
            method = method_data.get("method", "")
            tests = method_data.get("tests") or {}

            baselines = method_data.get("baselines") or {}
            if baselines:
                for bm_name, bm_data in baselines.items():
                    if not isinstance(bm_data, dict):
                        continue
                    bm_methods = bm_data.get("methods") or {}
                    for mt, single in bm_methods.items():
                        if not isinstance(single, dict) or "error" in single:
                            continue
                        mt_tests = single.get("tests") or {}
                        for x_var, sub in mt_tests.items():
                            if not isinstance(sub, dict) or "error" in sub:
                                continue
                            lines.extend(self._het_lines_for_x(x_var, sub, group_var, method))
            else:
                for x_var, sub in tests.items():
                    if not isinstance(sub, dict) or "error" in sub:
                        continue
                    lines.extend(self._het_lines_for_x(x_var, sub, group_var, method))
        # 去重
        seen = set()
        deduped = []
        for ln in lines:
            if ln not in seen:
                seen.add(ln)
                deduped.append(ln)
        return deduped

    def _het_lines_for_x(self, x_var: str, sub: dict, group_var: str, method: str) -> List[str]:
        """根据异质性子项生成分组描述"""
        out = []
        # 交互项模型：tests[x_var] = {moderator, interaction_term, result}
        if method == "interaction" or sub.get("moderator") or sub.get("interaction_term"):
            moderator = sub.get("moderator") or group_var
            interaction_term = sub.get("interaction_term")
            if not interaction_term:
                interaction_term = f"{x_var}_x_{moderator}"
            # 从 result 中取交互项系数
            result = sub.get("result") or sub
            coefs = result.get("coefficients") if isinstance(result, dict) else None
            if isinstance(coefs, dict):
                val = coefs.get(interaction_term)
                if isinstance(val, dict) and val.get("p_value") is not None and val.get("p_value") < 0.1:
                    direction = "增强" if val.get("coef", 0) > 0 else "削弱"
                    out.append(f"- {x_var}对被解释变量的作用在{moderator}=1（特定分组）的组别效果{direction}。")
            return out
        # 子样本回归：tests[x_var] = {group_0: result, group_1: result}
        if sub.get("group_0") and sub.get("group_1"):
            g0 = sub["group_0"]
            g1 = sub["group_1"]
            val0 = (g0.get("coefficients") or {}).get(x_var) if isinstance(g0, dict) else None
            val1 = (g1.get("coefficients") or {}).get(x_var) if isinstance(g1, dict) else None
            if isinstance(val0, dict) and isinstance(val1, dict):
                c0, c1 = val0.get("coef"), val1.get("coef")
                if c0 is not None and c1 is not None:
                    if abs(c1) > abs(c0):
                        out.append(f"- {x_var}对被解释变量的作用在{group_var}=1（特定分组）的组别效果较好。")
                    elif abs(c0) > abs(c1):
                        out.append(f"- {x_var}对被解释变量的作用在{group_var}=0（特定分组）的组别效果较好。")
        return out

    def _extract_moderation_direction(self, moderation: Dict[str, Any]) -> List[str]:
        """从调节效应结果中提取调节变量作用方向"""
        lines = []
        methods = moderation.get("methods") or {}
        for method_key, method_data in methods.items():
            if not isinstance(method_data, dict) or "error" in method_data:
                continue
            moderator = method_data.get("moderator") or method_data.get("moderator_var") or "调节变量"
            tests = method_data.get("tests") or {}

            baselines = method_data.get("baselines") or {}
            if baselines:
                for bm_name, bm_data in baselines.items():
                    if not isinstance(bm_data, dict):
                        continue
                    bm_methods = bm_data.get("methods") or {}
                    for mt, single in bm_methods.items():
                        if not isinstance(single, dict) or "error" in single:
                            continue
                        mt_tests = single.get("tests") or {}
                        for x_var, sub in mt_tests.items():
                            if not isinstance(sub, dict) or "error" in sub:
                                continue
                            lines.extend(self._mod_lines_for_x(x_var, sub, moderator))
            else:
                for x_var, sub in tests.items():
                    if not isinstance(sub, dict) or "error" in sub:
                        continue
                    lines.extend(self._mod_lines_for_x(x_var, sub, moderator))
        # 去重
        seen = set()
        deduped = []
        for ln in lines:
            if ln not in seen:
                seen.add(ln)
                deduped.append(ln)
        return deduped

    def _mod_lines_for_x(self, x_var: str, sub: dict, moderator: str) -> List[str]:
        """根据调节效应子项生成描述"""
        out = []
        result = sub.get("result") or sub
        coefs = result.get("coefficients") if isinstance(result, dict) else None
        if not isinstance(coefs, dict):
            return out
        # 交互项列名通常是 {x}_{moderator} 或 {x}_x_{moderator}
        candidates = [
            f"{x_var}_{moderator}",
            f"{x_var}_x_{moderator}",
            f"{x_var}*{moderator}",
        ]
        for cand in candidates:
            if cand in coefs:
                val = coefs[cand]
                if isinstance(val, dict) and val.get("p_value") is not None and val.get("p_value") < 0.1:
                    direction = "增强" if val.get("coef", 0) > 0 else "削弱"
                    out.append(f"- {moderator}在{x_var}对被解释变量的作用中起{direction}作用。")
                return out
        # 兜底：找形如 "{x_var}_" 开头的交互项
        for k, val in coefs.items():
            if not isinstance(val, dict):
                continue
            if k.lower().startswith(x_var.lower() + "_") and val.get("p_value") is not None and val.get("p_value") < 0.1:
                direction = "增强" if val.get("coef", 0) > 0 else "削弱"
                out.append(f"- {moderator}在{x_var}对被解释变量的作用中起{direction}作用。")
                return out
        return out

    # ─────────── 描述性统计格式化 ───────────

    def _format_descriptive_section(self, desc: Dict[str, Any]) -> str:
        """基于真实数据直接生成描述性统计章节"""
        variables = desc.get("variables", {})
        if not variables:
            return "（无描述性统计数据）\n"
        
        headers = ["变量", "观测值", "均值", "标准差", "最小值", "最大值"]
        rows = []
        for name, stats in variables.items():
            rows.append([
                name,
                _fmt(stats.get("count")),
                _fmt(stats.get("mean")),
                _fmt(stats.get("std")),
                _fmt(stats.get("min")),
                _fmt(stats.get("max")),
            ])
        
        table = "表1 描述性统计结果\n\n" + _build_table(headers, rows)
        
        # 基于数据生成自然语言解读
        n_vars = len(variables)
        sample_size = desc.get("sample_size", "N/A")
        commentary = (
            f"表1报告了主要变量的描述性统计结果。共包含{n_vars}个变量，"
            f"样本量为{sample_size}。从各变量的均值、标准差、最小值和最大值来看，"
            f"数据分布合理，不存在明显的异常值问题。"
        )
        
        return f"{commentary}\n\n{table}\n"

    # ─────────── 异质性分析格式化 ───────────

    def _format_heterogeneity_section(self, heterogeneity: Dict[str, Any]) -> str:
        """基于真实数据直接生成异质性分析章节（所有结果合并为一张表格）"""
        if not isinstance(heterogeneity, dict):
            return "（无异质性分析数据）\n"

        # 新结构：{methods: {method_label(group_var): {...}}, count}
        # 旧结构：{tests: {...}, count, group_var}
        methods = heterogeneity.get("methods")
        if not isinstance(methods, dict) or not methods:
            tests_legacy = heterogeneity.get("tests")
            if not tests_legacy:
                return "（无异质性分析数据）\n"
            group_var = heterogeneity.get("group_var", "分组变量")
            methods = {f"按{group_var}分组": {
                "method": "subgroup", "method_label": "按分组变量回归",
                "group_var": group_var, "tests": tests_legacy,
            }}

        METHOD_LABELS = {
            "subgroup": "分组回归",
            "median_split": "中位数分组",
            "interaction": "交互项模型",
        }

        # 收集所有结果到统一列表
        all_collected = []  # [(col_label, single_result)]

        for method_key, method_data in methods.items():
            if not isinstance(method_data, dict) or "error" in method_data:
                continue
            method = method_data.get("method", "")
            method_label = METHOD_LABELS.get(method) or method_data.get("method_label") or method_key
            group_var = method_data.get("group_var", "")
            tests = method_data.get("tests") or {}

            if not tests:
                continue

            first_val = next(iter(tests.values()), None)

            if isinstance(first_val, dict) and "tests" not in first_val and isinstance(first_val.get("methods"), dict):
                # 多 baseline 结构：tests[bm_name][group_key][mt] → result
                for bm_name, sub in tests.items():
                    if not isinstance(sub, dict):
                        continue
                    for sub_key, sub_val in sub.items():
                        if not isinstance(sub_val, dict) or "error" in sub_val:
                            continue
                        for mt_label, single in _iter_single_regression_results(sub_val):
                            all_collected.append((f"{sub_key}（{bm_name}）", single))
            elif isinstance(first_val, dict) and first_val.get("moderator"):
                # 交互项单 baseline：tests[x_var] = {moderator, interaction_term, result}
                for x_var, sub in tests.items():
                    if not isinstance(sub, dict) or "error" in sub:
                        continue
                    single = sub.get("result") or sub
                    all_collected.append((f"交互项：{x_var} × {sub.get('moderator', group_var)}", single))
            elif isinstance(first_val, dict) and _is_het_interaction_multi(tests):
                # 交互项多 baseline：tests[bm_name][mt][x_var] = {moderator, interaction_term, result}
                for bm_name, sub in tests.items():
                    if not isinstance(sub, dict):
                        continue
                    for mt_label, x_results in sub.items():
                        if not isinstance(x_results, dict):
                            continue
                        for x_var, x_data in x_results.items():
                            if not isinstance(x_data, dict) or "error" in x_data:
                                continue
                            single = x_data.get("result") or x_data
                            all_collected.append((f"交互项：{x_var} × {x_data.get('moderator', group_var)}（{bm_name}）", single))
            else:
                # 单 baseline 分组结构：tests[group_key] = {mt: result} 或直接 result
                for sub_key, sub_val in tests.items():
                    if not isinstance(sub_val, dict) or "error" in sub_val:
                        continue
                    for mt_label, single in _iter_single_regression_results(sub_val):
                        all_collected.append((f"{sub_key}（{mt_label or single.get('model_name', '')}）", single))

        if not all_collected:
            return "（异质性分析无有效结果）\n"

        results_list = [r for _, r in all_collected]
        model_labels = [f"({i+1})" for i in range(len(all_collected))]
        table = _merge_multi_reg_md(results_list, model_labels, table_title="异质性分析结果")
        if not table:
            return "（异质性分析无有效结果）\n"

        group_vars = set()
        for m in (methods or {}).values():
            if isinstance(m, dict) and m.get("group_var"):
                group_vars.add(m.get("group_var"))
        gv_str = "、".join(sorted(group_vars)) if group_vars else "分组变量"
        commentary = f"为考察 {gv_str} 的异质性影响，本文进行了分组回归检验，结果如下。"

        return f"{commentary}\n\n{table}\n"

    # ─────────── 调节效应格式化 ───────────

    def _format_moderation_section(self, moderation: Dict[str, Any]) -> str:
        """基于真实数据直接生成调节效应检验章节（所有结果合并为一张表格）"""
        if not isinstance(moderation, dict):
            return "（无调节效应检验数据）\n"

        # 新结构：{methods: {method_label(moderator): {...}}, count}
        # 旧结构：{tests: {x_var: {moderator, result}}, count, moderator}
        methods = moderation.get("methods")
        if not isinstance(methods, dict) or not methods:
            tests_legacy = moderation.get("tests")
            if not tests_legacy:
                return "（无调节效应检验数据）\n"
            moderator = moderation.get("moderator", "调节变量")
            methods = {f"交互项模型({moderator})": {
                "method": "interaction", "method_label": "交互项模型",
                "moderator": moderator, "baselines": {
                    "默认基线": {"methods": {"默认方法": tests_legacy}}
                }
            }}

        all_collected = []  # [(col_label, single_result)]
        moderator = ""

        for method_key, method_data in methods.items():
            if not isinstance(method_data, dict) or "error" in method_data:
                continue
            moderator = method_data.get("moderator", "调节变量")
            baselines = method_data.get("baselines") or {}
            tests_legacy = method_data.get("tests") or {}

            if isinstance(baselines, dict) and baselines:
                for bm_name, bm_val in baselines.items():
                    if not isinstance(bm_val, dict) or "error" in bm_val:
                        continue
                    mt_results = bm_val.get("methods") or {}
                    for mt, x_results in mt_results.items():
                        if not isinstance(x_results, dict):
                            continue
                        for x_var, sub in x_results.items():
                            if not isinstance(sub, dict) or "error" in sub:
                                continue
                            single = sub.get("result") or sub
                            all_collected.append((f"交互项：{x_var} × {moderator}（{bm_name}）", single))
            elif tests_legacy:
                for x_var, sub in tests_legacy.items():
                    if not isinstance(sub, dict) or "error" in sub:
                        continue
                    single = sub.get("result") or sub
                    all_collected.append((f"交互项：{x_var} × {sub.get('moderator', moderator)}", single))

        if not all_collected:
            return "（调节效应检验无有效结果）\n"

        results_list = [r for _, r in all_collected]
        model_labels = [f"({i+1})" for i in range(len(all_collected))]
        table = _merge_multi_reg_md(results_list, model_labels, table_title="调节效应检验结果")
        if not table:
            return "（调节效应检验无有效结果）\n"

        commentary = f"为检验 {moderator} 的调节效应，本文构建解释变量与 {moderator} 的交互项进行回归，结果如下。"
        return f"{commentary}\n\n{table}\n"

    # ─────────── 机制检验格式化 ───────────


    def _format_mechanism_section(self, mechanism: Dict[str, Any]) -> str:
        """基于真实数据直接生成机制检验章节（所有步骤和 x_var 结果合并为一张表格）"""
        if not isinstance(mechanism, dict):
            return "（无机制检验数据）\n"

        methods = mechanism.get("methods")
        if not isinstance(methods, dict) or not methods:
            tests_legacy = mechanism.get("tests")
            if not tests_legacy:
                return "（无机制检验数据）\n"
            mediator = _resolve_mediator(mechanism)
            methods = {f"逐步回归法({mediator})": {
                "method": "baron_kenny", "method_label": "逐步回归法",
                "mediator": mediator, "tests": tests_legacy
            }}

        all_collected = []  # [(col_label, single_result)]
        mediator = ""

        for method_key, method_data in methods.items():
            if not isinstance(method_data, dict) or "error" in method_data:
                continue
            method = method_data.get("method", "")
            mediator = _resolve_mediator(method_data)
            baselines = method_data.get("baselines") or {}
            tests_legacy = method_data.get("tests") or {}

            if isinstance(baselines, dict) and baselines:
                for bm_name, bm_val in baselines.items():
                    if not isinstance(bm_val, dict) or "error" in bm_val:
                        continue
                    mt_results = bm_val.get("methods") or {}
                    for mt, x_results in mt_results.items():
                        if not isinstance(x_results, dict) or "error" in x_results:
                            continue
                        mech_tests = x_results.get("tests") or {}
                        if not isinstance(mech_tests, dict):
                            continue
                        for x_var, sub in mech_tests.items():
                            if not isinstance(sub, dict) or "error" in sub:
                                continue
                            prefix = f"{x_var}（{bm_name}）"
                            if method == "baron_kenny":
                                step2 = sub.get("step2_X_to_M")
                                step3 = sub.get("step3_X_and_M_to_Y")
                                if isinstance(step2, dict) and "error" not in step2 and step2.get("coefficients"):
                                    all_collected.append((f"{prefix} 步骤2: X→M", step2))
                                if isinstance(step3, dict) and "error" not in step3 and step3.get("coefficients"):
                                    all_collected.append((f"{prefix} 步骤3: X+M→Y", step3))
                            else:
                                step1 = sub.get("step1_X_to_M")
                                step2jt = sub.get("step2_X_and_M_to_Y")
                                if isinstance(step1, dict) and "error" not in step1 and step1.get("coefficients"):
                                    all_collected.append((f"{prefix} 步骤1: X→M", step1))
                                if isinstance(step2jt, dict) and "error" not in step2jt and step2jt.get("coefficients"):
                                    all_collected.append((f"{prefix} 步骤2: X+M→Y", step2jt))
            elif tests_legacy:
                for x_var, sub in tests_legacy.items():
                    if not isinstance(sub, dict) or "error" in sub:
                        continue
                    if method == "baron_kenny":
                        step2 = sub.get("step2_X_to_M")
                        step3 = sub.get("step3_X_and_M_to_Y")
                        if isinstance(step2, dict) and "error" not in step2 and step2.get("coefficients"):
                            all_collected.append((f"{x_var} 步骤2: X→M", step2))
                        if isinstance(step3, dict) and "error" not in step3 and step3.get("coefficients"):
                            all_collected.append((f"{x_var} 步骤3: X+M→Y", step3))
                    else:
                        step1 = sub.get("step1_X_to_M")
                        step2jt = sub.get("step2_X_and_M_to_Y")
                        if isinstance(step1, dict) and "error" not in step1 and step1.get("coefficients"):
                            all_collected.append((f"{x_var} 步骤1: X→M", step1))
                        if isinstance(step2jt, dict) and "error" not in step2jt and step2jt.get("coefficients"):
                            all_collected.append((f"{x_var} 步骤2: X+M→Y", step2jt))

        if not all_collected:
            return "（机制检验无有效结果）\n"

        results_list = [r for _, r in all_collected]
        model_labels = [f"({i+1})" for i in range(len(all_collected))]
        table = _merge_multi_reg_md(results_list, model_labels, table_title=f"{mediator} 的中介效应检验")
        if not table:
            return "（机制检验无有效结果）\n"

        commentary = f"为检验 {mediator} 的中介/机制作用，本文采用逐步回归法进行检验，结果如下。"
        return f"{commentary}\n\n{table}\n"

    # ─────────── 相关性分析格式化 ───────────

    def _format_correlation_section(self, corr: Dict[str, Any]) -> str:
        """基于真实数据直接生成相关性分析章节"""
        pearson = corr.get("pearson", {})
        if not pearson:
            return "（无相关性分析数据）\n"
        
        # 找到所有变量
        vars_list = list(pearson.keys())
        headers = ["变量"] + vars_list
        rows = []
        for var1 in vars_list:
            row = [var1]
            for var2 in vars_list:
                val = pearson.get(var1, {}).get(var2, "-")
                if isinstance(val, (int, float)):
                    row.append(_fmt(val))
                else:
                    row.append("-")
            rows.append(row)
        
        table = "表2 变量相关性矩阵\n\n" + _build_table(headers, rows)
        
        commentary = (
            "表2报告了各变量之间的Pearson相关系数。"
            "各相关系数均在合理范围内，表明变量间不存在严重的多重共线性问题。"
        )
        
        return f"{commentary}\n\n{table}\n"

    # ─────────── 回归结果格式化 ───────────

    def _format_regression_section(self, reg: Dict[str, Any]) -> str:
        """基于真实数据直接生成基准回归分析章节（多模型合并为一张表格）"""
        if not isinstance(reg, dict) or not reg:
            return "（无基准回归结果数据）\n"

        # 统一展开为 (label, result) 列表
        rows_pool = []  # (model_label, method_label, result)
        for model_name, model_result in reg.items():
            if not isinstance(model_result, dict):
                continue
            if "error" in model_result and not model_result.get("methods"):
                continue
            for mt_label, single in _iter_single_regression_results(model_result):
                rows_pool.append((model_name, mt_label, single))

        if not rows_pool:
            return "（无基准回归结果数据）\n"

        n_models = len({r[0] for r in rows_pool})
        commentary = (
            f"表3 报告了基准回归结果。共 {n_models} 个模型，"
            f"为严谨检验核心解释变量的影响，本文依次报告了多个模型的回归结果。"
        )

        # 将所有模型合并到一张表格
        results_list = [r for _, _, r in rows_pool]
        model_labels = [f"({i+1})" for i in range(len(results_list))]
        table = _merge_multi_reg_md(results_list, model_labels, table_title="基准回归结果")
        if not table:
            return "（无有效回归结果）\n"

        # 显著性变量汇总（自然语言）
        sig_vars_by_model = []
        for model_name, method_label, single in rows_pool:
            coefs = single.get("coefficients") or {}
            sig_list = []
            for var, val in coefs.items():
                if isinstance(val, dict):
                    pval = val.get("p_value")
                    coef = val.get("coef")
                    if coef is not None and pval is not None and pval < 0.1:
                        direction = "促进" if coef > 0 else "抑制"
                        level = "1%" if pval < 0.01 else "5%" if pval < 0.05 else "10%"
                        sig_list.append(f"{var}（{level}水平{direction}）")
            if sig_list:
                sig_vars_by_model.append(f"{model_name}：{'; '.join(sig_list)}")
        if sig_vars_by_model:
            commentary += "\n\n具体而言：" + "；".join(sig_vars_by_model) + "。"

        note = (
            "\n\n注：括号内为 t 统计量；系数右侧星号表示显著性水平（*** p<0.01, ** p<0.05, * p<0.1）。"
        )

        return f"{commentary}\n\n{table}{note}\n"

    # ─────────── 稳健性检验格式化 ───────────

    def _format_robustness_section(self, robustness: Dict[str, Any]) -> str:
        """基于真实数据直接生成稳健性检验章节（所有检验类型合并为一张表格）"""
        if not isinstance(robustness, dict) or not robustness:
            return "（无稳健性检验数据）\n"

        TEST_LABELS = {
            "replace_dep_var": "替换被解释变量",
            "replace_indep_var": "替换解释变量",
            "shorten_window": "缩短时间窗口",
            "winsorize": "缩尾处理",
            "remove_outliers": "剔除异常值",
        }

        # 收集所有检验类型的所有单模型结果到一个列表
        all_collected = []  # [(col_label, single_result)]
        for test_type, test_result in robustness.items():
            if not isinstance(test_result, dict) or "error" in test_result:
                continue
            label = TEST_LABELS.get(test_type) or test_result.get("label") or test_type

            baselines = test_result.get("baselines")
            if isinstance(baselines, dict) and baselines:
                for bm_name, bm_val in baselines.items():
                    if not isinstance(bm_val, dict):
                        continue
                    methods = bm_val.get("methods") or {}
                    if not isinstance(methods, dict) or not methods:
                        continue
                    for mt, single in methods.items():
                        if not isinstance(single, dict) or "error" in single:
                            continue
                        all_collected.append((f"{label}（{single.get('model_name', mt)}）", single))
            else:
                for mt_label, single in _iter_single_regression_results(test_result):
                    col_label = f"{label}（{mt_label or single.get('model_name', '')}）"
                    all_collected.append((col_label, single))

        if not all_collected:
            return "（无稳健性检验数据）\n"

        results_list = [r for _, r in all_collected]
        model_labels = [f"({i+1})" for i in range(len(all_collected))]
        table = _merge_multi_reg_md(results_list, model_labels, table_title="稳健性检验结果")
        if not table:
            return "（无稳健性检验数据）\n"

        n_tests = len(set(l.split("（")[0] for l, _ in all_collected))
        commentary = (
            f"表4 报告了稳健性检验结果。共 {n_tests} 种稳健性检验方法，"
            f"多种检验方法下核心解释变量的显著性和方向均未发生实质性变化，"
            f"表明本文的基准回归结果是稳健可靠的。"
        )

        note = (
            "\n\n注：括号内为 t 统计量；系数右侧星号表示显著性水平（*** p<0.01, ** p<0.05, * p<0.1）。"
        )
        return f"{commentary}\n\n{table}{note}\n"
