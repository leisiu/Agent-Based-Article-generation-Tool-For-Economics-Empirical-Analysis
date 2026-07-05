"""
基础智能体类定义
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import json
from core.llm_client import LLMClient


@dataclass
class Task:
    """任务数据类"""
    id: str
    type: str
    content: str
    metadata: Dict[str, Any]


@dataclass
class AgentResponse:
    """智能体响应数据类"""
    agent_id: str
    task_id: str
    content: str
    metadata: Dict[str, Any]
    timestamp: float
    success: bool = True
    error_message: Optional[str] = None


class BaseAgent(ABC):
    """智能体基类
    
    所有智能体的抽象基类，提供统一的接口和通用功能。
    """
    
    def __init__(self, agent_id: str, role: str, capabilities: List[str], api_key: str = None, model_type: str = None):
        self.agent_id = agent_id
        self.role = role
        self.capabilities = capabilities
        self.api_key = api_key
        self.model_type = model_type or "deepseek"
        self.logger = logging.getLogger(f"{self.__class__.__name__}[{agent_id}]")
        self.logger.setLevel(logging.INFO)
    
    @abstractmethod
    async def process_task(self, task: Task) -> AgentResponse:
        """处理任务的抽象方法"""
        pass
    
    def create_response(
        self, 
        task: Task, 
        content: str, 
        metadata: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> AgentResponse:
        """创建响应对象"""
        return AgentResponse(
            agent_id=self.agent_id,
            task_id=task.id,
            content=content,
            metadata=metadata or {},
            timestamp=time.time(),
            success=success,
            error_message=error_message
        )
    
    def _parse_task_content(self, task: Task) -> Dict[str, Any]:
        """解析任务内容"""
        try:
            if isinstance(task.content, str):
                return json.loads(task.content)
            return task.content
        except json.JSONDecodeError as e:
            self.logger.error(f"任务内容解析失败: {e}")
            return {}
    
    def _build_prompt(self, system_prompt: str, user_prompt: str) -> List[Dict[str, str]]:
        """构建标准的对话提示词"""
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    
    async def _call_llm(self, messages: List[Dict[str, str]], model: str = None, 
                        temperature: float = 0.1, max_tokens: int = 2000) -> Optional[str]:
        """调用LLM模型"""
        try:
            client = LLMClient(
                api_key=self.api_key,
                model=model,
                model_type=self.model_type
            )
            return client.chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model
            )
        except ValueError:
            raise
        except Exception as e:
            self.logger.error(f"LLM调用失败: {str(e)}")
            raise RuntimeError(f"LLM调用失败: {str(e)}。请检查API Key是否正确，或稍后重试。")
    

