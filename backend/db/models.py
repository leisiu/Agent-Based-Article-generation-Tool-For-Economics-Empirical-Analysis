from sqlalchemy import Column, String, Text, DateTime, Enum, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

Base = declarative_base()

class ProjectDB(Base):
    """项目数据库模型"""
    __tablename__ = "projects"
    
    id = Column(String(36), primary_key=True, index=True, comment="项目ID")
    name = Column(String(255), nullable=False, comment="项目名称")
    description = Column(Text, comment="项目描述")
    data_path = Column(String(500), comment="数据文件路径")
    original_command = Column(Text, comment="原始实证命令")
    status = Column(String(50), default="uploaded", comment="项目状态")
    model_type = Column(String(50), default="doubao", comment="使用的AI模型类型")
    api_key = Column(String(255), comment="API密钥（加密存储）")
    result_path = Column(String(500), comment="结果文件路径")
    empirical_results = Column(JSON, comment="实证计算结果")
    paper_content = Column(Text, comment="AI生成的论文内容")
    review_comments = Column(Text, comment="审稿意见")
    quality_report = Column(Text, comment="质量评估报告")
    quality_scores = Column(JSON, comment="质量评分")
    outline = Column(JSON, comment="论文大纲")
    variable_config = Column(JSON, comment="用户变量配置（用于重试/恢复）")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), comment="更新时间")
    completed_at = Column(DateTime(timezone=True), comment="完成时间")

class ProjectCreate(BaseModel):
    """创建项目请求模型"""
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    data_path: Optional[str] = None
    model_type: str = "deepseek"
    api_key: Optional[str] = None

class ProjectUpdate(BaseModel):
    """更新项目请求模型"""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    result_path: Optional[str] = None
    empirical_results: Optional[Dict[str, Any]] = None
    paper_content: Optional[str] = None
    completed_at: Optional[datetime] = None

class ProjectResponse(BaseModel):
    """项目响应模型"""
    id: str
    name: str
    description: Optional[str] = None
    status: str
    model_type: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True, "protected_namespaces": ()}
