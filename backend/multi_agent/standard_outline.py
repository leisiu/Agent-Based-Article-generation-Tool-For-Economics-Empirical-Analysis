"""
标准化论文大纲模板


- 每个章节有固定的小节标题和写作要点
- 写作 agent 直接按这个模板逐节生成

"""

# 论文固定一级章节结构（基于 project_memory 中的论文结构约束）
STANDARD_OUTLINE = {
    "title": "",
    "sections": [
        {
            "title": "一、引言",
            "order": 1,
            "subsections": [
                {
                    "title": "1.1 研究背景与意义",
                    "content_requirement": "阐述研究主题的现实背景、理论意义和实践意义，"
                                          "指出该领域的研究价值和紧迫性。"
                },
                {
                    "title": "1.2 研究问题与研究内容",
                    "content_requirement": "明确提出本文拟解决的核心研究问题，"
                                          "简述研究框架和主要研究内容。"
                },
                {
                    "title": "1.3 研究创新与贡献",
                    "content_requirement": "总结本文的创新点（理论创新、方法创新、视角创新）"
                                          "和边际贡献，突出本文与已有研究的不同之处。"
                                          "**注意：研究方法、数据来源和模型设定等内容将在「三、研究设计」章节详细阐述，本节请勿涉及。**"
                },
            ],
        },
        {
            "title": "二、文献综述",
            "order": 2,
            "subsections": [
                {
                    "title": "2.1 核心理论基础",
                    "content_requirement": "梳理本文涉及的核心理论（如信息不对称理论、"
                                          "委托代理理论、融资优序理论等）的发展脉络。"
                },
                {
                    "title": "2.2 核心变量研究进展",
                    "content_requirement": "回顾核心解释变量、被解释变量的相关实证研究，"
                                          "总结已有研究的方法和发现。"
                },
                {
                    "title": "2.3 研究假设提出",
                    "content_requirement": "在文献梳理的基础上，提出本文的研究假设，"
                                          "说明假设的理论依据和预期方向。"
                },
            ],
        },
        {
            "title": "三、研究设计",
            "order": 3,
            "subsections": [
                {
                    "title": "3.1 样本选择与数据来源",
                    "content_requirement": "说明数据来源、样本筛选条件、样本期间和样本规模。"
                },
                {
                    "title": "3.2 变量定义与测度",
                    "content_requirement": "详细定义被解释变量、核心解释变量、控制变量、"
                                          "中介变量、调节变量及其测度方式。"
                },
                {
                    "title": "3.3 计量模型设定",
                    "content_requirement": "呈现基准回归模型、稳健性检验模型、"
                                          "异质性分析模型和机制检验模型的具体设定。"
                },
            ],
        },
        {
            "title": "四、实证分析",
            "order": 4,
            "subsections": [
                {
                    "title": "4.1 描述性统计分析",
                    "content_requirement": "（本小节内容由数据智能体基于真实数据自动生成，"
                                          "写作 agent 不要在本节中编造任何数据或表格）"
                },
                {
                    "title": "4.2 相关性分析",
                    "content_requirement": "（本小节内容由数据智能体基于真实数据自动生成，"
                                          "写作 agent 不要在本节中编造任何数据或表格）"
                },
                {
                    "title": "4.3 基准回归",
                    "content_requirement": "（本小节内容由数据智能体基于真实数据自动生成，"
                                          "写作 agent 不要在本节中编造任何数据或表格）"
                },
                {
                    "title": "4.4 稳健性检验",
                    "content_requirement": "（本小节内容由数据智能体基于真实数据自动生成，"
                                          "写作 agent 不要在本节中编造任何数据或表格）"
                },
                {
                    "title": "4.5 异质性分析",
                    "content_requirement": "（本小节内容由数据智能体基于真实数据自动生成，"
                                          "写作 agent 不要在本节中编造任何数据或表格）"
                },
                {
                    "title": "4.6 机制检验",
                    "content_requirement": "（本小节内容由数据智能体基于真实数据自动生成，"
                                          "写作 agent 不要在本节中编造任何数据或表格）"
                },
            ],
        },
        {
            "title": "五、研究结论与政策建议",
            "order": 5,
            "subsections": [
                {
                    "title": "5.1 主要研究结论",
                    "content_requirement": "概括本文的核心研究结论，使用自然语言描述"
                                          "（如「X 对 Y 有显著的正向影响」），"
                                          "**严禁出现任何具体的回归系数、p 值、t 值**。"
                },
                {
                    "title": "5.2 政策建议与启示",
                    "content_requirement": "基于研究结论提出针对性的政策建议和管理启示，"
                                          "建议应当具体、可操作、有理论支撑。"
                },
                {
                    "title": "5.3 研究局限与未来展望",
                    "content_requirement": "客观指出本文的研究局限（如样本范围、"
                                          "变量选择、方法局限等），并提出未来研究方向。"
                },
            ],
        },
    ],
}


def get_standard_outline(command: str = "") -> dict:
    """获取标准化的论文大纲模板

    Args:
        command: 研究指令（仅用于生成论文标题前缀）

    Returns:
        完整的大纲 dict，可直接传入 academic_writer_agent
    """
    import copy
    outline = copy.deepcopy(STANDARD_OUTLINE)
    # 标题默认为研究指令的前 50 字
    outline["title"] = (command or "实证研究论文")[:50]
    return outline
