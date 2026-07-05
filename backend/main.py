from fastapi import FastAPI, File, UploadFile, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uvicorn
import os
import tempfile
import shutil
import uuid
import logging
import json
import pandas as pd

# Import custom modules
from data_processor.preprocessor import DataPreprocessor
from parser.command_parser import CommandParser
from empirical_models.empirical_engine import EmpiricalEngine
from db.database import Database
from db.models import ProjectCreate
from core.llm_client import get_model_registry

app = FastAPI(
    title="经管实证AI自动论文生成工具",
    description="本地部署、开源免费、可二次开发的经管实证自动论文生成工具",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
db = Database()

# Initialize logger
logger = logging.getLogger(__name__)

class EmpiricalRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    command: Optional[str] = None
    model_type: str = "deepseek"
    api_key: Optional[str] = None
    project_id: Optional[str] = None
    dependent_var: Optional[str] = None
    independent_vars: Optional[List[str]] = []
    control_vars: Optional[List[str]] = []
    fixed_effects: Optional[Dict[str, str]] = {}
    cluster_var: Optional[str] = None
    model: Optional[str] = "ols"
    missing_method: Optional[str] = "drop"
    outlier_method: Optional[str] = "winsorize"
    regression_models: Optional[List[str]] = None
    robustness_tests: Optional[List[Dict[str, Any]]] = None
    test_types: Optional[List[str]] = None
    # 新增模块化参数
    moderation_var: Optional[str] = None          # 调节效应变量
    heterogeneity_var: Optional[str] = None       # 异质性分组变量
    mechanism_var: Optional[str] = None            # 机制检验变量
    # ====== 多模型/多方法新结构 ======
    baseline_models: Optional[List[Dict[str, Any]]] = None
    # 每个元素结构:
    #   {
    #     "name": "模型1",
    #     "dependent_var": "Y",
    #     "independent_vars": ["X1","X2"],
    #     "control_vars": ["C1"],
    #     "fixed_effects": {"企业代码": "true", "年度": "true"},
    #     "cluster_var": "企业代码",
    #     "regression_methods": ["fe", "ols"],
    #     "model": "fe",
    #     "missing_method": "drop"
    #   }
    heterogeneity_methods: Optional[List[Dict[str, Any]]] = None
    # 每个元素结构:
    #   {
    #     "method": "subgroup" | "median_split" | "interaction",
    #     "group_var": "...",
    #     "dependent_var": "Y",
    #     "independent_vars": ["X1"],
    #     "control_vars": [...],
    #     "fixed_effects": {...},
    #     "cluster_var": "...",
    #     "regression_methods": [...],
    #     "model": "fe"
    #   }
    mechanism_methods: Optional[List[Dict[str, Any]]] = None
    # 每个元素结构:
    #   {
    #     "method": "baron_kenny" | "jiang_ting",
    #     "mediator_var": "M",
    #     "dependent_var": "Y",
    #     "independent_vars": ["X1"],
    #     "control_vars": [...],
    #     "fixed_effects": {...},
    #     "cluster_var": "...",
    #     "regression_methods": [...],
    #     "model": "fe"
    #   }
    moderation_methods: Optional[List[Dict[str, Any]]] = None
    # 每个元素结构:
    #   {
    #     "method": "interaction",
    #     "moderator_var": "M",
    #     "dependent_var": "Y",
    #     "independent_vars": ["X1"],
    #     "control_vars": [...],
    #     "fixed_effects": {...},
    #     "cluster_var": "...",
    #     "regression_methods": [...],
    #     "model": "fe",
    #     "applied_baseline_models": [{name, dependent_var, ...}, ...]
    #   }

class AIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    project_id: Optional[str] = None

@app.get("/api/health")
async def health():
    return {"message": "经管实证AI自动论文生成工具后端服务"}

# 创建数据上传目录
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload-data", response_model=AIResponse)
async def upload_data(file: UploadFile = File(...), project_name: str = Form(None)):
    try:
        # 创建项目专属目录
        project_id = str(uuid.uuid4())
        project_dir = os.path.join(UPLOAD_DIR, project_id)
        os.makedirs(project_dir, exist_ok=True)
        
        file_path = os.path.join(project_dir, file.filename)
        
        # 保存上传文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 读取数据获取基本信息
        try:
            df = pd.read_excel(file_path) if file.filename.endswith(('.xlsx', '.xls')) else pd.read_csv(file_path)
            row_count = len(df)
            col_count = len(df.columns)
        except:
            row_count = 0
            col_count = 0
        
        # 初始化项目
        project_create = ProjectCreate(
            id=project_id,
            name=project_name or os.path.splitext(file.filename)[0],
            data_path=file_path,
            status="uploaded"
        )
        project = db.create_project(project_create)
        
        return AIResponse(
            success=True,
            message="数据上传成功",
            project_id=project.id,
            data={
                "filename": file.filename, 
                "project_id": project.id,
                "rows": row_count,
                "columns": col_count
            }
        )
        
    except Exception as e:
        return AIResponse(
            success=False,
            message=f"数据上传失败: {str(e)}"
        )

@app.get("/api/project/{project_id}/columns")
async def get_project_columns(project_id: str):
    try:
        project = db.get_project(project_id)
        if not project:
            return AIResponse(success=False, message="项目不存在")
        
        if not os.path.exists(project.data_path):
            return AIResponse(success=False, message="数据文件不存在")
        
        # 读取数据
        if project.data_path.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(project.data_path, header=0)
        elif project.data_path.endswith('.csv'):
            df = pd.read_csv(project.data_path, header=0)
        elif project.data_path.endswith('.dta'):
            df = pd.read_stata(project.data_path)
        else:
            return AIResponse(success=False, message="不支持的文件格式")

        # 确保列名是字符串
        df.columns = [str(col) for col in df.columns]

        # 获取列信息
        columns = df.columns.tolist()
        
        # 获取前5行数据作为预览，确保所有键都是字符串
        preview_data = df.head(5).to_dict(orient='records')
        preview = [{str(k): v for k, v in row.items()} for row in preview_data]
        
        return AIResponse(
            success=True,
            message="获取列信息成功",
            data={
                "columns": columns,
                "preview": preview,
                "total_rows": len(df),
                "total_columns": len(df.columns)
            }
        )
        
    except Exception as e:
        return AIResponse(
            success=False,
            message=f"获取列信息失败: {str(e)}"
        )

@app.post("/api/run-empirical", response_model=AIResponse)
async def run_empirical(request: EmpiricalRequest, background_tasks: BackgroundTasks):
    try:
        # Get project
        project = db.get_project(request.project_id)
        if not project:
            return AIResponse(success=False, message="项目不存在")
        
        # 构建命令（从结构化参数或原始命令）
        command = request.command
        if not command:
            # 优先从新结构 baseline_models 提取第一个被解释变量
            first_baseline = (request.baseline_models or [{}])[0]
            dep_for_cmd = request.dependent_var or first_baseline.get("dependent_var", "")
            if dep_for_cmd:
                command = f"被解释变量为{dep_for_cmd}，"
                # 解释变量
                indep = request.independent_vars or first_baseline.get("independent_vars", [])
                if indep:
                    command += f"解释变量为{'、'.join(indep)}，"
                # 控制变量
                ctrls = request.control_vars or first_baseline.get("control_vars", [])
                if ctrls:
                    command += f"控制变量包括{'、'.join(ctrls)}，"
                # 固定效应
                fe = request.fixed_effects or first_baseline.get("fixed_effects", {})
                if fe:
                    if 'individual' in fe and 'time' in fe:
                        command += "使用双向固定效应模型，"
                    elif 'individual' in fe:
                        command += f"使用个体固定效应模型（{fe['individual']}），"
                    elif 'time' in fe:
                        command += f"使用时间固定效应模型（{fe['time']}），"
                # 聚类
                clu = request.cluster_var or first_baseline.get("cluster_var")
                if clu:
                    command += f"聚类到{clu}，"
                # 模型类型
                mdl = request.model or first_baseline.get("model") or "ols"
                command += f"使用{mdl}模型"

        if not command:
            return AIResponse(success=False, message="请提供实证指令或选择变量")
        
        # 保存原始命令和结构化参数到数据库
        db.update_project(request.project_id, {
            "original_command": command,
            "model_type": request.model_type,
            "api_key": request.api_key,
            "variable_config": {
                "dependent_var": request.dependent_var,
                "independent_vars": request.independent_vars,
                "control_vars": request.control_vars,
                "fixed_effects": request.fixed_effects,
                "cluster_var": request.cluster_var,
                "model": request.model,
                "missing_method": request.missing_method,
                "outlier_method": request.outlier_method,
                "regression_models": request.regression_models,
                "robustness_tests": request.robustness_tests,
                "test_types": request.test_types,
                "moderation_var": request.moderation_var,
                "heterogeneity_var": request.heterogeneity_var,
                "mechanism_var": request.mechanism_var,
                "baseline_models": request.baseline_models,
                "heterogeneity_methods": request.heterogeneity_methods,
                "mechanism_methods": request.mechanism_methods,
            },
        })
        
        # Update project status - 清除旧的论文内容（保留实证结果占位）
        db.update_project(request.project_id, {
            "status": "processing",
            "empirical_results": {"progress": "正在解析命令..."},
            "paper_content": None,
            "review_comments": None,
            "quality_report": None,
            "quality_scores": None,
            "outline": None,
        })
        
        # 获取更新后的项目数据
        updated_project = db.get_project(request.project_id)
        
        # 构建结构化参数（直接从请求中获取，不经过命令解析器）
        test_types = request.test_types or ["descriptive", "correlation", "vif", "regression", "heterogeneity", "robustness"]
        structured_params = {
            "dependent_vars": [request.dependent_var] if request.dependent_var else [],
            "independent_vars": request.independent_vars or [],
            "control_vars": request.control_vars or [],
            "fixed_effects": request.fixed_effects or {},
            "cluster_var": request.cluster_var,
            "model_type": request.model or "ols",
            "missing_method": request.missing_method or "drop",
            "outlier_method": request.outlier_method or "winsorize",
            "test_types": test_types,
            "regression_models": request.regression_models or [request.model or "ols"],
            "robustness_tests": request.robustness_tests or [],
            "moderation_var": request.moderation_var,
            "heterogeneity_var": request.heterogeneity_var,
            "mechanism_var": request.mechanism_var,
            # 新结构：多模型 / 多方法
            "baseline_models": request.baseline_models or [],
            "heterogeneity_methods": request.heterogeneity_methods or [],
            "mechanism_methods": request.mechanism_methods or [],
            "moderation_methods": request.moderation_methods or [],
        }
        
        # Add background task - 传递结构化参数
        background_tasks.add_task(
            process_empirical_task,
            request.project_id,
            command,
            request.model_type,
            request.api_key,
            structured_params
        )
        
        return AIResponse(
            success=True,
            message="实证计算任务已启动",
            project_id=request.project_id,
            data={
                "id": updated_project.id,
                "name": updated_project.name,
                "status": updated_project.status,
                "modelType": updated_project.model_type,
                "createdAt": updated_project.created_at.isoformat() if updated_project.created_at else None,
                "updatedAt": updated_project.updated_at.isoformat() if updated_project.updated_at else None,
                "completedAt": updated_project.completed_at.isoformat() if updated_project.completed_at else None,
                "empiricalResults": updated_project.empirical_results,
                "paperContent": updated_project.paper_content,
            }
        )
        
    except Exception as e:
        return AIResponse(
            success=False,
            message=f"任务启动失败: {str(e)}"
        )

async def process_empirical_task(project_id: str, command: str, model_type: str, api_key: str, structured_params: dict = None):
    import traceback
    try:
        logger.info(f"[{project_id}] 开始处理实证任务")
        project = db.get_project(project_id)
        if not project:
            logger.error(f"[{project_id}] 项目不存在")
            return
        
        # 检查数据文件是否存在
        if not os.path.exists(project.data_path):
            error_msg = f"数据文件不存在: {project.data_path}"
            logger.error(f"[{project_id}] {error_msg}")
            db.update_project(project_id, {
                "status": "failed",
                "empirical_results": {"error": error_msg}
            })
            return
        
        # 更新状态为处理中
        db.update_project(project_id, {
            "status": "processing",
            "empirical_results": {"progress": "正在解析命令..."}
        })
        
        # 1. 解析命令（如果有结构化参数，优先使用）
        logger.info(f"[{project_id}] 步骤1: 解析参数")
        if structured_params:
            parsed_params = structured_params
            logger.info(f"[{project_id}] 使用结构化参数: {parsed_params}")
        else:
            parser = CommandParser()
            parsed_params = parser.parse(command)
            logger.info(f"[{project_id}] 解析结果: {parsed_params}")
        
        db.update_project(project_id, {
            "empirical_results": {"progress": "正在预处理数据..."}
        })
        
        # 2. 预处理数据
        logger.info(f"[{project_id}] 步骤2: 预处理数据")
        preprocessor = DataPreprocessor()
        processed_data = preprocessor.process(project.data_path, parsed_params)
        logger.info(f"[{project_id}] 数据预处理完成，数据形状: {processed_data.shape}")
        
        db.update_project(project_id, {
            "empirical_results": {"progress": "正在进行实证计算..."}
        })
        
        # 3. 运行实证计算
        logger.info(f"[{project_id}] 步骤3: 运行实证计算")
        engine = EmpiricalEngine()
        empirical_results = engine.run_all_tests(processed_data, parsed_params)
        logger.info(f"[{project_id}] 实证计算完成")

        # 更新项目状态为完成（仅实证结果，论文待用户确认后生成）
        db.update_project(
            project_id,
            {
                "status": "completed",
                "empirical_results": empirical_results,
                "paper_content": None
            }
        )
        logger.info(f"[{project_id}] 实证分析完成，等待用户确认生成论文")

    except Exception as e:
        error_msg = f"任务处理失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(f"[{project_id}] {error_msg}")
        try:
            db.update_project(project_id, {
                "status": "failed",
                "empirical_results": {"error": str(e), "traceback": traceback.format_exc()}
            })
        except Exception as db_error:
            logger.error(f"[{project_id}] 更新失败状态时出错: {str(db_error)}")


class RerunEmpiricalRequest(BaseModel):
    project_id: str
    dependent_var: Optional[str] = None
    independent_vars: Optional[List[str]] = []
    control_vars: Optional[List[str]] = []
    fixed_effects: Optional[Dict[str, str]] = {}
    cluster_var: Optional[str] = None
    model: Optional[str] = "ols"
    missing_method: Optional[str] = "drop"
    outlier_method: Optional[str] = "winsorize"
    regression_models: Optional[List[str]] = None
    robustness_tests: Optional[List[Dict[str, Any]]] = None
    test_types: Optional[List[str]] = None
    # 新结构
    baseline_models: Optional[List[Dict[str, Any]]] = None
    heterogeneity_methods: Optional[List[Dict[str, Any]]] = None
    mechanism_methods: Optional[List[Dict[str, Any]]] = None
    moderation_methods: Optional[List[Dict[str, Any]]] = None
    moderation_var: Optional[str] = None


@app.post("/api/rerun-empirical", response_model=AIResponse)
async def rerun_empirical(request: RerunEmpiricalRequest, background_tasks: BackgroundTasks):
    try:
        project = db.get_project(request.project_id)
        if not project:
            return AIResponse(success=False, message="项目不存在")

        if not os.path.exists(project.data_path):
            return AIResponse(success=False, message="数据文件不存在")

        # 构建新的参数
        structured_params = {
            "dependent_vars": [request.dependent_var] if request.dependent_var else [],
            "independent_vars": request.independent_vars or [],
            "control_vars": request.control_vars or [],
            "fixed_effects": request.fixed_effects or {},
            "cluster_var": request.cluster_var,
            "model_type": request.model or "ols",
            "missing_method": request.missing_method or "drop",
            "outlier_method": request.outlier_method or "winsorize",
            "test_types": request.test_types or ["descriptive", "correlation", "vif", "regression", "heterogeneity", "robustness"],
            "regression_models": request.regression_models or [request.model or "ols"],
            "robustness_tests": request.robustness_tests or [],
            "moderation_var": request.moderation_var,
            # 新结构
            "baseline_models": request.baseline_models or [],
            "heterogeneity_methods": request.heterogeneity_methods or [],
            "mechanism_methods": request.mechanism_methods or [],
            "moderation_methods": request.moderation_methods or [],
        }

        # 清除上一次的实证结果和论文内容
        db.update_project(request.project_id, {
            "status": "processing",
            "empirical_results": {"progress": "正在重新运行实证分析..."},
            "paper_content": None,
            "review_comments": None,
            "quality_report": None,
            "quality_scores": None,
            "outline": None,
        })

        # Add background task - 传递结构化参数
        background_tasks.add_task(
            process_rerun_empirical_task,
            request.project_id,
            project.original_command or "",
            project.model_type,
            project.api_key,
            structured_params
        )

        return AIResponse(
            success=True,
            message="重新实证分析任务已启动",
            project_id=request.project_id
        )

    except Exception as e:
        return AIResponse(
            success=False,
            message=f"任务启动失败: {str(e)}"
        )


async def process_rerun_empirical_task(project_id: str, command: str, model_type: str, api_key: str, structured_params: dict = None):
    import traceback
    try:
        logger.info(f"[{project_id}] 开始处理重新实证分析任务")
        project = db.get_project(project_id)
        if not project:
            logger.error(f"[{project_id}] 项目不存在")
            return

        # 检查数据文件是否存在
        if not os.path.exists(project.data_path):
            error_msg = f"数据文件不存在: {project.data_path}"
            logger.error(f"[{project_id}] {error_msg}")
            db.update_project(project_id, {
                "status": "failed",
                "empirical_results": {"error": error_msg}
            })
            return

        # 更新状态为处理中
        db.update_project(project_id, {
            "status": "processing",
            "empirical_results": {"progress": "正在预处理数据..."}
        })

        # 1. 预处理数据
        logger.info(f"[{project_id}] 步骤1: 预处理数据")
        preprocessor = DataPreprocessor()
        processed_data = preprocessor.process(project.data_path, structured_params)
        logger.info(f"[{project_id}] 数据预处理完成，数据形状: {processed_data.shape}")

        db.update_project(project_id, {
            "empirical_results": {"progress": "正在进行实证计算..."}
        })

        # 2. 运行实证计算
        logger.info(f"[{project_id}] 步骤2: 运行实证计算")
        engine = EmpiricalEngine()
        empirical_results = engine.run_all_tests(processed_data, structured_params)
        logger.info(f"[{project_id}] 实证计算完成")

        # 更新项目状态为完成（仅实证结果，论文待用户确认后生成）
        db.update_project(
            project_id,
            {
                "status": "completed",
                "empirical_results": empirical_results,
                "paper_content": None
            }
        )
        logger.info(f"[{project_id}] 重新实证分析完成")

    except Exception as e:
        error_msg = f"重新实证分析失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(f"[{project_id}] {error_msg}")
        try:
            db.update_project(project_id, {
                "status": "failed",
                "empirical_results": {"error": str(e), "traceback": traceback.format_exc()}
            })
        except Exception as db_error:
            logger.error(f"[{project_id}] 更新失败状态时出错: {str(db_error)}")


class GeneratePaperRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    project_id: str
    model_type: str = "deepseek"
    api_key: Optional[str] = None
    model: Optional[str] = None  # 模型名称
    custom_prompt: Optional[str] = ""  # 改为可选，默认为空字符串
    literature_content: Optional[str] = None  # 用户上传的文献综述参考内容


@app.post("/api/upload-literature", response_model=AIResponse)
async def upload_literature(file: UploadFile = File(...)):
    """上传文献综述参考文件（支持 .txt RefWorks 格式）"""
    try:
        content = await file.read()
        # 尝试多种编码
        for encoding in ["utf-8", "gbk", "gb2312", "utf-16"]:
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            return AIResponse(success=False, message="无法解析文件编码，请上传 UTF-8 或 GBK 编码的 .txt 文件")

        return AIResponse(
            success=True,
            message="文献文件上传成功",
            data={"filename": file.filename, "content": text}
        )
    except Exception as e:
        return AIResponse(success=False, message=f"文献上传失败: {str(e)}")


@app.post("/api/generate-paper", response_model=AIResponse)
async def generate_paper(request: GeneratePaperRequest, background_tasks: BackgroundTasks):
    try:
        project = db.get_project(request.project_id)
        if not project:
            return AIResponse(success=False, message="项目不存在")

        if not project.empirical_results or isinstance(project.empirical_results, dict) and not project.empirical_results.get("descriptive"):
            return AIResponse(success=False, message="项目尚未完成实证分析，无法生成论文")

        if project.status != "completed":
            return AIResponse(success=False, message=f"项目状态为 {project.status}，无法生成论文")

        # 使用用户自定义提示词，如果没有则使用项目原始命令
        command = request.custom_prompt or project.original_command or ""

        # 清空旧论文及相关内容，设置状态为生成中
        db.update_project(request.project_id, {
            "status": "generating_paper",
            "paper_content": None,
            "review_comments": None,
            "quality_report": None,
            "quality_scores": None,
            "outline": None,
        })

        background_tasks.add_task(
            process_paper_generation,
            request.project_id,
            request.model_type,
            request.api_key,
            request.model,
            project.empirical_results,
            command,
            request.literature_content
        )

        return AIResponse(
            success=True,
            message="论文生成任务已启动",
            project_id=request.project_id
        )

    except Exception as e:
        return AIResponse(success=False, message=f"启动论文生成失败: {str(e)}")


async def process_paper_generation(
    project_id: str,
    model_type: str,
    api_key: str,
    model_name: str,
    empirical_results: dict,
    command: str,
    literature_content: str = None
):
    import traceback
    import asyncio
    try:
        logger.info(f"[{project_id}] 开始生成论文")
        lit_len = len(literature_content) if literature_content else 0
        logger.info(f"[{project_id}] 收到文献内容长度: {lit_len}")
        if literature_content:
            logger.info(f"[{project_id}] 文献内容前200字: {literature_content[:200]}")

        db.update_project(project_id, {
            "empirical_results": empirical_results
        })

        from core.generator import create_multi_agent_generator
        generator = create_multi_agent_generator(model_type, api_key)
        # 使用 asyncio.to_thread 将同步操作放到线程池，避免阻塞事件循环
        generation_result = await asyncio.to_thread(
            generator.generate_paper, empirical_results, command, literature_content
        )
        logger.info(f"[{project_id}] 多智能体论文生成完成")

        # 提取论文正文和审稿意见
        paper_content = generation_result.get('paper', '')
        review_comments = generation_result.get('review_comments', '')
        quality_report = generation_result.get('quality_report', '')
        quality_scores = generation_result.get('quality_scores', {})
        outline = generation_result.get('outline', {})

        from export_engine.exporter import ResultExporter
        exporter = ResultExporter()
        export_path = exporter.export_all(empirical_results, paper_content, project_id)
        logger.info(f"[{project_id}] 结果导出完成: {export_path}")

        db.update_project(
            project_id,
            {
                "status": "completed",
                "result_path": export_path,
                "empirical_results": empirical_results,
                "paper_content": paper_content,
                "review_comments": review_comments,
                "quality_report": quality_report,
                "quality_scores": quality_scores,
                "outline": outline
            }
        )
        logger.info(f"[{project_id}] 论文生成并保存完成")

    except Exception as e:
        error_msg = f"论文生成失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(f"[{project_id}] {error_msg}")
        try:
            db.update_project(project_id, {
                "status": "failed",
                "empirical_results": empirical_results,
                "paper_content": None
            })
        except Exception as db_error:
            logger.error(f"[{project_id}] 更新失败状态时出错: {str(db_error)}")

@app.get("/api/project/{project_id}", response_model=AIResponse)
async def get_project(project_id: str):
    try:
        project = db.get_project(project_id)
        if not project:
            return AIResponse(success=False, message="项目不存在")
        
        return AIResponse(
            success=True,
            message="项目信息获取成功",
            data={
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "status": project.status,
                "modelType": project.model_type,
                "dataPath": project.data_path,
                "resultPath": project.result_path,
                "empiricalResults": project.empirical_results,
                "paperContent": project.paper_content,
                "variableConfig": project.variable_config,
                "createdAt": project.created_at.isoformat() if project.created_at else None,
                "updatedAt": project.updated_at.isoformat() if project.updated_at else None,
                "completedAt": project.completed_at.isoformat() if project.completed_at else None,
            },
            project_id=project_id
        )
        
    except Exception as e:
        return AIResponse(
            success=False,
            message=f"获取项目信息失败: {str(e)}"
        )

@app.get("/api/export/{project_id}", response_class=FileResponse)
async def export_project(project_id: str):
    try:
        project = db.get_project(project_id)
        if not project or not project.result_path:
            return AIResponse(success=False, message="项目结果不存在")
        
        return FileResponse(
            path=project.result_path,
            filename=f"实证论文_{project_id}.zip",
            media_type="application/zip"
        )
        
    except Exception as e:
        return AIResponse(
            success=False,
            message=f"导出失败: {str(e)}"
        )

@app.get("/api/export-pdf/{project_id}", response_class=FileResponse)
async def export_pdf(project_id: str):
    try:
        project = db.get_project(project_id)
        if not project:
            return AIResponse(success=False, message="项目不存在")
        
        if not project.empirical_results:
            return AIResponse(success=False, message="项目分析结果不存在")
        
        from export_engine.pdf_exporter import PDFExporter
        exporter = PDFExporter()
        
        pdf_path = exporter.export_analysis_results(
            project.empirical_results,
            project.name
        )
        
        return FileResponse(
            path=pdf_path,
            filename=f"实证分析结果_{project.name}.pdf",
            media_type="application/pdf"
        )
        
    except Exception as e:
        logger.error(f"PDF导出失败: {str(e)}")
        return AIResponse(
            success=False,
            message=f"PDF导出失败: {str(e)}"
        )

@app.get("/api/export-paper-word/{project_id}", response_class=FileResponse)
async def export_paper_word(project_id: str):
    try:
        project = db.get_project(project_id)
        if not project:
            return AIResponse(success=False, message="项目不存在")
        
        if not project.paper_content:
            return AIResponse(success=False, message="论文内容不存在")
        
        from export_engine.exporter import ResultExporter
        exporter = ResultExporter()
        
        # 创建临时目录
        import tempfile
        temp_dir = tempfile.mkdtemp()
        
        # 导出Word论文
        word_path = exporter._export_word_paper(
            project.empirical_results or {},
            project.paper_content,
            temp_dir
        )
        
        return FileResponse(
            path=word_path,
            filename=f"论文_{project.name}.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        
    except Exception as e:
        logger.error(f"Word导出失败: {str(e)}")
        return AIResponse(
            success=False,
            message=f"Word导出失败: {str(e)}"
        )

@app.get("/api/export-excel/{project_id}", response_class=FileResponse)
async def export_excel(project_id: str):
    try:
        project = db.get_project(project_id)
        if not project:
            return AIResponse(success=False, message="项目不存在")
        
        if not project.empirical_results:
            return AIResponse(success=False, message="项目分析结果不存在")
        
        from export_engine.excel_exporter import ExcelExporter
        exporter = ExcelExporter()
        
        excel_path = exporter.export_analysis_results(
            project.empirical_results,
            project.name
        )
        
        return FileResponse(
            path=excel_path,
            filename=f"实证分析结果_{project.name}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    except Exception as e:
        logger.error(f"Excel导出失败: {str(e)}")
        return AIResponse(
            success=False,
            message=f"Excel导出失败: {str(e)}"
        )

@app.get("/api/projects", response_model=AIResponse)
async def get_projects():
    try:
        projects = db.get_all_projects()
        project_list = []
        for p in projects:
            project_list.append({
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "status": p.status,
                "modelType": p.model_type,
                "createdAt": p.created_at.isoformat() if p.created_at else None,
                "updatedAt": p.updated_at.isoformat() if p.updated_at else None,
                "completedAt": p.completed_at.isoformat() if p.completed_at else None,
            })
        
        return AIResponse(
            success=True,
            message="项目列表获取成功",
            data={
                "projects": project_list,
                "total": len(project_list)
            }
        )
        
    except Exception as e:
        return AIResponse(
            success=False,
            message=f"获取项目列表失败: {str(e)}"
        )

@app.get("/api/model-registry")
async def model_registry():
    """返回支持的模型列表"""
    return get_model_registry()

# 设置相关API
class SettingsResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

class AISettings(BaseModel):
    modelType: str = "deepseek"
    deepseekApiKey: str = ""
    deepseekModel: str = "deepseek-chat"
    qwenApiKey: str = ""
    qwenModel: str = "qwen-plus"
    kimiApiKey: str = ""
    kimiModel: str = "kimi-k2.6"
    glmApiKey: str = ""
    glmModel: str = "glm-4-plus"
    doubaoApiKey: str = ""
    doubaoModel: str = "doubao-pro-32k"
    customApiKey: str = ""
    customModel: str = ""
    customBaseUrl: str = ""

class EmpiricalSettings(BaseModel):
    missingMethod: str = "drop"
    outlierMethod: str = "winsorize"
    winsorizeThreshold: float = 0.01
    significanceLevel: float = 0.05
    autoSaveResults: bool = True
    resultSavePath: str = ""

class SystemSettings(BaseModel):
    language: str = "zh-CN"
    theme: str = "light"
    autoRefreshInterval: int = 5
    maxParallelTasks: int = 2

@app.get("/api/settings", response_model=SettingsResponse)
async def get_settings():
    try:
        # 读取设置文件
        settings_path = "settings.json"
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        else:
            # 默认设置
            settings = {
                "aiSettings": AISettings().dict(),
                "empiricalSettings": EmpiricalSettings().dict(),
                "systemSettings": SystemSettings().dict()
            }
            # 保存默认设置
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        
        return SettingsResponse(
            success=True,
            message="设置获取成功",
            data=settings
        )
        
    except Exception as e:
        return SettingsResponse(
            success=False,
            message=f"获取设置失败: {str(e)}"
        )

@app.post("/api/settings", response_model=SettingsResponse)
async def save_settings(request: dict):
    try:
        settings_path = "settings.json"
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                all_settings = json.load(f)
        else:
            all_settings = {}
        
        # 更新设置
        if "aiSettings" in request:
            all_settings["aiSettings"] = request["aiSettings"]
        if "empiricalSettings" in request:
            all_settings["empiricalSettings"] = request["empiricalSettings"]
        if "systemSettings" in request:
            all_settings["systemSettings"] = request["systemSettings"]
        
        # 保存设置
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(all_settings, f, ensure_ascii=False, indent=2)
        
        return SettingsResponse(
            success=True,
            message="设置保存成功"
        )
        
    except Exception as e:
        return SettingsResponse(
            success=False,
            message=f"保存设置失败: {str(e)}"
        )

@app.post("/api/settings/ai", response_model=SettingsResponse)
async def save_ai_settings(settings: AISettings):
    try:
        # 读取现有设置
        settings_path = "settings.json"
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                all_settings = json.load(f)
        else:
            all_settings = {
                "empiricalSettings": EmpiricalSettings().dict(),
                "systemSettings": SystemSettings().dict()
            }
        
        # 更新AI设置
        all_settings["aiSettings"] = settings.dict()
        
        # 保存设置
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(all_settings, f, ensure_ascii=False, indent=2)
        
        return SettingsResponse(
            success=True,
            message="AI设置保存成功"
        )
        
    except Exception as e:
        return SettingsResponse(
            success=False,
            message=f"保存AI设置失败: {str(e)}"
        )

@app.post("/api/settings/empirical", response_model=SettingsResponse)
async def save_empirical_settings(settings: EmpiricalSettings):
    try:
        # 读取现有设置
        settings_path = "settings.json"
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                all_settings = json.load(f)
        else:
            all_settings = {
                "aiSettings": AISettings().dict(),
                "systemSettings": SystemSettings().dict()
            }
        
        # 更新实证设置
        all_settings["empiricalSettings"] = settings.dict()
        
        # 保存设置
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(all_settings, f, ensure_ascii=False, indent=2)
        
        return SettingsResponse(
            success=True,
            message="实证设置保存成功"
        )
        
    except Exception as e:
        return SettingsResponse(
            success=False,
            message=f"保存实证设置失败: {str(e)}"
        )

@app.post("/api/settings/system", response_model=SettingsResponse)
async def save_system_settings(settings: SystemSettings):
    try:
        # 读取现有设置
        settings_path = "settings.json"
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                all_settings = json.load(f)
        else:
            all_settings = {
                "aiSettings": AISettings().dict(),
                "empiricalSettings": EmpiricalSettings().dict()
            }
        
        # 更新系统设置
        all_settings["systemSettings"] = settings.dict()
        
        # 保存设置
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(all_settings, f, ensure_ascii=False, indent=2)
        
        return SettingsResponse(
            success=True,
            message="系统设置保存成功"
        )
        
    except Exception as e:
        return SettingsResponse(
            success=False,
            message=f"保存系统设置失败: {str(e)}"
        )

@app.get("/api/settings/stats", response_model=SettingsResponse)
async def get_system_stats():
    try:
        # 获取项目统计
        project_stats = db.get_project_stats()
        
        # 计算数据占用空间
        data_dir = "data"
        total_size = 0
        if os.path.exists(data_dir):
            for dirpath, dirnames, filenames in os.walk(data_dir):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp)
        
        # 数据库大小
        db_size = 0
        db_path = "empirical_ai.db"
        if os.path.exists(db_path):
            db_size = os.path.getsize(db_path)
        
        # 格式化大小
        def format_size(size):
            if size < 1024:
                return f"{size} B"
            elif size < 1024*1024:
                return f"{size/1024:.2f} KB"
            elif size < 1024*1024*1024:
                return f"{size/(1024*1024):.2f} MB"
            else:
                return f"{size/(1024*1024*1024):.2f} GB"
        
        stats = {
            "totalProjects": project_stats.get("total_projects", 0),
            "completedProjects": project_stats.get("completed_projects", 0),
            "dataSize": format_size(total_size),
            "dbSize": format_size(db_size)
        }
        
        return SettingsResponse(
            success=True,
            message="系统统计获取成功",
            data=stats
        )
        
    except Exception as e:
        return SettingsResponse(
            success=False,
            message=f"获取系统统计失败: {str(e)}"
        )

@app.get("/api/stats", response_model=AIResponse)
async def get_stats():
    try:
        project_stats = db.get_project_stats()
        stats = {
            "totalProjects": project_stats.get("total_projects", 0),
            "completedProjects": project_stats.get("completed_projects", 0),
            "processingProjects": project_stats.get("processing_projects", 0),
            "completionRate": round(project_stats.get("completion_rate", 0), 1),
        }
        return AIResponse(
            success=True,
            message="统计数据获取成功",
            data=stats
        )
    except Exception as e:
        return AIResponse(
            success=False,
            message=f"获取统计数据失败: {str(e)}"
        )

@app.get("/api/projects/recent", response_model=AIResponse)
async def get_recent_projects():
    try:
        projects = db.get_recent_projects(days=7, limit=5)
        return AIResponse(
            success=True,
            message="最近项目获取成功",
            data={"projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "status": p.status,
                    "modelType": p.model_type,
                    "createdAt": p.created_at.isoformat() if p.created_at else None,
                }
                for p in projects
            ]}
        )
    except Exception as e:
        return AIResponse(
            success=False,
            message=f"获取最近项目失败: {str(e)}"
        )

@app.get("/api/project/{project_id}/refresh", response_model=AIResponse)
async def refresh_project(project_id: str):
    try:
        project = db.get_project(project_id)
        if not project:
            return AIResponse(success=False, message="项目不存在")
        
        return AIResponse(
            success=True,
            message="项目信息刷新成功",
            data={
                "id": project.id,
                "name": project.name,
                "status": project.status,
                "modelType": project.model_type,
                "createdAt": project.created_at.isoformat() if project.created_at else None,
                "updatedAt": project.updated_at.isoformat() if project.updated_at else None,
                "completedAt": project.completed_at.isoformat() if project.completed_at else None,
                "empiricalResults": project.empirical_results,
                "paperContent": project.paper_content,
            }
        )
    except Exception as e:
        return AIResponse(
            success=False,
            message=f"刷新项目失败: {str(e)}"
        )

@app.post("/api/project/{project_id}/reset-from-generating", response_model=AIResponse)
async def reset_project_from_generating(project_id: str):
    """将项目从 generating_paper 状态重置为 completed，清空论文内容"""
    try:
        project = db.get_project(project_id)
        if not project:
            return AIResponse(success=False, message="项目不存在")

        db.update_project_status(project_id, "completed")
        # 清空论文内容，避免残留
        db.update_project(project_id, {"paper_content": None})

        return AIResponse(
            success=True,
            message="项目状态已重置",
            data={
                "id": project.id,
                "name": project.name,
                "status": "completed",
            }
        )
    except Exception as e:
        return AIResponse(
            success=False,
            message=f"重置项目失败: {str(e)}"
        )

@app.delete("/api/project/{project_id}", response_model=AIResponse)
async def delete_project(project_id: str):
    try:
        success = db.delete_project(project_id)
        if not success:
            return AIResponse(success=False, message="项目不存在")

        # 清理上传的数据文件
        upload_dir = os.path.join(UPLOAD_DIR, project_id)
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
            logger.info(f"已删除项目上传目录: {upload_dir}")

        # 清理 exports 中的导出文件（子目录 + ZIP）
        exports_dir = os.path.join(os.path.dirname(__file__), "exports")
        if os.path.exists(exports_dir):
            for f in os.listdir(exports_dir):
                if project_id in f:
                    path = os.path.join(exports_dir, f)
                    try:
                        if os.path.isdir(path):
                            shutil.rmtree(path)
                        else:
                            os.remove(path)
                        logger.info(f"已删除导出文件: {path}")
                    except Exception as e:
                        logger.warning(f"删除导出文件失败 {path}: {e}")

        return AIResponse(success=True, message="项目删除成功")
    except Exception as e:
        return AIResponse(
            success=False,
            message=f"删除项目失败: {str(e)}"
        )

@app.post("/api/project/{project_id}/retry", response_model=AIResponse)
async def retry_project(project_id: str, background_tasks: BackgroundTasks):
    try:
        project = db.get_project(project_id)
        if not project:
            return AIResponse(success=False, message="项目不存在")
        
        # 获取原始命令
        original_command = project.original_command or ""
        model_type = project.model_type or "deepseek"
        api_key = project.api_key or ""
        
        if not original_command:
            return AIResponse(success=False, message="无法获取原始命令")
        
        # 更新状态为处理中，清除旧的实证结果和论文内容
        db.update_project(project_id, {
            "status": "processing",
            "empirical_results": {"progress": "正在重新运行实证分析..."},
            "paper_content": None,
            "review_comments": None,
            "quality_report": None,
            "quality_scores": None,
            "outline": None,
        })
        
        # 重新启动后台任务（不传递结构化参数，使用命令解析）
        background_tasks.add_task(
            process_empirical_task,
            project_id,
            original_command,
            model_type,
            api_key,
            None  # 重试时使用命令解析
        )
        
        return AIResponse(
            success=True,
            message="项目已重新启动",
            project_id=project_id
        )
    except Exception as e:
        return AIResponse(
            success=False,
            message=f"项目重启失败: {str(e)}"
        )

# ========== 静态文件服务（前端生产构建） ==========
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(FRONTEND_DIST):
    # 挂载 assets 目录
    assets_dir = os.path.join(FRONTEND_DIST, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    
    # SPA 降级路由：所有非 /api 请求返回 index.html
    from fastapi.responses import HTMLResponse
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            return AIResponse(success=False, message="接口不存在")
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        return AIResponse(success=False, message="前端资源未构建，请运行 cd frontend && npm run build")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
