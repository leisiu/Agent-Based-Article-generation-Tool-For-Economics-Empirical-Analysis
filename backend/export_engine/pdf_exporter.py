from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
import pandas as pd
import os
from typing import Dict, Any
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFExporter:
    def __init__(self):
        self.export_dir = "exports"
        os.makedirs(self.export_dir, exist_ok=True)
        
        # 注册中文字体（使用系统字体）
        self._register_fonts()
    
    def _register_fonts(self):
        """注册中文字体"""
        try:
            # Windows系统字体路径
            font_paths = {
                'SimSun': r'C:\Windows\Fonts\simsun.ttc',
                'SimHei': r'C:\Windows\Fonts\simhei.ttf',
                'MicrosoftYaHei': r'C:\Windows\Fonts\msyh.ttc',
            }
            
            for font_name, font_path in font_paths.items():
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont(font_name, font_path))
                        logger.info(f"成功注册字体: {font_name}")
                    except Exception as e:
                        logger.warning(f"注册字体 {font_name} 失败: {e}")
            
            # 设置默认字体
            self.default_font = 'SimSun'
            self.heading_font = 'SimHei'
            
        except Exception as e:
            logger.warning(f"字体注册失败，将使用默认字体: {e}")
            self.default_font = 'Helvetica'
            self.heading_font = 'Helvetica-Bold'
    
    def export_analysis_results(self, empirical_results: Dict[str, Any], project_name: str) -> str:
        """
        导出分析结果为PDF
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            pdf_path = os.path.join(self.export_dir, f"实证分析结果_{project_name}_{timestamp}.pdf")
            
            # 创建PDF文档
            doc = SimpleDocTemplate(
                pdf_path,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )
            
            # 创建样式
            styles = self._create_styles()
            
            # 构建PDF内容
            story = []
            
            # 标题
            story.append(Paragraph(f'实证分析结果报告', styles['Title']))
            story.append(Spacer(1, 12))
            story.append(Paragraph(f'项目名称: {project_name}', styles['Normal']))
            story.append(Paragraph(f'生成日期: {datetime.now().strftime("%Y年%m月%d日 %H:%M")}', styles['Normal']))
            story.append(Spacer(1, 24))
            
            # 描述性统计
            if "descriptive" in empirical_results:
                story.append(Paragraph('1. 描述性统计', styles['Heading1']))
                story.append(Spacer(1, 12))
                self._add_descriptive_table(story, empirical_results["descriptive"], styles)
                story.append(PageBreak())
            
            # 相关性分析
            if "correlation" in empirical_results:
                story.append(Paragraph('2. 相关性分析', styles['Heading1']))
                story.append(Spacer(1, 12))
                self._add_correlation_table(story, empirical_results["correlation"], styles)
                story.append(PageBreak())
            
            # VIF检验
            if "vif" in empirical_results:
                story.append(Paragraph('3. VIF多重共线性检验', styles['Heading1']))
                story.append(Spacer(1, 12))
                self._add_vif_table(story, empirical_results["vif"], styles)
                story.append(PageBreak())
            
            # 回归结果
            if "regression" in empirical_results:
                story.append(Paragraph('4. 回归结果', styles['Heading1']))
                story.append(Spacer(1, 12))
                self._add_regression_tables(story, empirical_results["regression"], styles)
                story.append(PageBreak())
            
            # 稳健性检验
            if "robustness" in empirical_results:
                story.append(Paragraph('5. 稳健性检验', styles['Heading1']))
                story.append(Spacer(1, 12))
                self._add_robustness_tables(story, empirical_results["robustness"], styles)
            
            # 构建PDF
            doc.build(story)
            
            logger.info(f"PDF导出成功: {pdf_path}")
            return pdf_path
            
        except Exception as e:
            logger.error(f"PDF导出失败: {str(e)}")
            raise
    
    def _create_styles(self):
        """创建PDF样式"""
        styles = getSampleStyleSheet()
        
        # 标题样式
        styles.add(ParagraphStyle(
            name='Title',
            fontName=self.heading_font,
            fontSize=24,
            leading=30,
            alignment=TA_CENTER,
            spaceAfter=10,
            textColor=HexColor('#1a1a1a')
        ))
        
        # 一级标题样式
        styles.add(ParagraphStyle(
            name='Heading1',
            fontName=self.heading_font,
            fontSize=16,
            leading=20,
            spaceBefore=20,
            spaceAfter=10,
            textColor=HexColor('#2c3e50')
        ))
        
        # 二级标题样式
        styles.add(ParagraphStyle(
            name='Heading2',
            fontName=self.heading_font,
            fontSize=14,
            leading=18,
            spaceBefore=15,
            spaceAfter=8,
            textColor=HexColor('#34495e')
        ))
        
        # 正文样式
        styles.add(ParagraphStyle(
            name='Normal',
            fontName=self.default_font,
            fontSize=10,
            leading=14,
            alignment=TA_LEFT,
            spaceAfter=6
        ))
        
        # 表格标题样式
        styles.add(ParagraphStyle(
            name='TableTitle',
            fontName=self.heading_font,
            fontSize=11,
            leading=14,
            alignment=TA_CENTER,
            spaceAfter=8,
            textColor=HexColor('#2c3e50')
        ))
        
        return styles
    
    def _add_descriptive_table(self, story, descriptive_results, styles):
        """添加描述性统计表格"""
        try:
            variables = descriptive_results.get("variables", {})
            if not variables:
                story.append(Paragraph("无描述性统计数据", styles['Normal']))
                return
            
            # 构建表格数据
            data = [['变量', '样本量', '均值', '标准差', '最小值', '中位数', '最大值']]
            
            for var_name, stats in variables.items():
                row = [
                    var_name,
                    str(int(stats.get('count', 0))),
                    f"{stats.get('mean', 0):.4f}",
                    f"{stats.get('std', 0):.4f}",
                    f"{stats.get('min', 0):.4f}",
                    f"{stats.get('median', 0):.4f}",
                    f"{stats.get('max', 0):.4f}"
                ]
                data.append(row)
            
            # 创建表格
            table = Table(data, colWidths=[1.2*inch, 0.8*inch, 0.9*inch, 0.9*inch, 0.9*inch, 0.9*inch, 0.9*inch])
            
            # 设置表格样式
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor('#3498db')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), self.heading_font),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), HexColor('#ecf0f1')),
                ('TEXTCOLOR', (0, 1), (-1, -1), HexColor('#2c3e50')),
                ('FONTNAME', (0, 1), (-1, -1), self.default_font),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 1, HexColor('#bdc3c7')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#ffffff'), HexColor('#f8f9fa')]),
            ]))
            
            story.append(table)
            
        except Exception as e:
            logger.error(f"添加描述性统计表格失败: {e}")
            story.append(Paragraph("描述性统计数据格式错误", styles['Normal']))
    
    def _add_correlation_table(self, story, correlation_results, styles):
        """添加相关性分析表格"""
        try:
            pearson = correlation_results.get("pearson", {})
            if not pearson:
                story.append(Paragraph("无相关性分析数据", styles['Normal']))
                return
            
            # 获取变量列表
            variables = list(pearson.keys())
            
            # 构建表格数据
            header = ['变量'] + variables
            data = [header]
            
            for var1 in variables:
                row = [var1]
                for var2 in variables:
                    corr_value = pearson[var1].get(var2, 0)
                    row.append(f"{corr_value:.4f}")
                data.append(row)
            
            # 创建表格
            col_widths = [1.0*inch] + [0.8*inch] * len(variables)
            table = Table(data, colWidths=col_widths[:len(header)])
            
            # 设置表格样式
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor('#3498db')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), self.heading_font),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BACKGROUND', (0, 1), (0, -1), HexColor('#3498db')),
                ('TEXTCOLOR', (0, 1), (0, -1), colors.whitesmoke),
                ('FONTNAME', (0, 1), (0, -1), self.heading_font),
                ('FONTSIZE', (0, 1), (0, -1), 9),
                ('BACKGROUND', (1, 1), (-1, -1), HexColor('#ecf0f1')),
                ('FONTNAME', (1, 1), (-1, -1), self.default_font),
                ('FONTSIZE', (1, 1), (-1, -1), 8),
                ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 1, HexColor('#bdc3c7')),
            ]))
            
            story.append(table)
            
        except Exception as e:
            logger.error(f"添加相关性分析表格失败: {e}")
            story.append(Paragraph("相关性分析数据格式错误", styles['Normal']))
    
    def _add_vif_table(self, story, vif_results, styles):
        """添加VIF检验表格"""
        try:
            vif_data = vif_results.get("vif_values", {})
            if not vif_data:
                story.append(Paragraph("无VIF检验数据", styles['Normal']))
                return
            
            # 构建表格数据
            data = [['变量', 'VIF值', '判断']]
            
            for var_name, vif_value in vif_data.items():
                if vif_value > 10:
                    judgment = "严重共线性"
                elif vif_value > 5:
                    judgment = "中度共线性"
                else:
                    judgment = "无共线性问题"
                
                data.append([
                    var_name,
                    f"{vif_value:.4f}",
                    judgment
                ])
            
            # 创建表格
            table = Table(data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
            
            # 设置表格样式
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor('#3498db')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), self.heading_font),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), HexColor('#ecf0f1')),
                ('FONTNAME', (0, 1), (-1, -1), self.default_font),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 1, HexColor('#bdc3c7')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#ffffff'), HexColor('#f8f9fa')]),
            ]))
            
            story.append(table)
            
        except Exception as e:
            logger.error(f"添加VIF表格失败: {e}")
            story.append(Paragraph("VIF检验数据格式错误", styles['Normal']))
    
    def _add_regression_tables(self, story, regression_results, styles):
        """添加回归结果表格"""
        try:
            for model_name, model_result in regression_results.items():
                if not isinstance(model_result, dict):
                    continue
                
                story.append(Paragraph(f'{model_result.get("model_name", model_name)} 回归结果', styles['Heading2']))
                story.append(Spacer(1, 8))
                
                coefficients = model_result.get("coefficients", {})
                if not coefficients:
                    story.append(Paragraph("无回归系数数据", styles['Normal']))
                    continue
                
                # 构建表格数据
                data = [['变量', '系数', '标准误', 't值', 'P值', '显著性']]
                
                for var_name, coef_data in coefficients.items():
                    coef = coef_data.get('coef', 0)
                    std_err = coef_data.get('std_err', 0)
                    t_value = coef_data.get('t_value', 0)
                    p_value = coef_data.get('p_value', 1)
                    
                    # 显著性标记
                    if p_value < 0.01:
                        significance = '***'
                    elif p_value < 0.05:
                        significance = '**'
                    elif p_value < 0.1:
                        significance = '*'
                    else:
                        significance = ''
                    
                    data.append([
                        var_name,
                        f"{coef:.4f}",
                        f"{std_err:.4f}",
                        f"{t_value:.4f}",
                        f"{p_value:.4f}",
                        significance
                    ])
                
                # 创建表格
                table = Table(data, colWidths=[1.3*inch, 0.9*inch, 0.9*inch, 0.9*inch, 0.9*inch, 0.7*inch])
                
                # 设置表格样式
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), HexColor('#3498db')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), self.heading_font),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), HexColor('#ecf0f1')),
                    ('FONTNAME', (0, 1), (-1, -1), self.default_font),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                    ('GRID', (0, 0), (-1, -1), 1, HexColor('#bdc3c7')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#ffffff'), HexColor('#f8f9fa')]),
                ]))
                
                story.append(table)
                story.append(Spacer(1, 6))
                
                # 添加模型统计量
                stats = model_result.get("model_stats", {})
                stats_text = f"样本量: {stats.get('n_obs', 'N/A')}  |  R²: {stats.get('r_squared', 'N/A'):.4f}  |  调整R²: {stats.get('adj_r_squared', 'N/A'):.4f}  |  F值: {stats.get('f_statistic', 'N/A'):.4f}"
                story.append(Paragraph(stats_text, styles['Normal']))
                story.append(Spacer(1, 12))
                
        except Exception as e:
            logger.error(f"添加回归表格失败: {e}")
            story.append(Paragraph("回归结果数据格式错误", styles['Normal']))
    
    def _add_robustness_tables(self, story, robustness_results, styles):
        """添加稳健性检验表格"""
        try:
            if not isinstance(robustness_results, dict):
                story.append(Paragraph("无稳健性检验数据", styles['Normal']))
                return
            
            for test_name, test_result in robustness_results.items():
                story.append(Paragraph(f'{test_result.get("test_name", test_name)}', styles['Heading2']))
                story.append(Spacer(1, 8))
                
                # 添加检验说明
                description = test_result.get("description", "")
                if description:
                    story.append(Paragraph(description, styles['Normal']))
                    story.append(Spacer(1, 6))
                
                # 添加结果表格（如果有）
                if "results" in test_result:
                    results = test_result["results"]
                    if isinstance(results, dict):
                        data = [['指标', '结果']]
                        for key, value in results.items():
                            data.append([key, str(value)])
                        
                        table = Table(data, colWidths=[2.5*inch, 3*inch])
                        table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#3498db')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('FONTNAME', (0, 0), (-1, 0), self.heading_font),
                            ('FONTSIZE', (0, 0), (-1, 0), 10),
                            ('BACKGROUND', (0, 1), (-1, -1), HexColor('#ecf0f1')),
                            ('FONTNAME', (0, 1), (-1, -1), self.default_font),
                            ('FONTSIZE', (0, 1), (-1, -1), 9),
                            ('GRID', (0, 0), (-1, -1), 1, HexColor('#bdc3c7')),
                        ]))
                        story.append(table)
                
                story.append(Spacer(1, 12))
                
        except Exception as e:
            logger.error(f"添加稳健性检验表格失败: {e}")
            story.append(Paragraph("稳健性检验数据格式错误", styles['Normal']))
