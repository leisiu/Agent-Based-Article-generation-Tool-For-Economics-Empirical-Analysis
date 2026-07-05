from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional, Dict, Any
import os
import uuid
import logging
from datetime import datetime

# Import models
from .models import Base, ProjectDB, ProjectCreate, ProjectUpdate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_url: str = None):
        """初始化数据库连接"""
        if db_url is None:
            # 默认使用 backend 目录下的数据库（绝对路径，避免 CWD 影响）
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(backend_dir, "empirical_ai.db")
            db_url = f"sqlite:///{db_path}"
        self.engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False, "timeout": 30}  # SQLite特定参数，30秒超时
        )
        # 启用WAL模式，解决读写锁冲突
        from sqlalchemy import event
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        # 创建所有表
        self._create_tables()
    
    def _create_tables(self):
        """创建数据库表"""
        try:
            Base.metadata.create_all(bind=self.engine)
            # 兼容已有表：手动 ALTER TABLE 添加新列（SQLAlchemy 不会自动 ALTER）
            self._migrate_add_columns()
            logger.info("数据库表创建成功")
        except SQLAlchemyError as e:
            logger.error(f"创建数据库表失败: {str(e)}")

    def _migrate_add_columns(self):
        """
        手动补齐 ORM 中新增的列（SQLite 简易迁移）。
        仅在 Base 中存在但数据库表缺少的 JSON/Text 列会执行 ADD COLUMN。
        """
        try:
            with self.engine.connect() as conn:
                from sqlalchemy import text, inspect
                inspector = inspect(self.engine)
                existing_cols = {c['name'] for c in inspector.get_columns('projects')}
                # ORM 模型中所有 columns
                orm_cols = {c.name: c for c in ProjectDB.__table__.columns}
                for col_name, col in orm_cols.items():
                    if col_name in existing_cols:
                        continue
                    if col_name == 'id':
                        continue  # 主键不会缺失
                    # 仅做最常见的 JSON 文本/JSON 列
                    col_type = col.type.__class__.__name__
                    if col_type in ('JSON', 'Text'):
                        sql_type = 'TEXT'
                    elif col_type in ('Integer',):
                        sql_type = 'INTEGER'
                    else:
                        sql_type = 'TEXT'
                    try:
                        conn.execute(text(f"ALTER TABLE projects ADD COLUMN {col_name} {sql_type}"))
                        conn.commit()
                        logger.info(f"已添加缺失列: projects.{col_name} ({sql_type})")
                    except Exception as e:
                        logger.warning(f"添加列 {col_name} 失败: {e}")
        except Exception as e:
            logger.warning(f"迁移检查失败: {e}")
    
    def get_db(self):
        """获取数据库会话"""
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    def create_project(self, project_create: ProjectCreate) -> ProjectDB:
        """创建新项目"""
        try:
            db = self.SessionLocal()
            
            db_project = ProjectDB(
                id=project_create.id or str(uuid.uuid4()),
                name=project_create.name,
                description=project_create.description,
                data_path=project_create.data_path,
                model_type=project_create.model_type,
                api_key=project_create.api_key,
                created_at=datetime.now()
            )
            
            db.add(db_project)
            db.commit()
            db.refresh(db_project)
            
            logger.info(f"项目创建成功，ID: {db_project.id}")
            return db_project
            
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"创建项目失败: {str(e)}")
            raise
        finally:
            db.close()
    
    def get_project(self, project_id: str) -> Optional[ProjectDB]:
        """获取单个项目"""
        try:
            db = self.SessionLocal()
            project = db.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            return project
        except SQLAlchemyError as e:
            logger.error(f"获取项目失败: {str(e)}")
            return None
        finally:
            db.close()
    
    def get_all_projects(self, skip: int = 0, limit: int = 100) -> List[ProjectDB]:
        """获取所有项目"""
        try:
            db = self.SessionLocal()
            projects = db.query(ProjectDB).offset(skip).limit(limit).all()
            return projects
        except SQLAlchemyError as e:
            logger.error(f"获取项目列表失败: {str(e)}")
            return []
        finally:
            db.close()
    
    def update_project(self, project_id: str, project_update: Dict[str, Any]) -> Optional[ProjectDB]:
        """更新项目信息"""
        try:
            db = self.SessionLocal()
            project = db.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            
            if not project:
                logger.warning(f"项目不存在，ID: {project_id}")
                return None
            
            # 更新字段
            for key, value in project_update.items():
                if hasattr(project, key) and value is not None:
                    setattr(project, key, value)
            
            project.updated_at = datetime.now()
            
            db.commit()
            db.refresh(project)
            
            logger.info(f"项目更新成功，ID: {project_id}")
            return project
            
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"更新项目失败: {str(e)}")
            return None
        finally:
            db.close()
    
    def update_project_status(self, project_id: str, status: str):
        """更新项目状态"""
        try:
            db = self.SessionLocal()
            project = db.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            
            if not project:
                logger.warning(f"项目不存在，ID: {project_id}")
                return
            
            project.status = status
            project.updated_at = datetime.now()
            
            # 如果状态是completed，设置完成时间
            if status == "completed":
                project.completed_at = datetime.now()
            
            db.commit()
            logger.info(f"项目状态更新成功，ID: {project_id}，状态: {status}")
            
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"更新项目状态失败: {str(e)}")
        finally:
            db.close()
    
    def delete_project(self, project_id: str) -> bool:
        """删除项目"""
        try:
            db = self.SessionLocal()
            project = db.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            
            if not project:
                logger.warning(f"项目不存在，ID: {project_id}")
                return False
            
            db.delete(project)
            db.commit()
            
            logger.info(f"项目删除成功，ID: {project_id}")
            return True
            
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"删除项目失败: {str(e)}")
            return False
        finally:
            db.close()
    
    def get_projects_by_status(self, status: str, skip: int = 0, limit: int = 100) -> List[ProjectDB]:
        """按状态获取项目"""
        try:
            db = self.SessionLocal()
            projects = db.query(ProjectDB).filter(ProjectDB.status == status).offset(skip).limit(limit).all()
            return projects
        except SQLAlchemyError as e:
            logger.error(f"按状态获取项目失败: {str(e)}")
            return []
        finally:
            db.close()
    
    def get_recent_projects(self, days: int = 7, skip: int = 0, limit: int = 100) -> List[ProjectDB]:
        """获取最近创建的项目"""
        try:
            db = self.SessionLocal()
            from datetime import datetime, timedelta
            
            cutoff_date = datetime.now() - timedelta(days=days)
            projects = db.query(ProjectDB).filter(ProjectDB.created_at >= cutoff_date).offset(skip).limit(limit).all()
            
            return projects
        except SQLAlchemyError as e:
            logger.error(f"获取最近项目失败: {str(e)}")
            return []
        finally:
            db.close()
    
    def get_project_stats(self) -> Dict[str, Any]:
        """获取项目统计信息"""
        try:
            db = self.SessionLocal()
            
            total_projects = db.query(ProjectDB).count()
            completed_projects = db.query(ProjectDB).filter(ProjectDB.status == "completed").count()
            processing_projects = db.query(ProjectDB).filter(ProjectDB.status == "processing").count()
            failed_projects = db.query(ProjectDB).filter(ProjectDB.status == "failed").count()
            
            # 最近7天创建的项目
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=7)
            recent_projects = db.query(ProjectDB).filter(ProjectDB.created_at >= cutoff_date).count()
            
            stats = {
                "total_projects": total_projects,
                "completed_projects": completed_projects,
                "processing_projects": processing_projects,
                "failed_projects": failed_projects,
                "recent_projects_7d": recent_projects,
                "completion_rate": completed_projects / max(total_projects, 1) * 100
            }
            
            return stats
            
        except SQLAlchemyError as e:
            logger.error(f"获取项目统计失败: {str(e)}")
            return {}
        finally:
            db.close()
