# -*- coding: utf-8 -*-
"""
potential.py - 场景4：高潜客户。返回结构化数据用于前端渲染表格，并使用 pandas 导出 Excel 文件。
"""

import os
import pandas as pd
from utils.mock_db import POTENTIAL_CLIENTS
from utils.file_helper import ensure_dir
import utils.db_helper as db

def handle(keyword: str, user_id: int = None) -> dict:
    """
    筛选高潜客户列表，导出 Excel 文件供下载，并向前端返回结构化的表格数据。
    """
    db.log_event(user_id, "potential", "INFO", f"开始检索高潜客户线索并打包 Excel。查询词: '{keyword or '全部'}'")
    clients = POTENTIAL_CLIENTS
    
    # 模糊筛选高潜客户的行业或名称
    filtered_clients = []
    if keyword:
        # 去掉如“行业”、“客户”等干扰词，只保留词根
        clean_keyword = keyword.replace("行业", "").replace("客户", "").strip().lower()
        for client in clients:
            if (clean_keyword in client["name"].lower() or 
                clean_keyword in client["industry"].lower()):
                filtered_clients.append(client)
                
    # 如果没有筛选到或没有提供关键词，默认返回全部
    if not filtered_clients:
        filtered_clients = clients
        
    # 确定保存路径（在 static/generated/ 目录下）
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(base_dir, "static", "generated")
    ensure_dir(static_dir)
    
    excel_filename = "high_potential_clients.xlsx"
    excel_path = os.path.join(static_dir, excel_filename)
    web_url = f"/static/generated/{excel_filename}"
    
    excel_status = "success"
    try:
        # 1. 转换为 DataFrame 准备导出
        df = pd.DataFrame(filtered_clients)
        
        # 重命名表头为美观的中文
        df_excel = df.rename(columns={
            "name": "企业名称",
            "industry": "行业领域",
            "scale": "企业规模",
            "score": "商机匹配分 (满分100)",
            "reason": "商机推荐背景与理由",
            "contact": "核心对接人",
            "link": "外部跳转详情链接"
        })
        
        # 移去对外部用户无用的 ID 字段
        if "id" in df_excel.columns:
            df_excel = df_excel.drop(columns=["id"])
            
        # 2. 导出为 Excel 文件
        df_excel.to_excel(excel_path, index=False)
        db.log_event(user_id, "potential", "INFO", f"成功生成 Excel 线索报表。保存路径: {excel_path}")
        
    except Exception as e:
        import traceback
        db.log_event(user_id, "potential", "ERROR", f"高潜线索导出 Excel 失败: {str(e)}", traceback.format_exc())
        excel_status = "failed"
        
    # 3. 返回结构化表格数据和 Excel 下载链接
    return {
        "type": "table",
        "headers": [
            {"key": "name", "label": "企业名称"},
            {"key": "industry", "label": "行业领域"},
            {"key": "scale", "label": "企业规模"},
            {"key": "score", "label": "意向评分"},
            {"key": "reason", "label": "商机推荐背景"},
            {"key": "contact", "label": "核心联系人"}
        ],
        "data": filtered_clients,
        "excel_url": web_url if excel_status == "success" else None,
        "count": len(filtered_clients)
    }
