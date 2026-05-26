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
    
    # 1. 动态查询 MySQL 数据库 ranking_ent_dtl_clue 表
    db_ok = False
    raw_res = []
    
    if keyword:
        # 去掉干扰词，提取核心词根
        clean_keyword = keyword.replace("行业", "").replace("客户", "").replace("领域", "").strip()
        sql = """
            SELECT `企业名称`, `资质名称`, `补贴金额万元`, `客户区局`, `客户经理名称`, `集团分群二`, `工商行业`, `企业25年收入_万元`, `链接`
            FROM ranking_ent_dtl_clue
            WHERE `企业名称` LIKE :kw OR `工商行业` LIKE :kw OR `根营销行业一层` LIKE :kw
            ORDER BY `补贴金额万元` DESC
            LIMIT 50
        """
        params = {"kw": f"%{clean_keyword}%"}
    else:
        sql = """
            SELECT `企业名称`, `资质名称`, `补贴金额万元`, `客户区局`, `客户经理名称`, `集团分群二`, `工商行业`, `企业25年收入_万元`, `链接`
            FROM ranking_ent_dtl_clue
            ORDER BY `补贴金额万元` DESC
            LIMIT 50
        """
        params = {}
        
    try:
        raw_res = db.query_business_db(sql, params)
        if raw_res:
            db_ok = True
            db.log_event(user_id, "potential", "INFO", f"MySQL 动态直连查询高潜线索成功，获得 {len(raw_res)} 条数据。")
    except Exception as e:
        db.log_event(user_id, "potential", "ERROR", f"MySQL 查询高潜线索发生异常: {e}")
        db_ok = False
        
    # 2. 组装结构化高潜企业列表
    filtered_clients = []
    if db_ok:
        for idx, row in enumerate(raw_res):
            name = row.get("企业名称") or "未知企业"
            qualification = row.get("资质名称") or "优质企业"
            subsidy = float(row.get("补贴金额万元") or 0.0)
            region = row.get("客户区局") or "上海"
            manager = row.get("客户经理名称") or "客户经理"
            ind = row.get("工商行业") or "高科技行业"
            scale = row.get("集团分群二") or "中型企业"
            revenue_25 = float(row.get("企业25年收入_万元") or 0.0)
            link_url = row.get("链接") or "https://www.sheitc.sh.gov.cn/"
            
            # 信号加分：查询 zq_dtl_shnews_yyy 中是否有该企业的近期动态新闻
            news_bonus = 0.0
            news_desc = ""
            try:
                company_news = db.query_business_db(
                    "SELECT `标题` FROM zq_dtl_shnews_yyy WHERE `标题` LIKE :comp OR `内容` LIKE :comp LIMIT 1",
                    {"comp": f"%{name}%"}
                )
                if company_news:
                    news_bonus = 8.0
                    news_desc = f"且近期在上海本地新闻中检测到重大签约/合作活跃商业信号（商机匹配加分 +{news_bonus} 分）。"
            except Exception:
                pass
            
            # 计算商机匹配分
            score = 65.0
            score += min(subsidy * 0.5, 20.0)
            score += min(revenue_25 * 0.2, 10.0)
            if "专精特新" in qualification or "小巨人" in qualification:
                score += 4.5
            score += news_bonus
            score = min(round(score, 1), 99.5)
            
            # 组装推荐理由
            reason = (
                f"该企业属于{region}地区的{ind}领域，已被认定为【{qualification}】资质。累计获得财政扶持补贴资金高达 **{subsidy} 万元**，"
                f"体现出极高的政策敏感度与政府信任度。{news_desc}当前由我司经理【{manager}】负责维护。建议客户经理以政策补贴与活跃商机信号为契机，"
                f"切入云网基建与政企数字化改造产品，进一步深耕业务潜力。"
            )
            
            filtered_clients.append({
                "id": idx + 1,
                "name": name,
                "industry": ind,
                "scale": scale,
                "score": score,
                "reason": reason,
                "contact": f"{manager} (客户经理)" if manager != "客户经理" else "客户经理",
                "link": link_url
            })
    else:
        # 降级退回至模拟数据
        db.log_event(user_id, "potential", "WARNING", "高潜客户查询降级使用本地 Mock 数据。")
        clients = POTENTIAL_CLIENTS
        if keyword:
            clean_keyword = keyword.replace("行业", "").replace("客户", "").strip().lower()
            for client in clients:
                if (clean_keyword in client["name"].lower() or 
                    clean_keyword in client["industry"].lower()):
                    filtered_clients.append(client)
        if not filtered_clients:
            filtered_clients = clients

    # 3. 确定保存路径（在 static/generated/ 目录下）
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(base_dir, "static", "generated")
    ensure_dir(static_dir)
    
    excel_filename = "high_potential_clients.xlsx"
    excel_path = os.path.join(static_dir, excel_filename)
    web_url = f"/static/generated/{excel_filename}"
    
    excel_status = "success"
    try:
        # 转换为 DataFrame 准备导出
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
            
        # 导出为 Excel 文件
        df_excel.to_excel(excel_path, index=False)
        db.log_event(user_id, "potential", "INFO", f"成功生成 Excel 线索报表。保存路径: {excel_path}")
        
    except Exception as e:
        import traceback
        db.log_event(user_id, "potential", "ERROR", f"高潜线索导出 Excel 失败: {str(e)}", traceback.format_exc())
        excel_status = "failed"
        
    # 4. 返回结构化表格数据和 Excel 下载链接
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
