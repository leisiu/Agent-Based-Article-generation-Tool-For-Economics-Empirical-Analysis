"""
质量审稿智能体
负责对论文进行基于证据锚定的多维度学术质量评估
"""

import re
from typing import Dict, Any, Optional
from core.base_agent import BaseAgent, Task, AgentResponse


class QualityReviewerAgent(BaseAgent):
    """质量审稿智能体 - 负责对论文进行基于证据锚定的多维度学术质量评估
    
    功能：
    - 基于证据锚定的多维度学术质量评估
    - 8个评估维度评分（1-10分）
    - 提供具体改进建议
    - 生成质量评估摘要
    """
    
    def __init__(self, api_key: Optional[str] = None, model_type: str = None):
        super().__init__(
            agent_id="quality_reviewer",
            role="学术审稿专家",
            capabilities=[
                "学术质量评估",
                "多维度评分",
                "证据锚定分析",
                "改进建议生成",
                "学术规范检查"
            ],
            api_key=api_key
        )
    
    async def process_task(self, task: Task) -> AgentResponse:
        """处理质量评审任务"""
        self.logger.info(f"开始处理质量评审任务: {task.id}")
        
        try:
            # 解析任务内容
            data = self._parse_task_content(task)
            paper_content = data.get('paper_content', '')
            empirical_results = data.get('empirical_results', {})
            
            # 智能压缩论文内容（如果过长）
            if len(paper_content) > 20000:
                eval_text = self._compress_for_evaluation(paper_content)
                self.logger.info("论文较长，已智能压缩后评估")
            else:
                eval_text = paper_content
            
            # 构建评审提示词
            prompt = self._build_review_prompt(eval_text, empirical_results)
            
            # 调用LLM进行评审
            system_prompt = (
                "你是一位资深的学术论文评审专家，在经济学、管理学及交叉领域"
                "具有丰富的论文评估经验。\n\n"
                "=== 评估维度 ===\n\n"
                "请从以下8个维度对论文进行全面评估，每个维度给出1-10分：\n"
                "1. 学术规范性（格式、引用、术语使用、排版）\n"
                "2. 创新性（研究问题的新颖性、方法创新、贡献独特性）\n"
                "3. 完整性（结构完整、逻辑连贯、论证充分）\n"
                "4. 技术深度（方法描述清晰度、推导严谨性、设计合理性）\n"
                "5. 实验质量（实验设计、对比分析、统计显著性、可复现性）\n"
                "6. 写作质量（语言表达、可读性、专业性、段落衔接）\n"
                "7. 文献综述（覆盖面、时效性、相关性、与本文工作的关联分析）\n"
                "8. 数据与公式（符号一致性、推导正确性、变量定义完整性）\n\n"
                "=== 证据锚定原则 ===\n\n"
                "每个评价观点必须锚定到稿件中的具体位置：\n"
                "- 引用格式：（见表2；第4.1节；公式(5)；图3；第12页）\n"
                "- 如果缺少证据：「稿件中未找到直接证据。」\n\n"
                "=== 输出格式 ===\n\n"
                "对每个维度输出：\n"
                "- 维度名称：X分/10\n"
                "- 评价（2-4句，含证据锚点）\n"
                "- 具体改进建议（可执行、可验证）\n\n"
                "最后给出：\n"
                "- 总分：X分/10（8个维度的加权平均）\n"
                "- 综合评价（3-5句总结，含关键证据锚点）\n"
                "- 优先修改清单（按重要性排序的3-5条最关键改进项）"
            )
            
            messages = self._build_prompt(system_prompt, prompt)
            review_result = await self._call_llm(messages, max_tokens=6000)
            
            if review_result:
                # 解析评分
                scores = self._parse_scores(review_result)
                
                response = self.create_response(
                    task=task,
                    content=review_result,
                    metadata={
                        "review_type": "llm_generated",
                        "scores": scores,
                        "score_summary": self._generate_score_summary(scores)
                    }
                )
                self.logger.info(f"完成质量评审任务: {task.id}")
                return response
            else:
                raise ValueError("LLM调用失败，无法生成评审意见")
            
        except Exception as e:
            self.logger.error(f"质量评审失败: {str(e)}")
            return self.create_response(
                task=task,
                content=f"质量评审失败: {str(e)}",
                metadata={"error": True, "error_type": "review_error"},
                success=False,
                error_message=str(e)
            )
    
    def _build_review_prompt(self, paper_content: str, empirical_results: Dict[str, Any]) -> str:
        """构建质量评审提示词"""
        prompt = (
            f"请对以下学术论文进行全面质量评估：\n\n"
            f"论文内容：\n\n{paper_content}\n\n"
            f"实证结果数据：\n\n{str(empirical_results)[:2000]}\n\n"
            "请按照8个维度对该论文进行全面质量评估。\n"
            "每个评价观点必须锚定到稿件中的具体位置（表号/图号/公式/章节）。"
        )
        
        return prompt.strip()
    
    def _compress_for_evaluation(self, text: str) -> str:
        """智能压缩：保留结构 + 每节前800字"""
        lines = text.split("\n")
        result = []
        current_section = []
        
        for line in lines:
            stripped = line.strip()
            # 检测章节标题（Markdown格式）
            if stripped.startswith("##") or stripped.startswith("#"):
                if current_section:
                    body = "\n".join(current_section)
                    compressed = body[:800]
                    if len(body) > 800:
                        compressed += "\n\n... [内容省略] ...\n"
                    result.append(compressed)
                    current_section = []
                result.append(line)
            else:
                current_section.append(line)
        
        if current_section:
            body = "\n".join(current_section)
            compressed = body[:800]
            if len(body) > 800:
                compressed += "\n\n... [内容省略] ..."
            result.append(compressed)
        
        return "\n".join(result)
    
    def _parse_scores(self, report: str) -> Dict[str, float]:
        """从评估报告中解析评分"""
        scores = {}
        dimensions = [
            "学术规范性",
            "创新性",
            "完整性",
            "技术深度",
            "实验质量",
            "写作质量",
            "文献综述",
            "数据与公式",
        ]
        
        for dim in dimensions:
            # 匹配 "维度：X分" 或 "维度：X/10" 或 "维度：X 分"
            pattern = rf"{dim}[：:]\s*(\d+(?:\.\d+)?)\s*[分/]"
            match = re.search(pattern, report)
            if match:
                scores[dim] = float(match.group(1))
        
        # 尝试提取总分
        total_patterns = [
            r"总[体分][：:]\s*(\d+(?:\.\d+)?)\s*[分/]",
            r"总[体分][：:]\s*(\d+(?:\.\d+)?)",
        ]
        for pattern in total_patterns:
            match = re.search(pattern, report)
            if match:
                scores["总分"] = float(match.group(1))
                break
        
        return scores
    
    def _generate_score_summary(self, scores: Dict[str, float]) -> str:
        """生成质量评估摘要"""
        if not scores:
            return "未能解析评分"
        
        lines = ["论文质量评估摘要："]
        weak_dims = []
        
        for dim, score in scores.items():
            if dim != "总分":
                level = self._get_score_level(score)
                lines.append(f"  {dim}: {score:.1f}/10 ({level})")
                if score < 7:
                    weak_dims.append(dim)
        
        if "总分" in scores:
            total = scores["总分"]
            level = self._get_score_level(total)
            lines.append(f"\n  总体评分: {total:.1f}/10 ({level})")
        
        if weak_dims:
            lines.append(f"\n  需重点改进: {', '.join(weak_dims)}")
        
        return "\n".join(lines)
    
    def _get_score_level(self, score: float) -> str:
        """根据分数返回等级"""
        if score >= 9:
            return "优秀"
        elif score >= 8:
            return "良好"
        elif score >= 7:
            return "中等"
        elif score >= 6:
            return "及格"
        else:
            return "需改进"
