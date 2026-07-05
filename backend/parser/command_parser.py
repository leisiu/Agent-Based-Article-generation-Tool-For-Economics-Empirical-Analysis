import re
from typing import Dict, Any, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CommandParser:
    def __init__(self):
        # 关键词映射
        self.dependent_keywords = ["被解释变量", "因变量", "被解释项", "因变项"]
        self.independent_keywords = ["解释变量", "自变量", "解释项", "自变项"]
        self.control_keywords = ["控制变量", "控制项", "控制变量包括"]
        self.fixed_effects_keywords = ["固定效应", "固定效应类型", "个体固定效应", "时间固定效应", "双向固定效应"]
        self.cluster_keywords = ["聚类标准误", "聚类", "聚类到"]
        self.test_types_keywords = ["检验类型", "需要检验", "实证检验", "包括检验"]
        
        # 支持的模型类型
        self.supported_models = ["ols", "fe", "re", "logit", "probit", "tobit", "poisson"]
        self.supported_tests = ["descriptive", "correlation", "vif", "regression", "heterogeneity", "robustness"]
    
    def parse(self, command: str) -> Dict[str, Any]:
        """
        解析中文实证研究指令
        """
        result = {
            "dependent_vars": [],
            "independent_vars": [],
            "control_vars": [],
            "fixed_effects": {},
            "cluster_var": None,
            "model_type": "ols",
            "test_types": [],
            "missing_method": "drop",
            "outlier_method": "winsorize",
            "transformations": {},
            "original_command": command
        }
        
        try:
            # 解析变量
            result["dependent_vars"] = self._extract_variables(command, self.dependent_keywords)
            result["independent_vars"] = self._extract_variables(command, self.independent_keywords)
            result["control_vars"] = self._extract_variables(command, self.control_keywords)
            
            # 解析固定效应
            result["fixed_effects"] = self._extract_fixed_effects(command)
            
            # 解析聚类标准误
            result["cluster_var"] = self._extract_cluster_var(command)
            
            # 解析模型类型
            result["model_type"] = self._extract_model_type(command)
            
            # 解析检验类型
            result["test_types"] = self._extract_test_types(command)
            
            # 解析数据处理参数
            result = self._extract_processing_params(command, result)
            
            logger.info(f"指令解析完成: {result}")
            return result
            
        except Exception as e:
            logger.error(f"指令解析失败: {str(e)}")
            return result
    
    def _extract_variables(self, command: str, keywords: List[str]) -> List[str]:
        """
        从指令中提取变量列表
        """
        # 按长度降序排序关键词，优先匹配更长的关键词
        sorted_keywords = sorted(keywords, key=len, reverse=True)
        
        for keyword in sorted_keywords:
            if keyword in command:
                # 找到关键词后面的内容
                # 支持多种格式：关键词：变量、关键词为变量、关键词包括变量
                # 使用非贪婪匹配，只匹配到下一个逗号、句号或其他关键词
                # 使用负向后瞻确保不匹配到包含该关键词的更长关键词（如"解释变量"不匹配"被解释变量"）
                patterns = [
                    f"(?<!被){keyword}[：:](.*?)(?=[，。；；]|$|解释变量|被解释变量|控制变量|使用|模型|聚类|固定效应|检验)",
                    f"(?<!被){keyword}为(.*?)(?=[，。；；]|$|解释变量|被解释变量|控制变量|使用|模型|聚类|固定效应|检验)",
                    f"(?<!被){keyword}包括(.*?)(?=[，。；；]|$|解释变量|被解释变量|控制变量|使用|模型|聚类|固定效应|检验)",
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, command, re.DOTALL)
                    if matches:
                        var_str = matches[0].strip()
                        # 分割变量（支持顿号、逗号、空格、"和"分隔）
                        vars = re.split(r'[，,、\s和]+', var_str)
                        # 过滤空字符串
                        vars = [var.strip() for var in vars if var.strip()]
                        return vars
        
        return []
    
    def _extract_fixed_effects(self, command: str) -> Dict[str, str]:
        """
        解析固定效应类型和对应的列名
        返回字典格式：{"individual": "企业代码", "time": "年度"}
        """
        effects = {}
        
        # 匹配"个体固定效应模型（企业代码）"或"个体固定效应（企业代码）"
        individual_patterns = [
            r"个体固定效应[模型]*[（(](.*?)[）)]",
            r"个体效应[模型]*[（(](.*?)[）)]",
        ]
        
        for pattern in individual_patterns:
            matches = re.findall(pattern, command)
            if matches:
                effects["individual"] = matches[0].strip()
                break
        
        # 如果只提到"个体固定效应"但没有指定列名
        if "individual" not in effects and ("个体固定效应" in command or "个体效应" in command):
            effects["individual"] = ""  # 空字符串表示需要自动检测
        
        # 匹配"时间固定效应模型（年度）"或"时间固定效应（年度）"
        time_patterns = [
            r"时间固定效应[模型]*[（(](.*?)[）)]",
            r"年份固定效应[模型]*[（(](.*?)[）)]",
            r"时间效应[模型]*[（(](.*?)[）)]",
        ]
        
        for pattern in time_patterns:
            matches = re.findall(pattern, command)
            if matches:
                effects["time"] = matches[0].strip()
                break
        
        # 如果只提到"时间固定效应"但没有指定列名
        if "time" not in effects and ("时间固定效应" in command or "年份固定效应" in command or "时间效应" in command):
            effects["time"] = ""
        
        # 双向固定效应
        if "双向固定效应" in command or "双向效应" in command:
            if "individual" not in effects:
                effects["individual"] = ""
            if "time" not in effects:
                effects["time"] = ""
        
        return effects
    
    def _extract_cluster_var(self, command: str) -> Optional[str]:
        """
        解析聚类标准误变量
        """
        # 检查是否有"聚类到企业"、"聚类到行业"等表述
        cluster_patterns = [
            r"聚类到(.*?)(?=[，,。；;]|$|使用|模型)",
            r"按(.*?)聚类(?=[，,。；;]|$|使用|模型)"
        ]
        
        for pattern in cluster_patterns:
            matches = re.findall(pattern, command, re.DOTALL)
            if matches:
                cluster_var = matches[0].strip()
                # 标准化变量名
                if cluster_var in ["企业", "公司", "厂商"]:
                    return "firm"
                elif cluster_var in ["行业", "产业"]:
                    return "industry"
                elif cluster_var in ["地区", "省份", "城市"]:
                    return "region"
                elif cluster_var in ["年份", "时间"]:
                    return "year"
                else:
                    return cluster_var
        
        return None
    
    def _extract_model_type(self, command: str) -> str:
        """
        解析模型类型
        """
        command_lower = command.lower()
        
        if "固定效应" in command or "fe" in command_lower:
            return "fe"
        elif "随机效应" in command or "re" in command_lower:
            return "re"
        elif "logit" in command_lower or "逻辑回归" in command:
            return "logit"
        elif "probit" in command_lower:
            return "probit"
        elif "tobit" in command_lower:
            return "tobit"
        elif "poisson" in command_lower or "泊松回归" in command:
            return "poisson"
        elif "ols" in command_lower or "普通最小二乘" in command or "基准回归" in command:
            return "ols"
        else:
            return "ols"  # 默认OLS
    
    def _extract_test_types(self, command: str) -> List[str]:
        """
        解析需要进行的检验类型
        """
        tests = []
        command_lower = command.lower()
        
        if "描述性统计" in command or "描述统计" in command:
            tests.append("descriptive")
        
        if "相关性分析" in command or "相关分析" in command:
            tests.append("correlation")
        
        if "vif" in command_lower or "多重共线性" in command or "共线性检验" in command:
            tests.append("vif")
        
        if "回归" in command or "基准回归" in command:
            tests.append("regression")
        
        if "异质性分析" in command or "异质性检验" in command:
            tests.append("heterogeneity")
        
        if "稳健性检验" in command or "稳健性" in command:
            tests.append("robustness")
        
        # 如果没有指定任何检验，默认进行基础检验
        if not tests:
            tests = ["descriptive", "correlation", "regression"]
        
        return tests
    
    def _extract_processing_params(self, command: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析数据处理参数
        """
        command_lower = command.lower()
        
        # 缺失值处理
        if "填充缺失值" in command or "缺失值填充" in command:
            result["missing_method"] = "fill"
        elif "插值法" in command or "线性插值" in command:
            result["missing_method"] = "interpolate"
        else:
            result["missing_method"] = "drop"
        
        # 异常值处理
        if "删除异常值" in command or "去掉异常值" in command:
            result["outlier_method"] = "drop"
        elif "盖帽法" in command or "5%盖帽" in command:
            result["outlier_method"] = "cap"
        else:
            result["outlier_method"] = "winsorize"
        
        # 变量转换
        # 查找类似"对GDP取对数"、"将工资标准化"的表述
        transform_patterns = [
            (r"对(.*?)取对数", "log"),
            (r"(.*?)取对数", "log"),
            (r"将(.*?)标准化", "standardize"),
            (r"(.*?)标准化", "standardize"),
            (r"对(.*?)取平方", "square"),
            (r"(.*?)取平方", "square"),
            (r"将(.*?)归一化", "normalize"),
            (r"(.*?)归一化", "normalize")
        ]
        
        transformations = {}
        for pattern, transform_type in transform_patterns:
            matches = re.findall(pattern, command, re.DOTALL)
            for match in matches:
                var_name = match.strip()
                transformations[var_name] = transform_type
        
        if transformations:
            result["transformations"] = transformations
        
        return result
    
    def validate(self, parsed_params: Dict[str, Any], df_columns: List[str]) -> Dict[str, Any]:
        """
        验证解析结果与数据的匹配性
        """
        validation = {
            "is_valid": True,
            "errors": [],
            "warnings": []
        }
        
        # 检查被解释变量
        missing_dep = [var for var in parsed_params["dependent_vars"] if var not in df_columns]
        if missing_dep:
            validation["errors"].append(f"被解释变量在数据中不存在: {', '.join(missing_dep)}")
            validation["is_valid"] = False
        
        # 检查解释变量
        missing_ind = [var for var in parsed_params["independent_vars"] if var not in df_columns]
        if missing_ind:
            validation["errors"].append(f"解释变量在数据中不存在: {', '.join(missing_ind)}")
            validation["is_valid"] = False
        
        # 检查控制变量
        missing_ctrl = [var for var in parsed_params["control_vars"] if var not in df_columns]
        if missing_ctrl:
            validation["warnings"].append(f"控制变量在数据中不存在: {', '.join(missing_ctrl)}")
            # 从控制变量中移除不存在的变量
            parsed_params["control_vars"] = [var for var in parsed_params["control_vars"] if var in df_columns]
        
        # 检查聚类变量
        if parsed_params["cluster_var"] and parsed_params["cluster_var"] not in df_columns:
            validation["warnings"].append(f"聚类变量在数据中不存在: {parsed_params['cluster_var']}")
            parsed_params["cluster_var"] = None
        
        # 检查是否至少有一个被解释变量和一个解释变量
        if not parsed_params["dependent_vars"]:
            validation["errors"].append("未指定被解释变量")
            validation["is_valid"] = False
        
        if not parsed_params["independent_vars"]:
            validation["errors"].append("未指定解释变量")
            validation["is_valid"] = False
        
        return validation
