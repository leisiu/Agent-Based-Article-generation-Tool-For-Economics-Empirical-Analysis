"""
审稿智能体
负责基于多阶段推理和证据锚定的结构化审稿
"""

import re
from typing import Optional, List
from core.base_agent import BaseAgent, Task, AgentResponse


class EditorAgent(BaseAgent):
    """审稿智能体 - 负责基于多阶段推理和证据锚定的结构化审稿
    
    功能：
    - 多阶段审稿流程（结构理解→深度分析→批判性评估）
    - 证据锚定原则（每个观点必须有稿件证据支撑）
    - 结构化审稿意见（6节标准模板）
    - 质量自检
    """
    
    def __init__(self, api_key: Optional[str] = None, model_type: str = None):
        super().__init__(
            agent_id="editor",
            role="学术审稿专家",
            capabilities=[
                "结构化审稿",
                "多阶段推理",
                "证据锚定分析",
                "优缺点评估",
                "改进建议生成"
            ],
            api_key=api_key,
            model_type=model_type
        )
    
    async def process_task(self, task: Task) -> AgentResponse:
        """处理审稿任务"""
        self.logger.info(f"开始处理审稿任务: {task.id}")
        
        try:
            # 解析任务内容
            data = self._parse_task_content(task)
            paper_content = data.get('paper_content', '')
            
            # 智能压缩论文内容（如果过长）
            if len(paper_content) > 20000:
                review_text = self._compress_for_review(paper_content)
                self.logger.info("论文较长，已智能压缩后送审")
            else:
                review_text = paper_content
            
            # 构建审稿提示词
            prompt = self._build_review_prompt(review_text)
            
            # 调用LLM进行审稿
            system_prompt = (
                "你是一位资深的学术期刊审稿人，在经济学、管理学及交叉领域"
                "具有丰富的同行评审经验。\n\n"
                "请生成结构化的审稿意见，不得包含任何分数、评级或接收/拒绝决定。\n\n"
                "=== 多阶段审稿流程 ===\n\n"
                "在撰写审稿意见之前，请内部执行以下步骤：\n"
                "第一遍（结构理解）：识别核心问题、方法架构、关键组件、"
                "实验设计和创新点声明。\n"
                "第二遍（深度分析）：追踪逻辑流程（问题→方法→实验→结论），"
                "验证内部一致性，检查数学推导正确性，评估实验设计"
                "（对照组、基线、统计严谨性、可复现性）。\n"
                "第三遍（批判性评估）：与相关工作比较新颖性，识别隐含假设和局限性，"
                "评估泛化能力（数据集规模、领域适用性、可扩展性）。\n\n"
                "=== 证据锚定原则 ===\n\n"
                "每个观点必须有来自稿件的证据支撑"
                "（如：表号/图号/公式编号/章节/页码）。\n"
                "证据锚点格式：（见表2；第4.1节；公式(5)；图3；第12页）\n"
                "缺少证据时写：「稿件中未找到直接证据。」\n\n"
                "=== 输出结构（严格按顺序，不得增删） ===\n\n"
                "1) Synopsis of the paper — 简明重述问题、方法、贡献、结果（≤150字）\n"
                "2) Summary of Review — 3-5句总结，每句带证据锚点\n"
                "3) Strengths — ≥3条，每条加粗标题+4-6子点（含证据锚点）\n"
                "4) Weaknesses — ≥3条，必须含一条数学公式评估，每条4-6子点\n"
                "5) Suggestions for Improvement — 与Weaknesses一一对应，"
                "子点含可执行步骤和可验证标准\n"
                "6) References — 仅列审稿中引用且在稿件参考文献中的条目\n\n"
                "=== 质量自检 ===\n"
                "输出前验证：六节齐全；无分数/决定；每声明有证据锚点；"
                "Strengths/Weaknesses各≥3条；Suggestions一一对应；"
                "语气客观建设性；总长1200-1800字。"
            )
            
            messages = self._build_prompt(system_prompt, prompt)
            review_comments = await self._call_llm(messages, max_tokens=8000)
            
            if review_comments:
                # 分析审稿意见
                needs_revision = self._check_needs_revision(review_comments)
                weakness_count = self._count_section_items(review_comments, "Weaknesses")
                strength_count = self._count_section_items(review_comments, "Strengths")
                
                self.logger.info(
                    f"审稿完成：{strength_count} 条优点，{weakness_count} 条缺点，"
                    f"结论：{'需要修改' if needs_revision else '质量较好'}"
                )
                
                response = self.create_response(
                    task=task,
                    content=review_comments,
                    metadata={
                        "review_type": "structured",
                        "needs_revision": needs_revision,
                        "strength_count": strength_count,
                        "weakness_count": weakness_count
                    }
                )
                self.logger.info(f"完成审稿任务: {task.id}")
                return response
            else:
                raise ValueError("LLM调用失败，无法生成审稿意见")
            
        except Exception as e:
            self.logger.error(f"审稿失败: {str(e)}")
            return self.create_response(
                task=task,
                content=f"审稿失败: {str(e)}",
                metadata={"error": True, "error_type": "review_error"},
                success=False,
                error_message=str(e)
            )
    
    def _build_review_prompt(self, paper_content: str) -> str:
        """构建审稿提示词"""
        prompt = (
            f"请对以下学术论文进行结构化审稿：\n\n"
            f"论文内容：\n\n{paper_content}\n\n"
            "请严格按照六节模板（Synopsis → Summary → Strengths → "
            "Weaknesses → Suggestions → References）输出结构化审稿意见。\n"
            "每个观点必须锚定到稿件中的具体位置（表号/图号/公式/章节/页码）。"
        )
        
        return prompt.strip()
    
    def _compress_for_review(self, text: str) -> str:
        """智能压缩：保留结构 + 每节前800字 + 所有公式和表格环境"""
        lines = text.split("\n")
        result = []
        current_section = []
        
        for line in lines:
            stripped = line.strip()
            # 检测章节标题（Markdown格式）
            if stripped.startswith("##") or stripped.startswith("#"):
                if current_section:
                    compressed = self._compress_section(current_section)
                    result.append(compressed)
                    current_section = []
                result.append(line)
            else:
                current_section.append(line)
        
        if current_section:
            compressed = self._compress_section(current_section)
            result.append(compressed)
        
        return "\n".join(result)
    
    def _compress_section(self, lines: List[str]) -> str:
        """压缩单个章节：保留前800字 + 所有公式/表格/图片环境"""
        body = "\n".join(lines)
        # 提取所有数学环境和表格环境（审稿需要检查这些）
        important_envs = re.findall(
            r"(\$[^$]+\$|\$\$[^$]+\$\$|\|[^|]+\||```[^`]*```)",
            body,
            re.DOTALL,
        )
        # 前800字 + 重要环境
        compressed = body[:800]
        if len(body) > 800:
            compressed += "\n\n... [正文省略] ...\n"
            # 附加未被包含在前800字中的重要环境
            for env in important_envs:
                if env not in compressed:
                    compressed += "\n" + env
        return compressed
    
    def _check_needs_revision(self, comments: str) -> bool:
        """基于 Weaknesses 数量和严重程度判断是否需要修改"""
        weakness_count = self._count_section_items(comments, "Weaknesses")
        # 有缺点就需要修改
        if weakness_count > 0:
            return True
        # 兜底：检查关键词
        revision_keywords = [
            "严重不足", "重大缺陷", "关键问题", "fundamental",
            "critical", "major concern",
        ]
        lower = comments.lower()
        return any(kw.lower() in lower for kw in revision_keywords)
    
    def _count_section_items(self, comments: str, section_name: str) -> int:
        """统计审稿意见中某节的条目数（通过加粗标题计数）"""
        # 找到对应节的内容
        pattern = rf"(?:#+\s*\d*\)?\s*)?{section_name}\b(.*?)(?=(?:#+\s*\d*\)?\s*)?(?:Synopsis|Summary|Strengths|Weaknesses|Suggestions|References)\b|\Z)"
        match = re.search(pattern, comments, re.DOTALL | re.IGNORECASE)
        if not match:
            return 0
        section_text = match.group(1)
        # 统计加粗标题数量（**标题** 或 __标题__）
        bold_patterns = len(re.findall(r"\*\*[^*]+\*\*|__[^_]+__", section_text))
        return max(bold_patterns, 1) if section_text.strip() else 0
