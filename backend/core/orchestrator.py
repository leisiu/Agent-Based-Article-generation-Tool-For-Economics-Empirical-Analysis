"""
多智能体协调器
负责管理智能体间的协作流程
"""

import asyncio
import logging
import json
import re
from typing import Dict, Any, List

from multi_agent.data_analyst_agent import DataAnalystAgent
from multi_agent.literature_review_agent import LiteratureReviewAgent
from multi_agent.academic_writer_agent import AcademicWriterAgent
from multi_agent.quality_reviewer_agent import QualityReviewerAgent
from multi_agent.editor_agent import EditorAgent
from multi_agent.standard_outline import get_standard_outline
from core.base_agent import Task


class MultiAgentOrchestrator:
    """多智能体协调器 - 管理智能体间的协作流程"""

    def __init__(self, api_key=None, model_type=None):
        self.agents = {
            'data_analyst': DataAnalystAgent(api_key=api_key, model_type=model_type),
            'literature_review': LiteratureReviewAgent(api_key=api_key, model_type=model_type),
            'academic_writer': AcademicWriterAgent(api_key=api_key, model_type=model_type),
            'quality_reviewer': QualityReviewerAgent(api_key=api_key, model_type=model_type),
            'editor': EditorAgent(api_key=api_key, model_type=model_type)
        }
        self.logger = logging.getLogger(self.__class__.__name__)

    def _parse_uploaded_literature(self, literature_content: str) -> List[Dict[str, Any]]:
        """解析用户上传的 RefWorks 标签格式文献内容

        格式示例：
            RT Journal Article
            A1 作者1;作者2
            T1 文章标题
            JF 期刊名
            YR 年份
            IS 卷数
            VO 
            OP 页码
            K1 关键词
            AB 摘要内容
            SN 1004-5937
            LK https://...

        Returns:
            论文列表，每个论文包含 title, authors, year, abstract, journal 等字段
        """
        TAG_MAP = {
            "t1": "title",
            "a1": "authors",
            "yr": "year",
            "jf": "journal",
            "ab": "abstract",
            "k1": "keywords",
            "lk": "link",
            "sn": "issn",
        }

        papers = []
        paper = {}
        line_count = 0

        for line in literature_content.strip().split("\n"):
            stripped = line.strip()
            line_count += 1
            if not stripped:
                # 空行 = 一条文献结束
                if paper.get("title"):
                    papers.append(paper)
                paper = {}
                continue

            # 匹配 RefWorks 标签: "T1 Title", "A1 Author1;Author2"
            m = re.match(r"^([A-Za-z0-9]+)\s+(.*)", stripped)
            if not m:
                continue

            tag = m.group(1).strip().lower()
            value = m.group(2).strip()
            mapped = TAG_MAP.get(tag)

            if mapped == "authors":
                # 支持两种格式：
                #   A1 姓名1;姓名2  (一行多个作者)
                #   A1 姓名1         (多行，每个作者一行)
                new_authors = [a.strip() for a in value.split(";") if a.strip()]
                existing = paper.get("authors", [])
                existing.extend(new_authors)
                paper["authors"] = existing
                self.logger.info(f"  解析作者: {new_authors}")
            elif mapped:
                paper[mapped] = value

        # 最后一条文献
        if paper.get("title"):
            papers.append(paper)

        self.logger.info(f"RefWorks解析结果: 共读入 {line_count} 行, 解析出 {len(papers)} 篇文献")
        for i, p in enumerate(papers):
            self.logger.info(f"  [{i+1}] {p.get('title','?')[:80]} | 作者: {p.get('authors',[])} | 年份: {p.get('year','')}")
        return papers

    @staticmethod
    def _extract_variable_keywords(empirical_results: Dict[str, Any]) -> List[str]:
        """从实证分析结果中提取变量名，作为文献搜索关键词"""
        keywords = set()

        # 从 regression 结果中提取变量名
        reg = empirical_results.get("regression", {})
        if isinstance(reg, dict):
            for model_name, model_result in reg.items():
                if not isinstance(model_result, dict):
                    continue
                # 提取 dependent_var
                dep_var = model_result.get("dependent_var")
                if dep_var:
                    keywords.add(dep_var)
                # 提取 coefficients 中的变量名
                coefs = model_result.get("coefficients", {})
                if isinstance(coefs, dict):
                    for var_name in coefs:
                        if var_name != "_cons" and var_name != "const":
                            keywords.add(var_name)
                # 从 methods 中提取
                methods = model_result.get("methods", {})
                if isinstance(methods, dict):
                    for mt, single in methods.items():
                        if not isinstance(single, dict):
                            continue
                        dv = single.get("dependent_var")
                        if dv:
                            keywords.add(dv)
                        c = single.get("coefficients", {})
                        if isinstance(c, dict):
                            for vn in c:
                                if vn not in ("_cons", "const"):
                                    keywords.add(vn)

        # 从 heterogeneity 中提取分组变量
        het = empirical_results.get("heterogeneity", {})
        if isinstance(het, dict):
            methods = het.get("methods", {})
            if isinstance(methods, dict):
                for md in methods.values():
                    if isinstance(md, dict):
                        gv = md.get("group_var")
                        if gv:
                            keywords.add(gv)
                        # 兼容数组格式
                        for g in md.get("group_vars") or []:
                            if g:
                                keywords.add(g)

        # 从 moderation 中提取调节变量
        mod = empirical_results.get("moderation", {})
        if isinstance(mod, dict):
            methods = mod.get("methods", {})
            if isinstance(methods, dict):
                for md in methods.values():
                    if isinstance(md, dict):
                        mv = md.get("moderator")
                        if mv:
                            keywords.add(mv)
                        # 兼容数组格式
                        for m in md.get("moderator_vars") or []:
                            if m:
                                keywords.add(m)

        # 从 mechanism 中提取中介变量
        mech = empirical_results.get("mechanism", {})
        if isinstance(mech, dict):
            methods = mech.get("methods", {})
            if isinstance(methods, dict):
                for md in methods.values():
                    if isinstance(md, dict):
                        mv = md.get("mediator")
                        if mv:
                            keywords.add(mv)
                        # 兼容数组格式
                        for m in md.get("mediator_vars") or []:
                            if m:
                                keywords.add(m)

        result = sorted(kw for kw in keywords if kw)
        return result if result else []

    async def execute_workflow(self, empirical_results: Dict[str, Any], command: str, literature_content: str = None) -> Dict[str, Any]:
        """执行完整的多智能体工作流

        Returns:
            Dict[str, Any]: 包含论文、审稿意见、质量报告等完整结果
        """
        self.logger.info("开始多智能体协作论文生成")

        # 任务ID生成器
        import uuid
        task_counter = 0

        def create_task(task_type: str, content: str) -> Task:
            nonlocal task_counter
            task_counter += 1
            return Task(
                id=f"task_{task_counter}_{uuid.uuid4().hex[:8]}",
                type=task_type,
                content=content,
                metadata={}
            )

        try:
            # 步骤1: 数据分析
            self.logger.info("步骤1: 数据分析智能体处理中...")
            analysis_input = {
                'empirical_results': empirical_results,
                'command': command
            }
            analysis_task = create_task("data_analysis", json.dumps(analysis_input))
            analysis_response = await self.agents['data_analyst'].process_task(analysis_task)
            analysis_result = analysis_response.content
            # 从元数据中提取预生成的实证分析章节（含真实数据，无需LLM编造）
            data_analyst_meta = analysis_response.metadata or {}
            empirical_chapter = data_analyst_meta.get("empirical_chapter", "")
            # 提取假设素材（由数据智能体根据实际执行的实证分析自动生成）
            hypothesis_content = data_analyst_meta.get("hypothesis_content", "")
            if hypothesis_content:
                self.logger.info("📋 已从数据智能体获取研究假设素材，将用于约束文献综述")

            # 步骤1.5: 文献综述（如果有用户上传的文献，优先使用 + 搜索补齐）
            literature_review = ""
            literature_references = ""

            # 从 empirical_results 中提取变量名，作为文献搜索关键词
            variable_keywords = self._extract_variable_keywords(empirical_results)
            self.logger.info(f"📋 已提取实证变量名作为文献搜索关键词: {variable_keywords}")

            # 通用 lit_input：含 hypothesis_content，供 LLM 严格按素材生成研究假设
            if literature_content:
                self.logger.info("步骤1.5: 解析用户上传的文献内容...")
                # 将用户上传的文献内容传递给 LiteratureReviewAgent，由其搜索补齐
                uploaded_papers = self._parse_uploaded_literature(literature_content)
                lit_input = {
                    'research_topic': command,
                    'keywords': variable_keywords,
                    'research_direction': command,
                    'uploaded_papers': uploaded_papers,
                    'hypothesis_content': hypothesis_content,
                }
                lit_task = create_task("literature_review", json.dumps(lit_input))
                lit_response = await self.agents['literature_review'].process_task(lit_task)
                literature_review = lit_response.content
            else:
                self.logger.info("步骤1.5: 文献综述智能体搜索文献中...")
                lit_input = {
                    'research_topic': command,
                    'keywords': variable_keywords,
                    'research_direction': command,
                    'hypothesis_content': hypothesis_content,
                }
                lit_task = create_task("literature_review", json.dumps(lit_input))
                lit_response = await self.agents['literature_review'].process_task(lit_task)
                literature_review = lit_response.content
            # 从文献综述agent的metadata中提取真实参考文献列表
            lit_meta = lit_response.metadata or {}
            literature_references = lit_meta.get("references_text", "")

            # 步骤2: 使用标准化大纲模板（不再调用 outline_agent，避免 LLM 自由发挥污染正文）
            self.logger.info("步骤2: 使用标准化论文大纲模板...")
            outline_data = get_standard_outline(command=command)
            self.logger.info(f"标准化大纲已就绪，共 {len(outline_data.get('sections', []))} 个固定章节")

            # 步骤3: 学术写作（按标准化大纲逐节串行生成）
            self.logger.info("步骤3: 学术写作智能体按标准化大纲逐节生成...")
            writing_input = {
                'analysis_result': analysis_result,
                'literature_review': literature_review,
                'empirical_results': empirical_results,
                'command': command,
                'outline_data': outline_data,
                'empirical_chapter': empirical_chapter,
                'literature_references': literature_references,
            }
            writing_task = create_task("academic_writing", json.dumps(writing_input))
            writing_response = await self.agents['academic_writer'].process_task(writing_task)

            # 步骤4: 质量评审
            self.logger.info("步骤4: 质量审稿智能体处理中...")
            review_input = {
                'paper_content': writing_response.content,
                'empirical_results': empirical_results
            }
            review_task = create_task("quality_review", json.dumps(review_input))
            review_response = await self.agents['quality_reviewer'].process_task(review_task)

            # 步骤5: 编辑润色（结构化审稿）
            self.logger.info("步骤5: 审稿智能体处理中...")
            editing_input = {
                'paper_content': writing_response.content,
            }
            editing_task = create_task("editing", json.dumps(editing_input))
            editing_response = await self.agents['editor'].process_task(editing_task)

            # 步骤6: 根据审稿意见和质量报告修改论文
            self.logger.info("步骤6: 根据审稿意见修改论文...")
            revised_paper = await self.agents['academic_writer'].run_revision(
                paper_content=writing_response.content,
                review_comments=editing_response.content,
                quality_report=review_response.content,
            )

            # 组装完整结果
            final_result = {
                'paper': revised_paper,  # 修改后的论文正文
                'original_paper': writing_response.content,  # 原始论文
                'review_comments': editing_response.content,  # 审稿意见
                'quality_report': review_response.content,  # 质量报告
                'quality_scores': review_response.metadata.get('scores', {}),  # 质量评分
                'outline': outline_data  # 大纲
            }

            self.logger.info("多智能体协作完成")
            return final_result

        except Exception as e:
            self.logger.error(f"多智能体协作失败: {str(e)}")
            raise
