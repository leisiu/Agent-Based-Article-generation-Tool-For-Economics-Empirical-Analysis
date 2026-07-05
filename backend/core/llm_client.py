"""
LLM调用模块
提供统一的LLM调用接口，支持多种国内主流大模型
"""

import logging
from typing import Dict, Any, Optional, List
import requests


# 国内主流大模型注册表（支持 OpenAI 兼容格式）
MODEL_REGISTRY = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-chat", "deepseek-reasoner", "deepseek-v4-flash", "deepseek-v4-pro"],
        "default_model": "deepseek-chat",
        "api_key_name": "deepseekApiKey",
        "model_field_name": "deepseekModel",
    },
    "qwen": {
        "name": "通义千问 (阿里云)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo", "qwen3.5-plus", "qwen3-max", "qwen3.6-plus"],
        "default_model": "qwen-plus",
        "api_key_name": "qwenApiKey",
        "model_field_name": "qwenModel",
    },
    "kimi": {
        "name": "Kimi (月之暗面)",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["kimi-k2.6", "kimi-k2.5", "moonshot-v1-128k"],
        "default_model": "kimi-k2.6",
        "api_key_name": "kimiApiKey",
        "model_field_name": "kimiModel",
    },
    "glm": {
        "name": "智谱GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-plus", "glm-4-air", "glm-4-flash", "glm-5.2"],
        "default_model": "glm-4-plus",
        "api_key_name": "glmApiKey",
        "model_field_name": "glmModel",
    },
    "doubao": {
        "name": "豆包 (字节跳动)",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-pro-32k", "doubao-lite-128k"],
        "default_model": "doubao-pro-32k",
        "api_key_name": "doubaoApiKey",
        "model_field_name": "doubaoModel",
    },
    "custom": {
        "name": "自定义 (OpenAI兼容)",
        "base_url": "",
        "models": [],
        "default_model": "",
        "api_key_name": "customApiKey",
        "model_field_name": "customModel",
    }
}


def get_model_registry():
    """获取模型注册表（前端显示用）"""
    registry = {}
    for key, config in MODEL_REGISTRY.items():
        registry[key] = {
            "name": config["name"],
            "models": config["models"],
            "default_model": config["default_model"],
            "api_key_name": config["api_key_name"],
            "model_field_name": config["model_field_name"],
        }
    return registry


class LLMClient:
    """统一的LLM调用客户端，支持多种国内主流大模型"""
    
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None, model_type: str = None):
        self.api_key = api_key
        self.model = model
        self.model_type = model_type
        self.logger = logging.getLogger("LLMClient")
        # 如果提供了 model_type 但没有 base_url，从注册表中查找
        if model_type and model_type in MODEL_REGISTRY and not base_url:
            self.base_url = MODEL_REGISTRY[model_type]["base_url"]
        else:
            self.base_url = base_url
    
    def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.1, 
        max_tokens: int = 2000,
        model: str = None
    ) -> str:
        """调用LLM模型生成回复"""
        if not self.api_key or not self.api_key.strip():
            raise ValueError("未配置API密钥，请在系统设置中配置API Key")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": model or self.model or "deepseek-chat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            
            return result["choices"][0]["message"]["content"]
        
        except requests.exceptions.RequestException as e:
            self.logger.error(f"LLM调用失败: {str(e)}")
            raise RuntimeError(f"LLM调用失败: {str(e)}。请检查API Key是否正确，或稍后重试。")


# 全局LLM客户端实例
llm_client = LLMClient()
