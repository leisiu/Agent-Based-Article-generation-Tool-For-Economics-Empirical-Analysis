"""
多智能体论文生成器
主要接口类
"""

import asyncio
from typing import Dict, Any
from .orchestrator import MultiAgentOrchestrator


class MultiAgentPaperGenerator:
    """多智能体论文生成器 - 主要接口类"""
    
    def __init__(self, model_type: str = "deepseek", api_key: str = ""):
        self.model_type = model_type
        self.api_key = api_key
        self.orchestrator = MultiAgentOrchestrator(api_key=api_key, model_type=model_type)
    
    async def generate_paper_async(
        self,
        empirical_results: Dict[str, Any],
        command: str,
        literature_content: str = None
    ) -> Dict[str, Any]:
        """异步生成论文

        Args:
            empirical_results: 实证分析结果
            command: 用户研究指令
            literature_content: 用户上传的文献内容（可选）

        Returns:
            Dict[str, Any]: 包含论文、审稿意见、质量报告等完整结果
        """
        return await self.orchestrator.execute_workflow(
            empirical_results, command, literature_content=literature_content
        )

    def generate_paper(
        self,
        empirical_results: Dict[str, Any],
        command: str,
        literature_content: str = None
    ) -> Dict[str, Any]:
        """同步生成论文接口

        Args:
            empirical_results: 实证分析结果
            command: 用户研究指令
            literature_content: 用户上传的文献内容（可选）

        Returns:
            Dict[str, Any]: 包含论文、审稿意见、质量报告等完整结果
        """
        # 创建新的事件循环或使用现有的
        try:
            loop = asyncio.get_running_loop()
            # 如果已经在事件循环中，创建新的线程来运行
            import threading
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor() as executor:
                future = executor.submit(
                    lambda: asyncio.run(
                        self.generate_paper_async(empirical_results, command, literature_content)
                    )
                )
                return future.result()
        except RuntimeError:
            # 没有运行中的事件循环，直接运行
            return asyncio.run(
                self.generate_paper_async(empirical_results, command, literature_content)
            )


def create_multi_agent_generator(model_type: str = "deepseek", api_key: str = ""):
    """创建多智能体论文生成器的工厂函数"""
    return MultiAgentPaperGenerator(model_type, api_key)
