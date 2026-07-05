"""
文献综述智能体
负责搜索相关文献并生成文献综述
"""

import re
import logging
import time
from typing import Dict, Any, List, Optional

from core.base_agent import BaseAgent, Task, AgentResponse
from core.llm_client import LLMClient
from tools import arxiv_tool


class LiteratureReviewAgent(BaseAgent):
    """文献综述智能体
    
    负责根据研究主题搜索相关文献并生成文献综述
    """
    
    def __init__(self, api_key: str = None, agent_id: str = "literature_review_agent", model_type: str = None):
        """保持与其他 agent 构造函数签名一致：第一个位置参数是 api_key"""
        super().__init__(
            agent_id=agent_id,
            role="文献综述专家",
            capabilities=["文献搜索", "文献综述撰写"],
            api_key=api_key,
            model_type=model_type
        )
        self.logger = logging.getLogger(f"LiteratureReviewAgent[{agent_id}]")

        # 文献来源配置
        self.literature_sources = {
            "arxiv": {"enabled": True, "max_results": 50}
        }
    
    async def process_task(self, task: Task) -> AgentResponse:
        """处理文献综述任务"""
        try:
            task_data = self._parse_task_content(task)
            
            research_topic = task_data.get("research_topic", "")
            keywords = task_data.get("keywords", [])
            research_direction = task_data.get("research_direction", "")
            uploaded_papers = task_data.get("uploaded_papers", [])
            # 假设素材：来自数据智能体，仅基于实际执行的实证分析
            hypothesis_content = task_data.get("hypothesis_content", "") or ""
            
            self.logger.info(f"开始文献综述任务: {research_topic}")
            self.logger.info(f"用户上传文献: {len(uploaded_papers)} 篇")
            
            # 步骤1: 先整合用户上传文献
            all_papers = []
            for up in uploaded_papers:
                title = up.get("title", "")
                authors_raw = up.get("author", up.get("authors", ""))
                if isinstance(authors_raw, str):
                    authors = [authors_raw]
                else:
                    authors = authors_raw or []
                all_papers.append({
                    "title": f"{title} (用户提供)",
                    "authors": authors,
                    "year": up.get("year", ""),
                    "summary": up.get("abstract", up.get("summary", "")),
                    "journal": up.get("journal", ""),
                    "source": "user_uploaded",
                })
            
            self.logger.info(f"步骤1完成: 用户上传文献 {len(all_papers)} 篇")
            for up in all_papers:
                self.logger.info(f"  用户文献: {up.get('title','?')[:80]}")

            # 步骤2: 提取搜索关键词
            # 如果传入了变量名关键词（可能为中文），先翻译为英文再用于搜索
            variable_keywords = keywords or []
            if variable_keywords:
                self.logger.info(f"原始变量名关键词（可能需要翻译）: {variable_keywords}")
            # 通过 LLM 将变量名转化为英文学术术语，生成搜索关键词
            general_keywords = self._extract_keywords(research_topic, research_direction, variable_keywords)
            keywords = general_keywords[:15]

            self.logger.info(f"步骤2完成: 搜索关键词 {len(keywords)} 个: {keywords}")

            # 步骤3: 搜索arxiv
            self.logger.info("步骤3: 搜索arXiv...")
            arxiv_papers = self._search_arxiv(keywords)
            self.logger.info(f"arXiv初步搜索: 找到 {len(arxiv_papers)} 篇论文（去重后）")

            # 步骤4: 去重合并（无下限要求，硬性截断到50篇）
            arxiv_papers = self._deduplicate_papers(arxiv_papers)
            # 控制参考文献总量：用户文献全部保留 + arXiv 最多补到 50 篇
            MAX_REFERENCES = 50
            if len(arxiv_papers) > MAX_REFERENCES - len(all_papers):
                arxiv_papers = arxiv_papers[: max(0, MAX_REFERENCES - len(all_papers))]
            combined = self._merge_papers(all_papers, arxiv_papers)
            self.logger.info(f"去重合并后共 {len(combined)} 篇论文（arXiv 截断到 {len(arxiv_papers)} 篇）")

            self.logger.info(f"步骤4完成: 最终共 {len(combined)} 篇论文（其中用户上传 {len(uploaded_papers)} 篇）")
            
            # 生成真实参考文献列表（基于真实论文，不经过LLM）
            references_text = self._format_references(combined)
            
            # 步骤5: 生成文献综述（含研究假设）
            literature_review = self._generate_review(
                research_topic,
                research_direction,
                combined,
                uploaded_count=len(uploaded_papers),
                hypothesis_content=hypothesis_content,
            )
            
            # 步骤6: 解析文献综述中实际引用的编号，只保留被引用的论文，并重新编号引用
            cited_numbers = self._extract_cited_numbers(literature_review)
            if cited_numbers:
                self.logger.info(f"文献综述中实际引用的编号: {sorted(cited_numbers)}")
                # 只保留被引用的论文（按原顺序）
                cited_papers = [p for i, p in enumerate(combined, 1) if i in cited_numbers]
                if cited_papers:
                    self.logger.info(f"过滤后保留 {len(cited_papers)} 篇实际引用的论文（原共 {len(combined)} 篇）")
                    # 构建旧编号→新编号的映射（如旧[3]成为新[2]）
                    old_to_new = {}
                    new_idx = 1
                    for p in combined:
                        old_idx = combined.index(p) + 1
                        if old_idx in cited_numbers:
                            old_to_new[old_idx] = new_idx
                            new_idx += 1
                    # 对文献综述正文中的引用编号进行重映射
                    def _renumber_citation(match):
                        old_num = int(match.group(1))
                        new_num = old_to_new.get(old_num)
                        if new_num and new_num != old_num:
                            return f"[{new_num}]"
                        return match.group(0)
                    literature_review = re.sub(r'\[(\d+)\]', _renumber_citation, literature_review)
                    self.logger.info(f"引用编号重映射完成: {old_to_new}")
                    combined = cited_papers
                    references_text = self._format_references(combined)
                else:
                    self.logger.warning("解析到引用编号但无匹配论文，保留完整列表")
            else:
                self.logger.warning("文献综述中未检测到引用编号，保留完整论文列表")
            
            return self.create_response(
                task=task,
                content=literature_review,
                metadata={
                    "papers_count": len(combined),
                    "keywords": keywords,
                    "papers": combined[:50],
                    "references_text": references_text,  # 仅包含实际引用论文的参考文献
                }
            )
        
        except Exception as e:
            self.logger.error(f"文献综述任务失败: {str(e)}")
            return self.create_response(
                task=task,
                content="",
                metadata={},
                success=False,
                error_message=str(e)
            )
    
    def _extract_keywords(self, research_topic: str, research_direction: str,
                          variable_names: List[str] = None) -> List[str]:
        """从研究主题和变量名中提取英文搜索关键词

        variable_names: 实证分析中的关键变量名（解释变量、被解释变量、中介变量等），
                       用于生成更具针对性的搜索关键词。

        返回：通用主题关键词 + 每个变量翻译后的英文学术术语（共约10-15个）
        """
        var_context = ""
        if variable_names:
            var_context = (
                f"\n\n本研究涉及以下关键变量（需要逐个翻译为英文关键词）：\n"
                f"{', '.join(variable_names)}\n"
            )

        prompt = (
            f"研究主题: {research_topic}\n"
            f"研究方向: {research_direction}\n"
            f"{var_context}\n"
            "请输出两部分关键词，用 `---` 分隔。\n\n"
            "第一部分：**通用主题关键词**（3-5个）—— 涵盖研究主题和研究方向的核心概念。\n"
            "第二部分：**变量翻译关键词** —— 将上方每个变量名翻译为标准的英文学术术语。"
            "如果一个变量名可以用多个常见术语表达，都列出来，用逗号分隔。\n\n"
            "输出格式：\n"
            "通用关键词1, 通用关键词2, 通用关键词3\n"
            "---\n"
            "变量翻译1, 变量翻译2, 变量翻译3, ...\n\n"
            "要求：\n"
            "1. 关键词应对应国际学术界的标准术语，便于在学术数据库中检索\n"
            "2. 变量翻译关键词必须涵盖所有变量名，不能遗漏\n"
            "3. 不要包含具体公司/数据集名称或分析方法\n"
            "4. 仅返回上述格式的两行内容，不要多余文字"
        )
        try:
            result = self._call_llm_sync([
                {"role": "system", "content": "你是一个学术文献搜索专家，擅长提取和翻译关键词。"},
                {"role": "user", "content": prompt}
            ])
            all_keywords = []
            parts = result.strip().split("---")
            # 第一部分：通用关键词
            if len(parts) >= 1:
                general = [k.strip() for k in parts[0].strip().split(",") if k.strip()]
                all_keywords.extend(general[:5])
            # 第二部分：变量翻译关键词
            if len(parts) >= 2:
                specific = [k.strip() for k in parts[1].strip().split(",") if k.strip()]
                all_keywords.extend(specific[:12])
            # 去重（按小写）
            seen = set()
            unique = []
            for kw in all_keywords:
                key = kw.lower()
                if key not in seen:
                    seen.add(key)
                    unique.append(kw)
            return unique[:15] if unique else [research_topic]
        except Exception as e:
            self.logger.warning(f"关键词提取失败: {e}，使用默认关键词")
            return [research_topic]
    
    def _search_arxiv(self, keywords: List[str], max_per_query: int = 80) -> List[Dict]:
        """搜索arXiv"""
        if not self.literature_sources.get("arxiv", {}).get("enabled", True):
            return []
        # 使用全部关键词进行搜索（每个关键词单独搜索，由 search_multiple 去重合并）
        return arxiv_tool.search_multiple(keywords, max_per_query=max_per_query)
    
    def _deduplicate_papers(self, papers: List[Dict]) -> List[Dict]:
        """对论文列表按标题去重（保留第一个出现的）"""
        seen = set()
        result = []
        for p in papers:
            t = p.get("title", "").lower().strip()
            if t and t not in seen:
                seen.add(t)
                result.append(p)
        return result
    
    def _merge_papers(self, user_papers: List[Dict], arxiv_papers: List[Dict]) -> List[Dict]:
        """合并用户文献和arXiv文献（arXiv去重过滤，避免与用户文献重复）"""
        seen_titles = set()
        for p in user_papers:
            t = p.get("title", "").lower().strip()
            if t:
                seen_titles.add(t)
        
        result = list(user_papers)
        for p in arxiv_papers:
            t = p.get("title", "").lower().strip()
            if t and t not in seen_titles:
                seen_titles.add(t)
                result.append(p)
        return result
    
    def _expand_search(
        self,
        combined: List[Dict],
        user_papers: List[Dict],
        keywords: List[str],
        research_topic: str,
        research_direction: str,
        min_papers: int,
    ) -> List[Dict]:
        """扩展搜索直到达到最低论文数"""
        # 第一轮：用全部关键词，增加每关键词结果数
        if len(combined) < min_papers:
            self.logger.info("扩展搜索第一轮: 使用全部关键词 + 增大结果数")
            more = self._search_arxiv(keywords, max_per_query=40)
            more = self._deduplicate_papers(more)
            combined = self._merge_papers(user_papers, more)
            self.logger.info(f"第一轮扩展后: {len(combined)} 篇")

        # 第二轮：用LLM生成更多变体关键词再搜
        if len(combined) < min_papers:
            self.logger.info("扩展搜索第二轮: 生成变体关键词")
            variant_keywords = self._generate_variant_keywords(research_topic, research_direction, keywords)
            self.logger.info(f"变体关键词: {variant_keywords}")
            more = self._search_arxiv(variant_keywords, max_per_query=30)
            more = self._deduplicate_papers(more)
            combined = self._merge_papers(user_papers, more)
            self.logger.info(f"第二轮扩展后: {len(combined)} 篇")

        return combined
    
    def _generate_variant_keywords(self, title: str, direction: str, original: List[str]) -> List[str]:
        """用LLM生成更多变体关键词以扩大搜索范围"""
        orig_str = ", ".join(original)
        prompt = (
            f"论文题目：{title}\n"
            f"研究方向：{direction}\n"
            f"已有关键词：{orig_str}\n\n"
            "请生成5-8个与该研究相关的英文同义词、近义词或相关短语，用于在学术数据库中搜索论文。"
            "要求与已有关键词不同但相关。每行一个，不要编号，不要解释。"
        )
        try:
            result = self._call_llm_sync(
                messages=self._build_prompt(
                    system_prompt="你是一位学术研究专家，擅长生成学术搜索关键词。",
                    user_prompt=prompt
                ),
                max_tokens=300
            )
            keywords = [line.strip() for line in result.strip().split("\n") if line.strip()]
            cleaned = []
            for kw in keywords[:8]:
                kw = re.sub(r"^[\d\.\-\*]+\s*", "", kw).strip()
                if kw and kw not in original:
                    cleaned.append(kw)
            return cleaned if cleaned else original
        except Exception:
            return original
    
    @staticmethod
    def _extract_cited_numbers(literature_text: str) -> set:
        """解析文献综述正文，提取所有被引用的编号 [N]

        例如 "[1]"、" [2]、[3] " 中的 1, 2, 3
        """
        if not literature_text:
            return set()
        # 匹配 [1]、[2,3]、[1, 2, 3] 等各种格式
        numbers = set()
        # 匹配单独的 [N]
        for m in re.finditer(r'\[(\d+)\]', literature_text):
            numbers.add(int(m.group(1)))
        # 匹配 [N, M]、[N、M] 等复合格式
        for m in re.finditer(r'\[(\d+(?:[,、\s]+\d+)*)\]', literature_text):
            parts = re.split(r'[,、\s]+', m.group(1))
            for p in parts:
                if p.strip().isdigit():
                    numbers.add(int(p.strip()))
        return numbers

    def _format_papers(self, papers: List[Dict]) -> str:
        """将论文列表格式化为文本，供LLM参考"""
        if not papers:
            return "（未找到相关论文，请基于你的知识撰写文献综述）"
        
        lines = []
        for i, p in enumerate(papers, 1):
            authors = ", ".join(p.get("authors", [])[:3])
            if len(p.get("authors", [])) > 3:
                authors += " et al."
            summary = (p.get('summary') or p.get('abstract') or '')[:500]
            lines.append(
                f"[{i}] {p['title']}\n"
                f"    作者: {authors} ({p.get('year', '')})\n"
                f"    摘要: {summary}"
            )
        
        return "\n\n".join(lines)
    
    def _generate_review(self, title: str, direction: str, papers: List[Dict],
                          uploaded_count: int = 0, hypothesis_content: str = "") -> str:
        """生成文献综述内容（含研究假设）

        Args:
            hypothesis_content: 来自数据智能体的研究假设素材（基于实际执行的实证分析）。
                若非空，文献综述中的研究假设必须严格基于此素材生成，未执行的检验不能产生对应假设。
        """
        papers_text = self._format_papers(papers)

        # 构建「有效引用编号列表」（cite_key_map 机制），明确告知 LLM 只能使用这些编号
        cite_number_lines = []
        for i, p in enumerate(papers, 1):
            title_short = (p.get("title") or "")[:80]
            cite_number_lines.append(f"  [{i}] → {title_short}")
        cite_numbers_info = "\n".join(cite_number_lines)

        uploaded_note = ""
        if uploaded_count > 0:
            uploaded_note = (
                f"注意：上述论文列表中有 {uploaded_count} 篇由用户提供"
                "（已标注「用户提供」），"
                "**必须将这些用户提供的文献作为综述的核心分析对象**，以下arXiv论文仅为补充参考。\n"
                "要求：\n"
                "  - 对每一篇用户提供的文献进行详细评述，分析其理论观点、研究方法和核心发现\n"
                "  - 在此基础上指出现有研究的不足，引出本文的研究问题\n"
                "  - arXiv搜索到的论文仅作为补充和对比参考\n"
            )

        # 构建假设约束说明
        hypothesis_section = ""
        if hypothesis_content:
            hypothesis_section = (
                "\n\n## 【最重要】研究假设必须严格基于以下「研究假设素材」生成\n\n"
                f"以下是数据智能体根据本文实际执行的实证分析自动生成的假设素材，"
                "**所有研究假设必须严格基于以下内容生成，"
                "若某种分析未在下方素材中出现（如未做调节效应/异质性/机制检验），"
                "则不能为其编造假设**：\n\n"
                f"{hypothesis_content}\n\n"
                "---\n"
                "假设生成规则：\n"
                "1. 仔细阅读上方 4 类素材（基准回归方向 / 机制检验 / 异质性分析 / 调节效应）\n"
                "2. 仅当某种分析在素材中出现时，才为该分析生成对应的研究假设（假设 H1, H2, ...）\n"
                "3. 假设方向必须与素材中描述的方向严格一致（促进/抑制、增强/削弱、效果较好等）\n"
                "4. 假设中的自变量、因变量、中介变量、分组变量、调节变量名称必须与素材完全一致\n"
                "5. 严禁编造素材中未出现的检验结果或方向\n"
            )

        prompt = (
            f"论文题目：{title}\n"
            f"研究方向：{direction}\n\n"
            f"以下是搜索到的相关论文：\n\n{papers_text}\n\n"
            "请基于以上论文信息，撰写一篇完整的文献综述。要求：\n"
            "1. 按研究主题分小节组织\n"
            "2. **【引用格式强制要求】正文中引用论文时必须使用[1]、[2]等编号格式，例如「已有研究指出，X对企业绩效有显著正向影响[1]」。"
            "综述正文必须在每处引用位置使用[编号]标记，这是硬性要求，不可省略。**\n"
            "3. **必须仔细阅读每篇论文的摘要内容，基于摘要中的研究方法和核心发现进行评述，"
            "不能仅凭标题判断论文内容**\n"
            "4. 对于每篇引用的论文，应简要概括其研究设计（方法、样本、变量）和核心结论\n"
            "5. 涵盖该领域的经典方法和前沿进展\n"
            "6. 指出现有研究的不足和本文的切入点\n"
            "7. **在每个主题小节末尾，紧跟一个对应的研究假设**，格式为：\n"
            '   "基于以上文献分析，本文提出以下假设：\n'
            '    假设H1：自变量X对因变量Y有显著正向影响。\n'
            '    假设H2：...（如有多个假设）\n'
            "8. **文献综述中引用的文献编号必须与最终参考文献列表的编号严格一致**\n"
            "9. 语言严谨、学术化，使用中文撰写\n"
            "10. 输出Markdown格式\n"
            "11. **严禁在末尾输出「## 参考文献」或「参考文献」章节**，参考文献将由系统自动追加，"
            "你只负责撰写综述正文和文献分析部分。\n"
            "12. **【最重要】直接开始输出综述正文第一行，不要复述/回应我的指令，不要输出「好的」「好的，作为一名...」"
            "「我理解了」「下面开始」等任何确认/寒暄/自我介绍性质的语句。**\n"
            f"{uploaded_note}"
            f"{hypothesis_section}"
            f"\n\n## 有效引用编号列表（你**只能**使用以下编号，严禁使用此列表之外的编号）\n"
            f"{cite_numbers_info}\n"
            "每个编号对应上方论文列表中的一篇论文，请在引用时严格匹配编号与论文内容。"
        )

        try:
            raw = self._call_llm_sync(
                messages=self._build_prompt(
                    system_prompt=(
                        "你是一位学术文献研究专家，擅长撰写中文学术论文的文献综述部分。"
                        "你需要根据提供的论文题目和相关文献信息，撰写结构清晰、逻辑严密的文献综述。"
                        "综述应涵盖该领域的经典方法和前沿进展，指出现有研究的不足和本文的切入点。"
                        "**如果用户提供了文献，必须以用户提供的文献为核心分析对象**，对每篇用户文献进行详细评述。"
                        "Search搜索到的论文仅作补充参考。"
                        "**每个主题小节后必须提出对应的研究假设**，假设必须基于前文文献分析得出。"
                        "**【关键】如果提供了「研究假设素材」，则所有研究假设必须严格基于该素材生成，"
                        "未在素材中出现的检验类型不能为其生成假设。**"
                        "**【引用格式】正文中引用论文时**必须**在引用位置使用[1]、[2]等编号标记，例如「已有研究指出，X对企业绩效有显著正向影响[1]」。"
                        "这是硬性要求。**"
                        "**绝对禁止输出任何前置寒暄、自我介绍、确认语句，直接进入正文。**"
                    ),
                    user_prompt=prompt
                ),
                max_tokens=6000
            )
            result = self._strip_llm_prefix(raw)
            # 后处理：验证输出中是否包含引用标记 [N]
            if result and not re.search(r'\[\d+\]', result):
                self.logger.warning("文献综述输出中未检测到引用标记 [N]，重新生成...")
                # 在原有prompt末尾追加更严格的提醒
                stronger_prompt = prompt + (
                    "\n\n**【再次强调】你之前输出的文献综述正文中没有使用[1]、[2]等引用标记。"
                    "这是必须修正的硬性错误。请重新输出，确保每处引用论文的位置都使用[编号]标记，"
                    "例如「已有研究指出，X对企业绩效有显著正向影响[1]」。**"
                )
                raw2 = self._call_llm_sync(
                    messages=self._build_prompt(
                        system_prompt=(
                            "你是一位学术文献研究专家，擅长撰写中文学术论文的文献综述部分。"
                            "**【硬性要求】正文中引用论文时必须使用[1]、[2]等编号标记，这是不可省略的格式要求。**"
                        ),
                        user_prompt=stronger_prompt
                    ),
                    max_tokens=6000
                )
                result2 = self._strip_llm_prefix(raw2)
                if result2 and re.search(r'\[\d+\]', result2):
                    result = result2
                    self.logger.info("重新生成的文献综述已包含引用标记")
                else:
                    self.logger.warning("重新生成后仍未检测到引用标记，使用首次输出")
            return result
        except Exception as e:
            self.logger.error(f"文献综述生成失败: {str(e)}")
            return ""

    def _strip_llm_prefix(self, text: str) -> str:
        """剥离 LLM 输出开头的寒暄/确认/自我介绍语句"""
        if not text:
            return text
        # 常见的 LLM 前缀模式
        prefix_patterns = [
            r"^好的[，,：:。.\s]*.*?(?:我将|我会|我先|下面|接下来|以下是|开始).*?\n",
            r"^作为.*?[:：，,].*?(?:我|将|会).*?\n",
            r"^我.*?(?:理解了|了解了|会.*?做).*?\n",
            r"^下面.*?开始.*?\n",
            r"^以下是.*?文献综述.*?\n",
            r"^根据.*?(?:您的|您提供的).*?(?:我将|我会).*?\n",
        ]
        for pat in prefix_patterns:
            m = re.match(pat, text, re.DOTALL)
            if m:
                text = text[m.end():].lstrip()
                self.logger.info(f"剥离 LLM 前缀（{pat[:30]}...）")
                break
        return text
    
    def _format_references(self, papers: List[Dict]) -> str:
        """基于真实论文列表生成格式化参考文献"""
        if not papers:
            return "## 参考文献\n\n（无可用参考文献）\n"
        
        # 分离中文和英文文献
        cn_papers = []
        en_papers = []
        for p in papers:
            title = p.get("title", "")
            # 判断是否包含中文
            if re.search(r'[\u4e00-\u9fff]', title):
                cn_papers.append(p)
            else:
                en_papers.append(p)
        
        lines = ["## 参考文献\n"]
        ref_num = 1
        
        # 先中文
        for p in cn_papers:
            authors = p.get("authors", [])
            if isinstance(authors, list):
                author_str = ", ".join(authors[:3])
                if len(authors) > 3:
                    author_str += " 等"
            else:
                author_str = str(authors)
            year = p.get("year", "")
            title = p.get("title", "").replace(" (用户提供)", "")
            journal = p.get("journal", "")
            
            if journal:
                lines.append(f"[{ref_num}] {author_str} ({year}). {title}. {journal}.")
            elif year:
                lines.append(f"[{ref_num}] {author_str} ({year}). {title}.")
            else:
                lines.append(f"[{ref_num}] {author_str}. {title}.")
            ref_num += 1
        
        # 后英文
        for p in en_papers:
            authors = p.get("authors", [])
            if isinstance(authors, list):
                author_str = ", ".join(authors[:3])
                if len(authors) > 3:
                    author_str += " et al."
            else:
                author_str = str(authors)
            year = p.get("year", "")
            title = p.get("title", "").replace(" (用户提供)", "")
            journal = p.get("journal", "")
            
            if journal:
                lines.append(f"[{ref_num}] {author_str} ({year}). {title}. {journal}.")
            elif year:
                lines.append(f"[{ref_num}] {author_str} ({year}). {title}.")
            else:
                lines.append(f"[{ref_num}] {author_str}. {title}.")
            ref_num += 1
        
        return "\n\n".join(lines) + "\n"
    
    def _call_llm_sync(self, messages: List[Dict[str, str]], model: str = None,
                       temperature: float = 0.1, max_tokens: int = 2000) -> str:
        """同步调用LLM模型"""
        client = LLMClient(
            api_key=self.api_key,
            base_url=None,  # 可以从配置中读取
            model=model
        )
        return client.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model
        )
