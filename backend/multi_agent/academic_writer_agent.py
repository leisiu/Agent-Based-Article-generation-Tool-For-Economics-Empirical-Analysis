"""
学术写作智能体
负责根据大纲、实证结果和文献综述生成完整论文
（实证分析章节由DataAnalystAgent基于真实数据生成，本agent不再格式化表格）
"""

import json
import re
from typing import Dict, Any, List, Optional

from core.base_agent import BaseAgent, Task, AgentResponse


# ──────────────────── 智能体类 ────────────────────

class AcademicWriterAgent(BaseAgent):
    """学术写作智能体 - 根据大纲逐节生成论文"""

    def __init__(self, api_key: Optional[str] = None, model_type: str = None):
        super().__init__(
            agent_id="academic_writer",
            role="学术写作专家",
            capabilities=["论文撰写", "学术规范", "结构组织", "文献引用", "实证结果整合", "表格生成"],
            api_key=api_key,
            model_type=model_type
        )

    async def process_task(self, task: Task) -> AgentResponse:
        """处理学术写作任务"""
        self.logger.info(f"开始处理学术写作任务: {task.id}")

        try:
            data = self._parse_task_content(task)
            outline_data = data.get("outline_data")
            if not outline_data:
                raise ValueError("缺少 outline_data 参数")

            paper = await self._generate_by_outline(
                outline_data=outline_data,
                analysis_result=data.get("analysis_result", ""),
                literature_review=data.get("literature_review", ""),
                empirical_results=data.get("empirical_results", {}),
                command=data.get("command", ""),
                empirical_chapter=data.get("empirical_chapter", ""),
                literature_references=data.get("literature_references", ""),
            )

            return self.create_response(
                task=task,
                content=paper,
                metadata={"writing_type": "llm_generated"},
            )

        except Exception as e:
            self.logger.error(f"学术写作失败: {e}")
            return self.create_response(
                task=task,
                content=f"学术写作失败: {e}",
                metadata={"error": True, "error_type": "writing_error"},
                success=False,
                error_message=str(e),
            )

    # ──────────────────── 主流程 ────────────────────

    async def _generate_by_outline(
        self,
        outline_data: Dict[str, Any],
        analysis_result: str,
        literature_review: str,
        empirical_results: Dict[str, Any],
        command: str,
        empirical_chapter: str = "",  # 数据智能体预生成的实证章节（含真实数据）
        literature_references: str = "",  # 文献综述智能体预生成的真实参考文献列表
    ) -> str:
        """根据大纲逐节生成论文"""
        sections = outline_data.get("sections", [])
        outline_title = outline_data.get("title", "")

        self.logger.info(f"开始按大纲生成论文，共 {len(sections)} 个章节")
        self.logger.info(f"是否有预生成的实证章节: {'是' if empirical_chapter else '否'}")
        self.logger.info(f"是否有预生成的参考文献: {'是' if literature_references else '否'}")

        # 先由 LLM 生成论文标题
        title = await self._generate_title(
            command=command,
            analysis_result=analysis_result,
            outline_title=outline_title,
        )

        # 构建上下文（所有方法共享）
        ctx = {
            "title": title,
            "command": command,
            "analysis_result": analysis_result,
            "literature_review": literature_review,
            "empirical_results": empirical_results,
            "all_sections": sections,
            "core_findings": self._extract_core_findings(empirical_results),
            "empirical_chapter": empirical_chapter,
            "literature_references": literature_references,
        }

        # 顺序生成：摘要 → 章节 → 参考文献（直接使用预生成的）
        abstract = await self._generate_abstract_keywords(ctx)

        LITERATURE_CHAPTER_TITLE = "二、文献综述"
        EMPIRICAL_CHAPTER_TITLE = "四、实证分析"
        chapter_results = []
        for section in sections:
            section_title = section.get("title", "")

            # 文献综述章节：直接使用文献综述agent预生成的内容（保持引用编号与参考文献列表一致）
            if section_title == LITERATURE_CHAPTER_TITLE and literature_review:
                self.logger.info(f"使用文献综述agent预生成的文献综述章节（保留引用编号）")
                literature_chapter = f"\n## {LITERATURE_CHAPTER_TITLE}\n\n{literature_review.strip()}"
                chapter_results.append(literature_chapter)
            # 实证分析章节：使用数据智能体预生成的内容（基于真实数据，不经过LLM）
            elif section_title == EMPIRICAL_CHAPTER_TITLE and empirical_chapter:
                self.logger.info(f"使用数据智能体预生成的实证分析章节（基于真实数据）")
                empirical_content = f"\n## {EMPIRICAL_CHAPTER_TITLE}\n\n{empirical_chapter.strip()}"
                chapter_results.append(empirical_content)
            else:
                chapter = await self._generate_chapter(section, ctx)
                chapter_results.append(chapter)

        # 组装论文：标题 → 摘要 → 所有章节 → 参考文献（直接使用文献综述agent预生成的）
        parts = [f"# {title}\n", abstract]
        for i, result in enumerate(chapter_results):
            if isinstance(result, str) and result:
                parts.append(result)
            else:
                self.logger.warning(f"章节 {i+1} 生成失败")
                parts.append(f"\n## {sections[i]['title']}\n\n（该章节生成失败）\n")
        # 参考文献直接使用文献综述agent基于真实论文生成的列表
        if literature_references:
            parts.append(f"\n\n{literature_references}")
        else:
            parts.append("\n\n## 参考文献\n\n（参考文献生成失败）\n")

        return "\n".join(parts)

    # ──────────────────── 标题生成 ────────────────────

    async def _generate_title(
        self,
        command: str,
        analysis_result: str,
        outline_title: str,
    ) -> str:
        """由 LLM 生成论文标题"""
        prompt = f"""请根据以下研究信息生成一个学术论文标题：

研究指令：{command}
数据分析概述：{analysis_result[:1500] if analysis_result else "无"}
大纲参考标题：{outline_title}

要求：
1. 标题简洁、准确，体现研究主题和方法
2. 不超过25个汉字
3. 中文学术风格
4. 只输出标题本身，不要任何前缀、引号或说明
5. 可以有副标题
直接输出标题。"""

        title = await self._call_llm(
            self._build_prompt("你是一位学术论文写作专家，擅长拟定论文标题。", prompt),
            max_tokens=50,
        )
        return title.strip().strip('"').strip("'").strip() if title else "实证研究论文"

    # ──────────────────── 摘要 ────────────────────

    async def _generate_abstract_keywords(self, ctx: Dict[str, Any]) -> str:
        """生成摘要和关键词

        摘要采用「背景→研究欠缺→实验设计→研究发现」结构化模板：
            - 背景：阐述研究主题的现实/理论背景
            - 研究欠缺：指出已有研究的不足（基于文献综述）
            - 实验设计：简述样本/变量/方法
            - 研究发现：分点列出基准回归/稳健性/异质性/调节效应/机制的核心发现
        """
        findings = self._extract_core_findings(ctx["empirical_results"])

        prompt = f"""请为以下论文撰写摘要和关键词。

## 论文基本信息
- 论文标题：{ctx['title']}
- 研究指令：{ctx['command']}
- 核心实证发现（自然语言描述）：{findings[:1000] if findings else "详见实证分析部分"}
- 数据分析概述：{ctx['analysis_result'][:1500] if ctx['analysis_result'] else "无"}
- 文献综述要点：{ctx['literature_review'][:800] if ctx['literature_review'] else "无"}

## 摘要结构模板（严格按此逻辑组织，约 300-400 字）
摘要需按以下五个层次递进展开：

1. **背景**：1-2 句，阐述研究主题的现实背景和理论背景，引出研究问题的重要性。
2. **研究欠缺**：1 句，基于文献综述指出已有研究存在的不足或研究空白（为本文切入点铺垫）。
3. **实验设计**：1-2 句，说明数据来源、样本范围、核心变量、计量方法（用自然语言，不列具体公式）。
4. **研究发现**（**核心，必须按以下四点逐条描述，每条 1-2 句，全部用自然语言，严禁出现具体数值**）：
   - (1) 基准回归发现：[核心解释变量 X 对被解释变量 Y 是促进还是抑制，显著性方向]
   - (2) 稳健性检验发现：[替换被解释变量/缩短窗口/缩尾/剔除异常值等稳健性检验后，主要结论是否依然成立]
   - (3) 异质性分析发现：[在不同分组（如国有/非国有、东部/中西部等）下，X 对 Y 的影响是否存在显著差异]
   - (4) 机制检验发现：[通过中介变量或调节效应，揭示 X 影响 Y 的作用渠道或边界条件]
   - (5) 调节效应发现
5. **结论与启示**：1-2 句，总结本文的理论贡献和实践启示。

## 格式与语言要求
- 摘要正文控制在 300-400 字
- 全部使用中文学术语言，句式严谨、逻辑连贯、表达精炼
- Markdown 格式
- 摘要标题为 `## 摘要`
- 摘要正文后另起一行输出关键词（3-5 个），格式：**关键词**：关键词1；关键词2；关键词3

## 严格禁止
- 严禁出现任何具体的回归系数、p 值、t 值、R²、样本量等数值
- 严禁编造本文未执行的检验结果（如未做异质性就不要写异质性发现）
- 严禁在摘要开头输出「好的」「我将」「下面」等任何寒暄/确认语句
- 严禁输出「## 参考文献」章节（参考文献由系统自动追加）

## 输出示例（仅作结构参考）
```
## 摘要

背景：[1-2 句背景描述]。然而，[研究欠缺]。

本文基于 [数据来源]，[实验设计简述]。研究发现：(1) 基准回归发现...；(2) 稳健性检验发现...；(3) 异质性分析发现...；(4) 机制检验发现...。

[结论与启示]。

**关键词**：关键词1；关键词2；关键词3
```

直接输出摘要和关键词正文，不要任何额外说明。"""

        return await self._call_llm(
            self._build_prompt(
                "你是一位学术论文写作专家，擅长撰写中文学术论文摘要。"
                "摘要应严格遵循「背景→研究欠缺→实验设计→研究发现→结论」五段式结构，"
                "语言精炼、逻辑严密、学术化。",
                prompt
            ),
            max_tokens=1500,
        ) or "\n## 摘要\n\n（摘要生成失败）\n"

    # ──────────────────── 章节生成 ────────────────────

    async def _generate_chapter(self, section: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """生成单个章节（小节串行，保持连贯性）"""
        section_title = section.get("title", "")
        subsections = section.get("subsections", [])

        if not subsections:
            return f"\n## {section_title}\n\n"

        self.logger.info(f"开始生成章节: {section_title}，共 {len(subsections)} 个小节")

        chapter_parts = [f"## {section_title}\n"]
        previous_tail = ""

        for subsection in subsections:
            prompt = self._build_subsection_prompt(subsection, section_title, ctx, previous_tail)

            content = await self._call_llm(
                self._build_prompt(
                    "你是一位专业的学术论文写作专家，擅长撰写经济学和管理学领域的学术论文。"
                    "请根据要求撰写指定小节，语言学术化、逻辑清晰、论证充分。"
                    "输出格式：使用Markdown格式，不要重复输出章节标题。",
                    prompt,
                ),
                max_tokens=4000,
            )

            if content:
                chapter_parts.append(content)
                previous_tail = content[-1500:] if len(content) > 1500 else content
            else:
                self.logger.warning(f"小节 '{subsection.get('title', '')}' 生成失败")
                chapter_parts.append(f"\n### {subsection.get('title', '')}\n\n（该小节生成失败）\n")

        return "\n\n".join(chapter_parts)

    def _build_subsection_prompt(
        self,
        subsection: Dict[str, Any],
        section_title: str,
        ctx: Dict[str, Any],
        previous_tail: str,
    ) -> str:
        """构建单个小节的生成提示词"""
        subsection_title = subsection.get("title", "")
        content_requirement = subsection.get("content_requirement", "")

        # 论文整体结构
        structure = "论文整体结构：\n" + "\n".join(f"- {s.get('title', '')}" for s in ctx["all_sections"])

        # 根据大纲章节标题精确判断章节类型
        LITERATURE_CHAPTERS = {"二、文献综述"}
        EMPIRICAL_CHAPTERS = {"四、实证分析"}
        INTRODUCTION_CHAPTERS = {"一、引言"}
        CONCLUSION_CHAPTERS = {"五、研究结论与政策建议"}
        RESEARCH_DESIGN_CHAPTERS = {"三、研究设计"}

        constraint = ""
        if section_title in LITERATURE_CHAPTERS:
            constraint = (
                "**约束**：本节属于文献综述章节，严禁出现任何自己的实证结果、数据表格或回归系数。\n"
                "**引用要求**：本节**必须**使用引用标记如[1]、[2]引证文献来源，引用编号必须与论文末尾参考文献列表严格对应。"
            )
        elif section_title in INTRODUCTION_CHAPTERS:
            constraint = (
                "**约束**：本节属于引言章节，仅应阐述研究背景、研究问题、研究意义和创新点。\n"
                "**严禁在本节出现以下内容**：\n"
                "  - 具体的研究方法、模型设定、公式推导（这些属于「三、研究设计」章节）\n"
                "  - 数据来源、样本筛选、变量测度方式（这些属于「三、研究设计」章节）\n"
                "  - 研究假设的提出或推导（这些属于「二、文献综述」章节）\n"
                "  - 任何具体的回归系数、p值、t值、表格等实证数据（这些属于「四、实证分析」章节）\n"
                "  - **严禁提及或引用任何已有文献、已有研究、现有文献或学术界观点**——本节只需陈述研究背景和本文贡献"
            )
        elif section_title in CONCLUSION_CHAPTERS:
            constraint = (
                '**约束**：本节属于研究结论章节，总结主要发现时只能使用自然语言描述（如"x对y有显著的促进作用"），严禁出现任何具体的回归系数、p值、t值、R²等数据。所有具体实证数据已在实证分析章节呈现。\n'
                "**严禁提及或引用任何已有文献、已有研究或现有文献**——本节仅总结本文的研究发现和政策建议。"
            )
        elif section_title in RESEARCH_DESIGN_CHAPTERS:
            constraint = (
                "**约束**：本节属于研究设计章节，仅应阐述研究方法、模型设定、数据来源和变量说明。\n"
                "**严禁提及或引用任何已有文献、已有研究或现有文献**——本节只需说明本文的研究设计。"
            )
        elif section_title not in EMPIRICAL_CHAPTERS:
            constraint = "**约束**：本节不属于实证分析章节，严禁出现任何具体的回归系数、p值、t值、表格等实证数据。所有实证数据只能在「实证分析」章节呈现。\n**严禁引用标记**：本节**严禁**使用[1]、[2]等引用标记，如需引用文献请使用「已有研究」「现有文献」等模糊表述。"

        data_injection = ""
        # 非实证章节：使用自然语言的核心发现作为参考
        core_findings = ctx.get('core_findings', '')
        if core_findings and any(kw in section_title for kw in ("研究设计", "结论", "摘要")):
            data_injection = f"""## 本文实际实证结果摘要（仅用于自然语言总结参考，严禁出现具体数据）

核心发现（自然语言描述）：{core_findings}

**约束**：
1. 总结实证发现时只能使用自然语言，如"x对y有显著的促进作用"
2. 严禁输出任何回归系数、p值、t值、R²等具体数值
3. 严禁编造任何不在上述核心发现中的额外结果"""

        # 非文献综述章节不传入文献综述内容，防止 LLM 编造虚假引用
        lit_review_context = ""
        if section_title in LITERATURE_CHAPTERS and ctx.get('literature_review'):
            lit_review_context = f"文献综述参考（含引用标记，引用时需与参考文献编号一致）：{ctx['literature_review']}"

        prompt = f"""请撰写论文《{ctx['title']}》的以下小节：
### {subsection_title}

撰写要求：{content_requirement}

论文整体结构：
{structure}

研究指令：{ctx['command']}

{lit_review_context}
{data_injection}
{constraint}
"""
        if previous_tail:
            prompt += f"\n上一小节的结尾（供衔接参考）：\n{previous_tail[-500:]}\n请确保与上一小节自然衔接。\n"

        prompt += """
要求：
- 只撰写当前小节内容
- 使用正式的学术语言，论证充分
- 符合经济管理学期刊写作风格
- 输出格式：Markdown
- 不要输出论文大标题和章标题

**重要约束：**
1. **严禁编造任何不存在的实证数据、表格、回归系数或统计量**。本文真实的实证数据/表格已统一在「四、实证分析」章节呈现。
2. **严禁在正文中插入任何 Markdown 表格**（除非该小节标题明确指出需要表格）。所有表格只能在「四、实证分析」章节出现。
3. **严禁在文献综述、研究结论、引言中编造具体的研究数据、p值、回归系数**。
4. **严禁提及或引用任何已有文献、已有研究或现有文献**（文献综述章节除外）。
5. **引用标记规则**：仅「文献综述」章节可以使用[1]、[2]等引用标记标记引用文献；其他所有章节（引言、研究设计、实证分析、研究结论）**严禁使用[1]、[2]等引用标记**。

请直接输出该小节内容。"""

        return prompt.strip()

    def _extract_core_findings(self, empirical_results: Dict[str, Any]) -> str:
        """提取核心实证发现（仅输出自然语言描述，不包含具体数据）"""
        if not empirical_results or not isinstance(empirical_results, dict):
            return ""

        findings = []
        regressions = empirical_results.get("regression", {})
        if isinstance(regressions, dict):
            for model_type, model_result in regressions.items():
                if not isinstance(model_result, dict) or "error" in model_result:
                    continue
                coefs = model_result.get("coefficients", {})
                if isinstance(coefs, dict):
                    for var, val in coefs.items():
                        if isinstance(val, dict):
                            coef = val.get("coef")
                            pval = val.get("p_value")
                            if coef is not None and pval is not None and pval < 0.1:
                                direction = "促进" if coef > 0 else "抑制"
                                sig_level = "在1%水平上显著" if pval < 0.01 else "在5%水平上显著" if pval < 0.05 else "在10%水平上显著"
                                findings.append(f"{var}对{direction}作用，{sig_level}")

        return "；".join(findings[:5]) if findings else "各变量间存在显著相关性"

    # ──────────────────── 审查修改 ────────────────────

    async def run_revision(
        self,
        paper_content: str,
        review_comments: str,
        quality_report: str,
    ) -> str:
        """根据审稿意见修改论文
        注意：以下章节由前置 agent 基于真实数据预生成，跳过 LLM 二次修改以保留格式/编号：
            - 二、文献综述（含研究假设和引用编号，必须保持原样）
            - 四、实证分析（含真实表格，LLM 无法再生成准确的）
            - 参考文献（由系统生成）
            - 摘要（避免 LLM 改动核心发现数据）
        """
        # 不允许 LLM 重新生成的章节（保留前置 agent 的输出）
        PROTECTED_SECTIONS = ("二、文献综述", "四、实证分析", "参考文献", "摘要")

        sections = self._split_sections(paper_content)

        # 先把"五、研究结论与政策建议"之后的内容（参考文献）剥离出来，由系统保护
        ref_text = ""
        for sec_name, sec_text in list(sections.items()):
            if any(p in sec_name for p in ("参考文献", "Reference")) and not sec_name.startswith("五"):
                ref_text = sec_text
                del sections[sec_name]
                break
        # 收集实证分析章节的完整原文（可能跨多个 section，保留到原文中）
        empirical_original = None
        for sec_name, sec_text in sections.items():
            if "四、实证分析" in sec_name or sec_name.startswith("四") and "实证" in sec_name:
                empirical_original = sec_text
                break

        review_summary = review_comments[:3000] if len(review_comments) > 3000 else review_comments
        quality_summary = quality_report[:2000] if len(quality_report) > 2000 else quality_report

        self.logger.info("【写作 Agent】根据审稿意见修改论文...")

        revised_contents = {}
        for section_name, section_text in sections.items():
            # 受保护的章节：直接保留原内容，不调用 LLM
            if any(p in section_name for p in PROTECTED_SECTIONS):
                self.logger.info(f"跳过 LLM 修改（受保护章节）: {section_name}")
                revised_contents[section_name] = section_text
                continue

            self.logger.info(f"修改章节：{section_name}")

            section_truncated = section_text[:4000] if len(section_text) > 4000 else section_text

            prompt = (
                f"审稿意见摘要：\n{review_summary}\n\n"
                f"质量评估报告：\n{quality_summary}\n\n"
                f"当前章节：{section_name}\n"
                f"当前内容：\n{section_truncated}\n\n"
                "请根据审稿意见修改该章节。要求：\n"
                "1. 只输出修改后的内容，不要解释修改过程\n"
                "2. 针对审稿意见中提到的具体问题逐一修改\n"
                "3. 参考质量评估报告中的薄弱环节进行改进\n"
                "4. 保持或增加内容的充实度，不要删减篇幅\n"
                "5. 使用中文学术语言，Markdown格式\n"
                "6. **严禁编造任何不存在的实证数据、表格、回归系数**"
            )

            revised_text = await self._call_llm(
                self._build_prompt("你是一位学术论文修改专家，擅长根据审稿意见修改论文。", prompt),
                max_tokens=4000,
            )
            if revised_text:
                revised_contents[section_name] = revised_text
            else:
                revised_contents[section_name] = section_text

        # 重新组装论文
        # 提取原标题
        title_match = re.search(r"^#\s+(.+)$", paper_content, re.MULTILINE)
        title = title_match.group(1) if title_match else "实证研究论文"

        # 章节显示名称 → 实际键名映射
        section_display_order = [
            "摘要", "一、引言", "二、文献综述",
            "三、研究设计", "四、实证分析", "五、研究结论与政策建议", "参考文献"
        ]

        parts = [f"# {title}\n"]
        # 按标准顺序依次添加
        for display_name in section_display_order:
            # 精确匹配或部分匹配
            matched_key = None
            for key in revised_contents:
                if key == display_name or key.endswith(display_name) or display_name in key:
                    matched_key = key
                    break
            if matched_key:
                parts.append(revised_contents[matched_key])

        # 添加剩余未匹配的章节（防止遗漏）
        matched_keys = set()
        for display_name in section_display_order:
            for key in revised_contents:
                if key == display_name or key.endswith(display_name) or display_name in key:
                    matched_keys.add(key)
        for key, text in revised_contents.items():
            if key not in matched_keys:
                parts.append(text)

        # 【关键】重新追加参考文献（run_revision 开头从 sections 中剥离过参考文献，必须恢复回来）
        if ref_text:
            parts.append(ref_text)
        else:
            # 兜底：如果原文中没有找到独立的参考文献段，尝试在最后追加
            self.logger.warning("【run_revision】未在原文中找到参考文献段，请检查前置 agent 是否生成了参考文献")
            parts.append("## 参考文献\n\n（参考文献生成失败）\n")

        return "\n\n".join(parts)

    async def run_selective_revision(
        self,
        paper_content: str,
        review_comments: str,
        quality_report: str,
        sections_to_revise: List[str],
    ) -> str:
        """根据审稿意见修改指定章节"""
        sections = self._split_sections(paper_content)

        review_summary = review_comments[:3000] if len(review_comments) > 3000 else review_comments
        quality_summary = quality_report[:2000] if len(quality_report) > 2000 else quality_report

        self.logger.info("【写作 Agent】根据审稿意见修改指定章节...")

        revised_contents = sections.copy()
        for section_name in sections_to_revise:
            # 模糊匹配章节名
            matched_name = None
            for key in sections:
                if section_name in key or key in section_name:
                    matched_name = key
                    break

            if not matched_name:
                self.logger.warning(f"警告: 章节 '{section_name}' 不存在，跳过")
                continue

            section_text = sections[matched_name]
            section_truncated = section_text[:4000] if len(section_text) > 4000 else section_text
            self.logger.info(f"修改章节：{matched_name}")

            prompt = (
                f"审稿意见摘要：\n{review_summary}\n\n"
                f"质量评估报告：\n{quality_summary}\n\n"
                f"当前章节：{matched_name}\n"
                f"当前内容：\n{section_truncated}\n\n"
                "请根据审稿意见修改该章节。要求：\n"
                "1. 只输出修改后的内容，不要解释修改过程\n"
                "2. 针对审稿意见中提到的具体问题逐一修改\n"
                "3. 保持或增加内容的充实度，不要删减篇幅\n"
                "4. 使用中文学术语言，Markdown格式"
            )

            revised_text = await self._call_llm(
                self._build_prompt("你是一位学术论文修改专家，擅长根据审稿意见修改论文。", prompt),
                max_tokens=4000,
            )
            if revised_text:
                revised_contents[matched_name] = revised_text

        # 重新组装
        title_match = re.search(r"^#\s+(.+)$", paper_content, re.MULTILINE)
        title = title_match.group(1) if title_match else "实证研究论文"

        parts = [f"# {title}\n"]
        for sec_name, sec_text in revised_contents.items():
            parts.append(sec_text)

        return "\n\n".join(parts)

    def _split_sections(self, paper_content: str) -> Dict[str, str]:
        """将论文按 ## 一级章节拆分为字典（### 子节保留在父章节内）

        只匹配中文编号的一级标题（如 一、引言, 二、文献综述, 参考文献 等），
        避免文献综述/实证分析等章节内部的 ## 子标题被错误分割。
        """
        sections = {}
        lines = paper_content.split("\n")
        current_section = None
        current_lines = []

        # 匹配中文编号章节标题：^##\s+[一二三四五六七八九十]、 或 ^##\s+参考文献
        section_pattern = re.compile(r'^##\s+([一二三四五六七八九十]、.+|参考文献|摘要)$')

        for line in lines:
            match = section_pattern.match(line)
            if match:
                # 保存上一个章节
                if current_section:
                    sections[current_section] = "\n".join(current_lines).strip()
                current_section = match.group(1).strip()
                current_lines = [line]
            else:
                current_lines.append(line)

        # 保存最后一个章节
        if current_section:
            sections[current_section] = "\n".join(current_lines).strip()

        self.logger.info(f"【_split_sections】拆分为 {len(sections)} 个章节: {list(sections.keys())}")
        return sections
