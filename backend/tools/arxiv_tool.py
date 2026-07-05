"""
arXiv文献搜索工具

完全遵循 arXiv API 官方文档：
  http://info.arxiv.org/help/api/user-manual.html
  http://info.arxiv.org/help/api/examples/python_arXiv_parsing_example.txt

搜索语法：
  - prefix:term  如 all:electron, ti:attention, cat:cs.LG
  - 多词用 AND/OR 组合：au:bengio AND ti:deep learning
  - 空格表示 OR：ti:deep learning = ti:deep OR ti:learning
  - 精确短语需要用 %22 包裹：ti:%22deep+learning%22
  - category 不支持通配符 *，必须列出具体子类
"""

import urllib.request
import urllib.parse
import logging
from typing import List, Dict, Optional
import time


class ArxivTool:
    """arXiv文献搜索工具类"""

    # 经管实证论文相关 arXiv 分类（来自官方分类体系）
    # 经济学在 arXiv 上归入 q-fin（ Quantitative Finance）大类
    ECON_CATEGORIES = [
        "q-fin.EC",  # Economics（经济学）
        "q-fin.GN",  # General Finance（财务概述）
        "q-fin.ST",  # Statistical Finance（金融统计）
        "q-fin.RM",  # Risk Management（风险管理）
        "q-fin.CP",  # Computational Finance（金融工程）
        "q-fin.MF",  # Mathematical Finance（数学金融）
        "q-fin.PM",  # Portfolio Management（投资组合管理）
        "q-fin.PR",  # Pricing of Securities（证券定价）
        "q-fin.TR",  # Trading and Market Microstructure（交易与市场微观结构）
        "stat.AP",   # Applications（应用统计）
        "stat.ME",   # Methodology（统计方法论）
        "stat.ML",   # Machine Learning（机器学习）
        "stat.CO",   # Computation（统计计算）
        "stat.TH",   # Statistics Theory（统计学理论）
    ]

    def __init__(self):
        self.base_url = "http://export.arxiv.org/api/query"
        self.logger = logging.getLogger("ArxivTool")

    def _format_keyword(self, keyword: str) -> str:
        """将关键词格式化为 arxiv 查询 term

        - 单空格词视为短语，用 %22 + 包裹（精确匹配）
        - 无空格词直接使用
        """
        kw = keyword.strip()
        if not kw:
            return ""
        if " " in kw:
            # 多词短语：精确匹配
            return f"%22{urllib.parse.quote(kw)}%22"
        else:
            return kw

    def _build_search_query(self, keyword: str, relevant_only: bool = True) -> str:
        """构建 search_query 参数字符串

        官方示例构造方式：手动拼接 prefix:term + AND/OR，不使用 urlencode。
        """
        kw_term = self._format_keyword(keyword)
        if not kw_term:
            return ""

        if relevant_only:
            # 类别限制：cat:econ.EM+OR+cat:econ.GN+OR+...
            cat_parts = [f"cat:{c}" for c in self.ECON_CATEGORIES]
            cat_query = "+OR+".join(cat_parts)
            return f"all:{kw_term}+AND+({cat_query})"
        else:
            return f"all:{kw_term}"

    def search_by_keyword(self, keyword: str, max_results: int = 10, relevant_only: bool = True) -> List[Dict]:
        """根据关键词搜索 arXiv 论文

        Args:
            relevant_only: True 时限制类别为经济学及相关学科
        """
        search_query = self._build_search_query(keyword, relevant_only)
        if not search_query:
            return []

        try:
            # 按官方示例手动拼接 URL
            url = (f"{self.base_url}?search_query={search_query}"
                   f"&start=0&max_results={max_results}"
                   f"&sortBy=submittedDate&sortOrder=descending")

            self.logger.info(f"搜索: {url}")
            with urllib.request.urlopen(url, timeout=60) as response:
                xml_content = response.read().decode("utf-8")

            papers = self._parse_response(xml_content)
            self.logger.info(f"  结果: {len(papers)} 篇论文")
            return papers

        except Exception as e:
            self.logger.error(f"arXiv搜索失败: {str(e)}")
            return []

    def search_multiple(self, keywords: List[str], max_per_query: int = 10) -> List[Dict]:
        """根据多个关键词搜索（去重：按标题去重，保留第一次出现的结果）

        流程：
          1. 先用类别限制搜索所有关键词
          2. 若结果 < 30 篇，再用不限类别补充搜索前 10 个最相关关键词
          3. 合并去重后返回
        """
        all_papers = []
        seen_titles = set()

        # 第一轮：类别过滤搜索
        for keyword in keywords:
            papers = self.search_by_keyword(keyword, max_per_query, relevant_only=True)
            for p in papers:
                t = (p.get("title") or "").lower().strip()
                if t and t not in seen_titles:
                    seen_titles.add(t)
                    all_papers.append(p)
            time.sleep(3)  # 遵守速率限制

        self.logger.info(f"类别搜索完成: {len(keywords)} 个关键词, 去重后 {len(all_papers)} 篇论文")

        # 如果类别搜索结果太少（< 30 篇），用不限类别补充搜索
        MIN_PAPERS = 30
        if len(all_papers) < MIN_PAPERS:
            # 用前 10 个关键词做补充搜索（不限类别）
            supplement_keywords = keywords[:10]
            self.logger.info(f"类别搜索仅 {len(all_papers)} 篇 < {MIN_PAPERS}，补充不限类别搜索 (前 {len(supplement_keywords)} 个关键词)")
            for keyword in supplement_keywords:
                papers = self.search_by_keyword(keyword, max_per_query, relevant_only=False)
                for p in papers:
                    t = (p.get("title") or "").lower().strip()
                    if t and t not in seen_titles:
                        seen_titles.add(t)
                        all_papers.append(p)
                time.sleep(3)

            self.logger.info(f"补充搜索完成: 共 {len(all_papers)} 篇论文")

        # 最终裁剪：最多返回 50 篇
        if len(all_papers) > 50:
            self.logger.info(f"裁剪至 50 篇（原 {len(all_papers)} 篇）")
            all_papers = all_papers[:50]
        return all_papers
    
    def _parse_response(self, xml_content: str) -> List[Dict]:
        """解析 arXiv API 返回的 XML（Atom 格式）"""
        try:
            import xml.etree.ElementTree as ET
            
            root = ET.fromstring(xml_content)
            papers = []
            
            for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                title = entry.find("{http://www.w3.org/2005/Atom}title").text.strip()
                summary = entry.find("{http://www.w3.org/2005/Atom}summary").text.strip()
                published = entry.find("{http://www.w3.org/2005/Atom}published").text[:4]
                
                authors = []
                for author in entry.findall("{http://www.w3.org/2005/Atom}author"):
                    name = author.find("{http://www.w3.org/2005/Atom}name").text
                    authors.append(name)
                
                papers.append({
                    "title": title,
                    "authors": authors,
                    "year": published,
                    "summary": summary,
                    "source": "arXiv",
                    "arxiv_id": entry.find("{http://www.w3.org/2005/Atom}id").text.split("/")[-1]
                })
            
            return papers
        
        except Exception as e:
            self.logger.error(f"解析arXiv响应失败: {str(e)}")
            return []


# 全局实例
arxiv_tool = ArxivTool()
