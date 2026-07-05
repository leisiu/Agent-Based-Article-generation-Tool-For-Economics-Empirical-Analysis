import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from scipy import stats
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataPreprocessor:
    def __init__(self):
        self.processing_report = []
    
    def process(self, file_path: str, params: Dict[str, Any]) -> pd.DataFrame:
        """
        完整的数据预处理流程
        """
        self.processing_report = []
        
        # 1. 读取数据
        df = self._read_data(file_path)
        
        # 2. 数据初步探查
        self._data_exploration(df)
        
        # 3. 缺失值处理
        df = self._handle_missing_values(df, params)
        
        # 4. 异常值处理
        df = self._handle_outliers(df, params)
        
        # 5. 变量转换
        df = self._transform_variables(df, params)
        
        # 6. 生成处理报告
        self._generate_processing_report(df)
        
        logger.info("数据预处理完成")
        return df
    
    def _read_data(self, file_path: str) -> pd.DataFrame:
        """
        读取不同格式的数据文件
        """
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path, encoding='utf-8-sig')
            elif file_path.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
            elif file_path.endswith('.dta'):
                df = pd.read_stata(file_path)
            else:
                raise ValueError(f"不支持的文件格式: {file_path}")

            logger.info(f"成功读取数据，样本量: {len(df)}，变量数: {len(df.columns)}")
            self.processing_report.append(f"成功读取数据，样本量: {len(df)}，变量数: {len(df.columns)}")

            return df

        except Exception as e:
            logger.error(f"读取数据失败: {str(e)}")
            raise
    
    def _data_exploration(self, df: pd.DataFrame):
        """
        数据初步探查
        """
        report = []
        report.append(f"数据基本信息:")
        report.append(f"  样本量: {len(df)}")
        report.append(f"  变量数: {len(df.columns)}")
        report.append(f"  数值型变量数: {len(df.select_dtypes(include=[np.number]).columns)}")
        report.append(f"  字符型变量数: {len(df.select_dtypes(include=['object']).columns)}")
        
        # 缺失值统计
        missing_stats = df.isnull().sum()[df.isnull().sum() > 0]
        if not missing_stats.empty:
            report.append(f"\n缺失值统计:")
            for col, count in missing_stats.items():
                report.append(f"  {col}: {count} ({count/len(df)*100:.2f}%)")
        
        self.processing_report.extend(report)
    
    def _handle_missing_values(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """
        处理缺失值：默认直接删除含缺失值的样本（dropna）。
        不自动删除高缺失率列，只删行。
        """
        method = params.get('missing_method', 'drop')
        
        self.processing_report.append(f"\n缺失值处理方法: {method}")
        
        if method == 'drop':
            original_count = len(df)
            df = df.dropna()
            self.processing_report.append(f"  删除含缺失值的样本，剩余样本量: {len(df)} (删除{original_count - len(df)}个样本)")
        
        elif method == 'fill':
            # 数值型变量用中位数填充
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].median())
            
            # 分类变量用众数填充
            categorical_cols = df.select_dtypes(include=['object']).columns
            for col in categorical_cols:
                df[col] = df[col].fillna(df[col].mode()[0] if not df[col].mode().empty else 'Unknown')
            
            self.processing_report.append(f"  缺失值填充完成: 数值型变量用中位数，分类变量用众数")
        
        elif method == 'interpolate':
            df = df.interpolate(method='linear')
            self.processing_report.append(f"  线性插值填充缺失值完成")
        
        return df
    
    def _handle_outliers(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """
        处理异常值：默认不处理（none）。
        """
        method = params.get('outlier_method', 'none')
        threshold = params.get('outlier_threshold', 0.01)
        
        self.processing_report.append(f"\n异常值处理方法: {method}")
        
        if method == 'none':
            self.processing_report.append(f"  不进行异常值处理")
            return df
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        if method == 'drop':
            # 使用3σ原则删除异常值
            original_count = len(df)
            for col in numeric_cols:
                mean = df[col].mean()
                std = df[col].std()
                df = df[(df[col] > mean - 3*std) & (df[col] < mean + 3*std)]
            self.processing_report.append(f"  删除3σ以外的异常值，剩余样本量: {len(df)} (删除{original_count - len(df)}个样本)")
        
        elif method == 'winsorize':
            # 缩尾处理
            for col in numeric_cols:
                lower = df[col].quantile(threshold)
                upper = df[col].quantile(1 - threshold)
                df[col] = np.clip(df[col], lower, upper)
            self.processing_report.append(f"  {int(threshold*100)}%水平缩尾处理完成")
        
        elif method == 'cap':
            # 盖帽处理
            for col in numeric_cols:
                lower = df[col].quantile(0.05)
                upper = df[col].quantile(0.95)
                df[col] = np.where(df[col] < lower, lower, df[col])
                df[col] = np.where(df[col] > upper, upper, df[col])
            self.processing_report.append(f"  5%/95%盖帽处理完成")
        
        return df
    
    def _transform_variables(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """
        变量转换
        """
        transformations = params.get('transformations', {})
        
        if transformations:
            self.processing_report.append(f"\n变量转换:")
            
            for col, transform_type in transformations.items():
                if col not in df.columns:
                    continue
                    
                if transform_type == 'log':
                    # 对数转换（加1避免0值）
                    df[f'log_{col}'] = np.log1p(df[col])
                    self.processing_report.append(f"  {col}: 对数转换为log_{col}")
                
                elif transform_type == 'square':
                    df[f'sq_{col}'] = df[col] ** 2
                    self.processing_report.append(f"  {col}: 平方转换为sq_{col}")
                
                elif transform_type == 'standardize':
                    df[f'std_{col}'] = (df[col] - df[col].mean()) / df[col].std()
                    self.processing_report.append(f"  {col}: 标准化转换为std_{col}")
                
                elif transform_type == 'normalize':
                    df[f'norm_{col}'] = (df[col] - df[col].min()) / (df[col].max() - df[col].min())
                    self.processing_report.append(f"  {col}: 归一化转换为norm_{col}")
        
        # 根据指令中的变量列表筛选变量
        if 'variables' in params:
            variables = params['variables']
            # 确保所有指定的变量都存在
            valid_vars = [var for var in variables if var in df.columns]
            df = df[valid_vars]
            self.processing_report.append(f"\n根据指令筛选变量，剩余变量数: {len(df.columns)}")
        
        return df
    
    def _generate_processing_report(self, df: pd.DataFrame):
        """
        生成完整的处理报告
        """
        final_report = ["="*50, "数据预处理报告", "="*50]
        final_report.extend(self.processing_report)
        final_report.append("\n" + "="*50)
        final_report.append(f"处理完成后样本量: {len(df)}")
        final_report.append(f"处理完成后变量数: {len(df.columns)}")
        final_report.append("="*50)
        
        self.processing_report = final_report
        
        # 打印报告
        print('\n'.join(final_report))
    
    def get_processing_report(self) -> List[str]:
        """
        获取预处理报告
        """
        return self.processing_report
