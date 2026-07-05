# 经管实证AI自动论文生成工具

本地部署的经管实证论文自动生成工具。上传面板数据，自动完成实证分析并生成完整论文。

---

## 项目能做什么

1. **上传数据** — 支持 Excel / CSV 格式的面板数据
2. **配置模型** — 设置变量（被解释变量、解释变量、控制变量、固定效应、聚类）
3. **自动实证分析** — 运行一系列标准计量经济学检验
4. **一键生成论文** — 多智能体协作，自动撰写包含实证结果的完整论文
5. **导出结果** — 支持 Word / PDF / Excel 导出

---

## 实证分析技术
pyfixest、statsmodels库等完成与stata相同的计量分析

## 多智能体协作流程

系统由 5 个 AI 智能体协作完成论文生成：
```  
                                                                     返修           
                                                      -------------------------------
                                                      |               ↑             ↑
                                                      ↓               |             |
用户确定实证结果---→数据分析agent---→文献综述agent---→学术写作agent---→质量评审agent---→审稿agent---→输出论文

每个智能体调用 LLM，前一个智能体的输出作为上下文传递给下一个。
```

## 部署与启动

### 环境要求
- Python >= 3.9

### 1. 安装依赖

```
bash
cd backend
pip install -r requirements.txt
```

### 2. 启动服务

```
bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8002
python main.py
> 启动后访问 http://localhost:8002
```

### 3. 访问

- **前端页面**：http://localhost:8002
- **API 文档**：http://localhost:8002/docs
---

## 项目结构

```
实证AI自动论文生成/
├── backend/                    # Python 后端
│   ├── main.py                 # FastAPI 主入口 + 静态文件服务
│   ├── core/                   # AI 智能体核心
│   │   ├── llm_client.py       # LLM 统一调用 + 模型注册表
│   │   ├── base_agent.py       # 智能体基类
│   │   ├── generator.py        # 多智能体协调入口
│   │   └── orchestrator.py     # 智能体编排器
│   ├── multi_agent/            # 5 个 AI 智能体
│   │   ├── data_analyst_agent.py       # 数据分析
│   │   ├── literature_review_agent.py  # 文献综述
│   │   ├── academic_writer_agent.py    # 学术写作
│   │   ├── quality_reviewer_agent.py   # 质量评审
│   │   └── editor_agent.py             # 审稿编辑
│   ├── empirical_models/       # 计量模型引擎
│   │   └── empirical_engine.py # OLS / FE / RE 
│   ├── data_processor/         # 数据预处理
│   ├── export_engine/          # 导出 Word / PDF / Excel
│   ├── db/                     # SQLite 数据库
│   ├── uploads/                # 上传数据存储
│   ├── exports/                # 导出文件存储
│   ├── settings.json           # 系统配置
│   └── requirements.txt        # Python 依赖
├── frontend/                   # Vue3 前端（已构建）
│   ├── src/                    # 源码
│   │   ├── views/              # 页面
│   │   ├── components/         # 组件
│   │   ├── api/                # API 封装
│   │   └── store/              # 状态管理
│   └── dist/                   # 构建产物
└── README.md
```

---
