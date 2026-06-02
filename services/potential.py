# -*- coding: utf-8 -*-
"""
potential.py - 场景4：高潜客户线索检索。

基于 ranking_ent_dtl_clue 企业线索表与 zq_dtl_shnews_yyy 新闻信号表，
执行条件过滤、确定性评分、推荐理由生成，并提供 Excel 导出能力。
"""

import os
import re
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font
from sqlalchemy import text

import utils.db_helper as db
from utils.file_helper import ensure_dir
from utils.mock_db import POTENTIAL_CLIENTS
from utils.rag_engine import RAGEngine
import asyncio
from openai import AsyncOpenAI
import json

DISTRICT_ALIASES = {
    "浦东": "浦东新区",
    "浦东新区": "浦东新区",
    "黄浦": "黄浦区",
    "黄浦区": "黄浦区",
    "徐汇": "徐汇区",
    "徐汇区": "徐汇区",
    "长宁": "长宁区",
    "长宁区": "长宁区",
    "静安": "静安区",
    "静安区": "静安区",
    "普陀": "普陀区",
    "普陀区": "普陀区",
    "虹口": "虹口区",
    "虹口区": "虹口区",
    "杨浦": "杨浦区",
    "杨浦区": "杨浦区",
    "闵行": "闵行区",
    "闵行区": "闵行区",
    "宝山": "宝山区",
    "宝山区": "宝山区",
    "嘉定": "嘉定区",
    "嘉定区": "嘉定区",
    "金山": "金山区",
    "金山区": "金山区",
    "松江": "松江区",
    "松江区": "松江区",
    "青浦": "青浦区",
    "青浦区": "青浦区",
    "奉贤": "奉贤区",
    "奉贤区": "奉贤区",
    "崇明": "崇明区",
    "崇明区": "崇明区",
}

INDUSTRY_KEYWORDS = [
    "人工智能", "AI", "通信", "信息技术", "软件", "互联网", "数字经济", "大数据", "云计算",
    "算力", "集成电路", "半导体", "生物医药", "医疗", "智能制造", "机器人", "新能源",
    "新材料", "汽车", "金融", "文创", "航运", "低空经济", "物联网", "工业互联网",
]

NOISE_WORDS = [
    "推荐", "高潜", "潜在", "重点", "客户", "名单", "线索", "商机", "企业", "有哪些",
    "给我", "帮我", "筛选", "查询", "查看", "导出", "excel", "Excel", "表格", "一批",
]

# SIGNAL_RULES 已废弃
SIGNAL_RULES = []

DEFAULT_SCORE_MIN = 85
DEFAULT_LIMIT = 20


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _contains_any(text_value: str, keywords: Iterable[str]) -> bool:
    return any(keyword and keyword in text_value for keyword in keywords)


def _parse_number(value: Any) -> float:
    """将收入、增长率等混合文本解析为数字。收入统一近似为万元。"""
    raw = _clean_text(value)
    if not raw or raw in {"-", "--", "无", "暂无", "None", "nan"}:
        return 0.0

    normalized = raw.replace(",", "").replace("，", "").replace(" ", "")
    match = re.search(r"-?\d+(?:\.\d+)?", normalized)
    if not match:
        return 0.0

    number = float(match.group())
    if "亿" in normalized:
        number *= 10000
    return number


def _parse_percent(value: Any) -> float:
    raw = _clean_text(value).replace("%", "").replace("％", "")
    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    return float(match.group()) if match else 0.0


def parse_filters(keyword: Optional[str], score_min: int = DEFAULT_SCORE_MIN) -> Dict[str, Any]:
    text_value = _clean_text(keyword)
    district = None
    industry = None

    for alias, full_name in DISTRICT_ALIASES.items():
        if alias and alias in text_value:
            district = full_name
            break

    for ind in INDUSTRY_KEYWORDS:
        if ind and ind.lower() in text_value.lower():
            industry = "人工智能" if ind == "AI" else ind
            break

    cleaned = text_value
    for word in NOISE_WORDS:
        cleaned = cleaned.replace(word, " ")
    if district:
        cleaned = cleaned.replace(district, " ").replace(district.replace("新区", "").replace("区", ""), " ")
    if industry:
        cleaned = cleaned.replace(industry, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return {
        "district": district,
        "industry": industry,
        "keyword": cleaned or None,
        "score_min": score_min,
    }


def _build_like_filter(field_exprs: List[str], param_name: str) -> str:
    return "(" + " OR ".join([f"{field} LIKE :{param_name}" for field in field_exprs]) + ")"


def fetch_candidate_enterprises(filters: Dict[str, Any], limit: int = 300) -> List[Dict[str, Any]]:
    where_parts = [
        "`企业名称` IS NOT NULL",
        "`企业名称` != ''",
        "(`榜单废弃` IS NULL OR `榜单废弃` = '' OR `榜单废弃` = '否')",
        "(`资质名称` IS NULL OR `资质名称` NOT LIKE '%榜单废弃%')",
    ]
    params: Dict[str, Any] = {"limit": limit}

    district = filters.get("district")
    if district:
        district_short = district.replace("新区", "").replace("区", "")
        where_parts.append("(" + " OR ".join([
            "`客户区局` LIKE :district_full",
            "`客户区局` LIKE :district_short",
            "`客户经理所属部门` LIKE :district_full",
            "`客户经理所属部门` LIKE :district_short",
            "`省份` LIKE :district_full",
            "`省份` LIKE :district_short",
            "`城市` LIKE :district_full",
            "`城市` LIKE :district_short",
            "`备注` LIKE :district_full",
            "`备注` LIKE :district_short",
        ]) + ")")
        params["district_full"] = f"%{district}%"
        params["district_short"] = f"%{district_short}%"

    industry = filters.get("industry")
    if industry:
        where_parts.append(_build_like_filter(["`工商行业`", "`归属行业`", "`根营销行业一层`", "`集团行业一层`", "`资质名称`", "`企业名称`"], "industry"))
        params["industry"] = f"%{industry}%"

    keyword = filters.get("keyword")
    if keyword:
        where_parts.append(_build_like_filter(["`企业名称`", "`企业简称`", "`客户名称`", "`工商行业`", "`归属行业`", "`资质名称`", "`榜单名称`"], "keyword"))
        params["keyword"] = f"%{keyword}%"

    sql = text(f"""
        SELECT
            c.`企业名称` AS name,
            c.`企业简称` AS short_name,
            c.`客户名称` AS customer_name,
            c.`客户区局` AS region,
            c.`省份` AS province,
            c.`城市` AS city,
            c.`工商行业` AS industry,
            c.`归属行业` AS industry_alt,
            c.`根营销行业一层` AS marketing_industry_l1,
            c.`集团行业一层` AS group_industry_l1,
            c.`榜单名称` AS ranking_name,
            c.`榜单类型` AS ranking_type,
            c.`资质名称` AS qualification,
            c.`2024年营业收入（万元）` AS revenue_2024,
            c.`企业25年收入_万元` AS revenue_2025,
            c.`营业收入增长率` AS growth_rate,
            c.`补贴金额万元` AS subsidy_amount,
            c.`补贴金额规则` AS subsidy_rule,
            c.`客户经理名称` AS account_manager,
            c.`客户经理所属部门` AS account_manager_department,
            c.`链接` AS ranking_link,
            c.`是否入选新希望客户` AS is_new_hope_customer,
            c.`企业注册时间` AS registered_at,
            o.`score` AS regional_score,
            o.`matched_rules` AS signals_json,
            o.`title` AS latest_title,
            o.`release_time` AS latest_date,
            o.`link` AS latest_link
        FROM ranking_ent_dtl_clue c
        LEFT JOIN (
            SELECT ent_name, MAX(score) AS score, MAX(matched_rules) AS matched_rules,
                   MAX(title) AS title, MAX(release_time) AS release_time, MAX(link) AS link
            FROM opportunity_articles
            GROUP BY ent_name
        ) o ON c.`企业名称` = o.`ent_name`
        WHERE {' AND '.join(where_parts)}
        ORDER BY IFNULL(o.score, 0) DESC
        LIMIT :limit
    """)

    with db.engine.connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).mappings().all()]


def fetch_enterprise_signals(candidates: List[Dict[str, Any]], max_candidates: int = 100) -> Dict[str, Dict[str, Any]]:
    return {}



def score_enterprise(row: Dict[str, Any]) -> Tuple[int, List[str], Dict[str, int]]:
    import json
    score_parts: Dict[str, int] = {}
    tags: List[str] = []

    regional_score = int(row.get("regional_score") or 0)
    score_parts["Regional基础分"] = regional_score

    signals_json = row.get("signals_json")
    if signals_json:
        try:
            signal_tags = json.loads(signals_json)
            if isinstance(signal_tags, list):
                tags.extend(signal_tags)
        except:
            pass

    return regional_score, list(dict.fromkeys(tags)), score_parts


def build_reason(row: Dict[str, Any], tags: List[str]) -> str:
    tag_text = "、".join(tags[:4]) if tags else "优质企业"
    latest_title = _clean_text(row.get("latest_title"))
    if latest_title:
        return f"企业具备{tag_text}等特征，近期动态“{latest_title}”显示其业务扩张或投入意愿较强，适合优先跟进。"
    return f"企业具备{tag_text}等特征，符合高潜客户筛选标准，建议纳入重点客户池持续跟进。"


def build_next_action(row: Dict[str, Any], tags: List[str]) -> str:
    industry = " ".join([
        _clean_text(row.get("industry")),
        _clean_text(row.get("industry_alt")),
        _clean_text(row.get("marketing_industry_l1")),
        _clean_text(row.get("group_industry_l1")),
    ])
    if _contains_any(industry + " ".join(tags), ["人工智能", "算力", "大数据", "云计算", "软件", "信息技术"]):
        return "建议客户经理优先跟进云资源、专线、算力和数据服务需求。"
    if _contains_any(industry + " ".join(tags), ["智能制造", "机器人", "汽车", "新能源", "新材料", "半导体", "集成电路"]):
        return "建议优先跟进工业互联网、园区专线、边缘计算和 ICT 集成需求。"
    return "建议客户经理开展首次触达，确认专线、云资源、ICT 集成和政策申报需求。"


def _build_enterprise_rag_document(row: Dict[str, Any]) -> Dict[str, Any]:
    name = _clean_text(row.get("name"))
    region = _clean_text(row.get("region")) or _clean_text(row.get("city")) or _clean_text(row.get("province"))
    industry = (
        _clean_text(row.get("industry"))
        or _clean_text(row.get("industry_alt"))
        or _clean_text(row.get("marketing_industry_l1"))
        or _clean_text(row.get("group_industry_l1"))
    )
    import json
    try:
        signals = json.loads(row.get("signals_json") or "[]")
    except:
        signals = []
    content = "\\n".join([
        f"企业名称：{name}",
        f"企业简称：{_clean_text(row.get('short_name'))}",
        f"行政区：{region}",
        f"行业：{industry}",
        f"榜单资质：{_clean_text(row.get('qualification'))}",
        f"榜单名称：{_clean_text(row.get('ranking_name'))}",
        f"榜单类型：{_clean_text(row.get('ranking_type'))}",
        f"2024年营业收入：{_clean_text(row.get('revenue_2024'))}",
        f"2025年收入：{_clean_text(row.get('revenue_2025'))}",
        f"营业收入增长率：{_clean_text(row.get('growth_rate'))}",
        f"补贴金额：{_clean_text(row.get('subsidy_amount'))}",
        f"补贴规则：{_clean_text(row.get('subsidy_rule'))}",
        f"是否入选新希望客户：{_clean_text(row.get('is_new_hope_customer'))}",
        f"客户经理：{_clean_text(row.get('account_manager'))}",
        f"近期新闻信号：{'、'.join(signals)}",
        f"最新动态标题：{_clean_text(row.get('latest_title'))}",
    ])
    return {
        "title": name or "高潜候选企业",
        "content": content,
        "publish_date": _clean_text(row.get("latest_date")) or _clean_text(row.get("registered_at")) or datetime.now().strftime("%Y-%m-%d"),
        "source": "ranking_ent_dtl_clue",
        "link": _clean_text(row.get("latest_link")) or _clean_text(row.get("ranking_link")),
        "company": name,
        "district": region,
        "industry": industry,
        "doc_type": "enterprise_profile",
    }


def _build_news_rag_documents(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    documents = []
    for row in candidates[:100]:
        name = _clean_text(row.get("name"))
        latest_title = _clean_text(row.get("latest_title"))
        if not name or not latest_title:
            continue
        try:
            import json
            signals = json.loads(row.get("signals_json") or "[]")
        except:
            signals = []
        content = "\\n".join([
            f"企业名称：{name}",
            f"新闻标题：{latest_title}",
            f"命中信号：{'、'.join(signals)}",
            f"新闻信号得分：{_clean_text(row.get('regional_score'))}",
        ])
        documents.append({
            "title": latest_title,
            "content": content,
            "publish_date": _clean_text(row.get("latest_date")),
            "source": "opportunity_articles",
            "link": _clean_text(row.get("latest_link")),
            "company": name,
            "district": _clean_text(row.get("region")) or _clean_text(row.get("city")) or _clean_text(row.get("province")),
            "industry": _clean_text(row.get("industry")) or _clean_text(row.get("industry_alt")),
            "doc_type": "news_signal",
        })
    return documents


def _fetch_policy_rag_documents(filters: Dict[str, Any], limit: int = 12) -> List[Dict[str, Any]]:
    keywords = [filters.get("industry"), filters.get("district"), filters.get("keyword")]
    keywords = [item for item in keywords if item]
    if not keywords:
        return []

    params = {f"kw{idx}": f"%{kw}%" for idx, kw in enumerate(keywords)}
    like_parts = []
    for idx in range(len(keywords)):
        like_parts.append(f"`标题` LIKE :kw{idx} OR `正文` LIKE :kw{idx} OR `关键词` LIKE :kw{idx}")
    sql = text(f"""
        SELECT `标题` AS title, `正文` AS content, `网址` AS link, `发布单位` AS source, `发布时间` AS publish_date
        FROM zq_dtl_onenet_all
        WHERE {' OR '.join(like_parts)}
        ORDER BY `发布时间` DESC
        LIMIT {int(limit)}
    """)

    try:
        rows = db.query_business_db(str(sql), params)
    except Exception:
        return []

    documents = []
    for row in rows:
        documents.append({
            "title": row.get("title") or "政策信号",
            "content": row.get("content") or "",
            "publish_date": row.get("publish_date") or "",
            "source": row.get("source") or "政策库",
            "link": row.get("link") or "",
            "company": "policy",
            "district": filters.get("district") or "",
            "industry": filters.get("industry") or "",
            "doc_type": "policy_signal",
        })
    return documents


def _build_potential_rag_query(filters: Dict[str, Any]) -> str:
    return "\n".join([
        f"区域：{filters.get('district') or '不限'}",
        f"行业：{filters.get('industry') or '不限'}",
        f"关键词：{filters.get('keyword') or '高潜客户'}",
        "任务：筛选高潜客户，关注收入增长、榜单资质、政策补贴、融资上市、重大签约、扩产落地、技术突破、政府关注和数字化业务需求。",
    ])


def _aggregate_rag_by_company(retrieved_docs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for doc in retrieved_docs:
        metadata = doc.get("metadata") or {}
        company = metadata.get("company") or ""
        if not company or company == "policy":
            continue
        score = float(doc.get("rerank_score", doc.get("final_score", 0.0)) or 0.0)
        item = result.setdefault(company, {"best_score": 0.0, "evidence": []})
        item["best_score"] = max(item["best_score"], score)
        if len(item["evidence"]) < 3:
            item["evidence"].append({
                "title": metadata.get("title") or "RAG证据",
                "source": metadata.get("source") or "",
                "link": metadata.get("link") or "",
                "doc_type": metadata.get("doc_type") or "",
                "score": round(score, 4),
            })
    return result


def _rag_bonus(score: float) -> int:
    if score >= 0.85:
        return 10
    if score >= 0.70:
        return 7
    if score >= 0.55:
        return 5
    if score >= 0.40:
        return 2
    return 0


def _run_potential_rag(filters: Dict[str, Any], candidates: List[Dict[str, Any]], user_id: int = None) -> Dict[str, Dict[str, Any]]:
    documents = []
    for row in candidates[:300]:
        name = _clean_text(row.get("name"))
        if name:
            documents.append(_build_enterprise_rag_document(row))
    documents.extend(_build_news_rag_documents(candidates))
    documents.extend(_fetch_policy_rag_documents(filters))

    if not documents:
        return {}

    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    query = _build_potential_rag_query(filters)

    try:
        rag = RAGEngine(documents=documents)
        retrieved_docs = rag.retrieve(query, top_k=40)
        if api_key and "your_api_key" not in api_key:
            retrieved_docs = rag.rerank(query, retrieved_docs, api_key, base_url, model_name)
        else:
            for doc in retrieved_docs:
                doc["rerank_score"] = doc.get("final_score", 0.0)
        company_rag = _aggregate_rag_by_company(retrieved_docs)
        db.log_event(user_id, "potential", "INFO", f"高潜客户 RAG 检索完成，命中企业数: {len(company_rag)}")
        return company_rag
    except Exception as exc:
        db.log_event(user_id, "potential", "WARNING", f"高潜客户 RAG 检索失败，降级规则评分: {exc}")
        return {}

    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    query = _build_potential_rag_query(filters)

    try:
        rag = RAGEngine(documents=documents)
        retrieved_docs = rag.retrieve(query, top_k=40)
        if api_key and "your_api_key" not in api_key:
            retrieved_docs = rag.rerank(query, retrieved_docs, api_key, base_url, model_name)
        else:
            for doc in retrieved_docs:
                doc["rerank_score"] = doc.get("final_score", 0.0)
        company_rag = _aggregate_rag_by_company(retrieved_docs)
        db.log_event(user_id, "potential", "INFO", f"高潜客户 RAG 检索完成，命中企业数: {len(company_rag)}")
        return company_rag
    except Exception as exc:
        db.log_event(user_id, "potential", "WARNING", f"高潜客户 RAG 检索失败，降级规则评分: {exc}")
        return {}


def _apply_rag_to_candidate(item: Dict[str, Any], rag_info: Dict[str, Any]) -> Dict[str, Any]:
    regional_score = item.get("score", 0)
    
    if not rag_info:
        item["rag_score"] = 0.0
        item["rag_evidence"] = []
        final_score = int(regional_score * 0.8)
        item["score"] = final_score
        item["level"] = "HOT" if final_score >= 85 else "关注"
        return item

    score = float(rag_info.get("best_score") or 0.0)
    evidence = rag_info.get("evidence") or []
    item["rag_score"] = round(score, 4)
    item["rag_evidence"] = evidence
    
    rag_scaled = int(score * 100)
    final_score = int(regional_score * 0.8 + rag_scaled * 0.2)
    item["score"] = min(100, final_score)
    item["level"] = "HOT" if item["score"] >= 85 else "关注"
    
    if final_score > int(regional_score * 0.8):
        item.setdefault("score_parts", {})["RAG加权分"] = int(rag_scaled * 0.2)
        signals = item.setdefault("signals", [])
        if "RAG强相关证据" not in signals:
            signals.append("RAG强相关证据")
        if evidence:
            title = evidence[0].get("title") or "相关证据"
            item["reason"] = f"{item.get('reason', '')} RAG 证据“{title}”进一步证明其与当前筛选目标相关，建议优先核实业务需求。"
    return item

    score = float(rag_info.get("best_score") or 0.0)
    bonus = _rag_bonus(score)
    evidence = rag_info.get("evidence") or []
    item["rag_score"] = round(score, 4)
    item["rag_evidence"] = evidence
    if bonus:
        item["score"] = min(100, int(item.get("score") or 0) + bonus)
        item["level"] = "HOT" if item["score"] >= 80 else "关注"
        item.setdefault("score_parts", {})["RAG证据"] = bonus
        signals = item.setdefault("signals", [])
        if "RAG强相关证据" not in signals:
            signals.append("RAG强相关证据")
        if evidence:
            title = evidence[0].get("title") or "相关证据"
            item["reason"] = f"{item.get('reason', '')} RAG 证据“{title}”进一步证明其与当前筛选目标相关，建议优先核实业务需求。"
    return item


def _normalize_candidate(row: Dict[str, Any], score: int, tags: List[str], score_parts: Dict[str, int]) -> Dict[str, Any]:
    region = _clean_text(row.get("region")) or _clean_text(row.get("city")) or _clean_text(row.get("province"))
    industry = (
        _clean_text(row.get("industry"))
        or _clean_text(row.get("industry_alt"))
        or _clean_text(row.get("marketing_industry_l1"))
        or _clean_text(row.get("group_industry_l1"))
        or "未标注"
    )
    level = "HOT" if score >= 85 else "关注"
    return {
        "name": _clean_text(row.get("name")),
        "short_name": _clean_text(row.get("short_name")),
        "score": score,
        "level": level,
        "industry": industry,
        "region": region or "未标注",
        "signals": tags[:6],
        "reason": build_reason(row, tags),
        "next_action": build_next_action(row, tags),
        "account_manager": _clean_text(row.get("account_manager")) or "待分配",
        "qualification": _clean_text(row.get("qualification")),
        "revenue_2024": _clean_text(row.get("revenue_2024")),
        "growth_rate": _clean_text(row.get("growth_rate")),
        "subsidy_amount": _clean_text(row.get("subsidy_amount")),
        "subsidy_rule": _clean_text(row.get("subsidy_rule")),
        "ranking_name": _clean_text(row.get("ranking_name")),
        "ranking_type": _clean_text(row.get("ranking_type")),
        "ranking_link": _clean_text(row.get("ranking_link")),
        "is_new_hope_customer": _clean_text(row.get("is_new_hope_customer")),
        "latest_title": _clean_text(row.get("latest_title")),
        "latest_date": _clean_text(row.get("latest_date")),
        "link": _clean_text(row.get("latest_link")),
        "score_parts": score_parts,
    }


def _fallback_from_mock(filters: Dict[str, Any], limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    keyword = filters.get("keyword") or filters.get("industry") or ""
    items = []
    for client in POTENTIAL_CLIENTS:
        if keyword and keyword.lower() not in (client.get("name", "") + client.get("industry", "")).lower():
            continue
        score = int(client.get("score") or 0)
        items.append({
            "name": client.get("name"),
            "short_name": "",
            "score": score,
            "level": "HOT" if score >= 80 else "关注",
            "industry": client.get("industry"),
            "region": filters.get("district") or "未标注",
            "signals": ["Mock兜底", "优质线索"],
            "reason": client.get("reason"),
            "next_action": "建议客户经理优先确认专线、云资源和 ICT 集成需求。",
            "account_manager": client.get("contact", "待分配"),
            "qualification": "",
            "revenue_2024": client.get("scale", ""),
            "growth_rate": "",
            "subsidy_rule": "",
            "latest_title": "",
            "latest_date": "",
            "link": client.get("link", ""),
            "score_parts": {},
        })
    return items[:limit] or []


def get_recommendations(filters: Dict[str, Any], limit: int = DEFAULT_LIMIT, skip_rag: bool = False) -> List[Dict[str, Any]]:
    try:
        candidates = fetch_candidate_enterprises(filters)
        company_rag = {} if skip_rag else _run_potential_rag(filters, candidates)
        recommendations = []
        ranked_all = []
        score_min = int(filters.get("score_min") or DEFAULT_SCORE_MIN)
        seen_names = set()

        for row in candidates:
            name = _clean_text(row.get("name"))
            if not name or name in seen_names:
                continue
            
            if not _clean_text(row.get("latest_link")):
                continue

            seen_names.add(name)
            score, tags, score_parts = score_enterprise(row)
            normalized = _normalize_candidate(row, score, tags, score_parts)
            normalized = _apply_rag_to_candidate(normalized, company_rag.get(name, {}))
            ranked_all.append(normalized)
            if int(normalized.get("score") or 0) >= score_min:
                recommendations.append(normalized)

        if skip_rag:
            ranked_all.sort(key=lambda item: (item["score"], item.get("rag_score", 0.0)), reverse=True)
            return ranked_all[:limit]

        recommendations.sort(key=lambda item: (item["score"], item.get("rag_score", 0.0)), reverse=True)
        if recommendations:
            return recommendations[:limit]

        # 行政区类查询如果没有超过阈值的企业，不直接返回空；保底返回该区域综合得分最高的若干企业。
        ranked_all.sort(key=lambda item: (item["score"], item.get("rag_score", 0.0)), reverse=True)
        if ranked_all and (filters.get("district") or filters.get("industry") or filters.get("keyword")):
            return ranked_all[: min(limit, 10)]
        return []
    except Exception as exc:
        import traceback
        import utils.db_helper as db
        db.log_event(None, "potential", "ERROR", f"高潜客户数据库检索失败，启用兜底数据: {exc}", traceback.format_exc())
        return _fallback_from_mock(filters, limit=limit)



def write_items_to_excel(items: List[Dict[str, Any]], safe_scope: str) -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(base_dir, "static", "generated")
    ensure_dir(static_dir)

    safe_scope = re.sub(r"[\\/:*?\"<>|\s]+", "_", safe_scope)[:30]
    filename = f"high_potential_{safe_scope}_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}.xlsx"
    excel_path = os.path.join(static_dir, filename)

    if items:
        df = pd.DataFrame(items)
        df_excel = df.rename(columns={
            "name": "企业名称",
            "short_name": "企业简称",
            "region": "行政区",
            "industry": "行业",
            "score": "推荐评分",
            "level": "推荐等级",
            "signals": "命中信号",
            "reason": "推荐理由",
            "next_action": "下一步动作",
            "account_manager": "客户经理",
            "qualification": "资质名称",
            "ranking_name": "榜单名称",
            "ranking_type": "榜单类型",
            "revenue_2024": "2024年营业收入（万元）",
            "growth_rate": "营业收入增长率",
            "subsidy_amount": "补贴金额万元",
            "subsidy_rule": "补贴金额规则",
            "is_new_hope_customer": "是否入选新希望客户",
            "latest_title": "最新动态标题",
            "latest_date": "最新动态日期",
            "link": "新闻原文链接",
            "ranking_link": "榜单原文链接",
        })
        if "命中信号" in df_excel.columns:
            df_excel["命中信号"] = df_excel["命中信号"].apply(lambda value: "、".join(value) if isinstance(value, list) else value)
        keep_columns = [
            "企业名称", "企业简称", "行政区", "行业", "推荐评分", "推荐等级", "命中信号", "推荐理由",
            "下一步动作", "客户经理", "资质名称", "榜单名称", "榜单类型", "2024年营业收入（万元）",
            "营业收入增长率", "补贴金额万元", "补贴金额规则", "是否入选新希望客户",
            "最新动态标题", "最新动态日期", "新闻原文链接", "榜单原文链接",
        ]
        df_excel = df_excel[[column for column in keep_columns if column in df_excel.columns]]
    else:
        df_excel = pd.DataFrame([{"提示": "暂无符合条件的高潜客户"}])

    df_excel.to_excel(excel_path, index=False)
    _apply_excel_hyperlinks(excel_path, ["新闻原文链接", "榜单原文链接"])
    return excel_path


def _build_export_url(filters: Dict[str, Any]) -> str:
    params = {"score_min": filters.get("score_min") or DEFAULT_SCORE_MIN}
    if filters.get("district"):
        params["district"] = filters["district"]
    if filters.get("industry"):
        params["industry"] = filters["industry"]
    if filters.get("keyword"):
        params["keyword"] = filters["keyword"]
    return "/api/potential/export?" + urlencode(params)


def handle(keyword: str, user_id: int = None) -> dict:
    if not keyword:
        return {
            "type": "text",
            "content": "请问您想挖掘哪个行政区或哪个行业的高潜客户？（例如：浦东新区、人工智能行业等）"
        }
    filters = parse_filters(keyword)
    db.log_event(user_id, "potential", "INFO", f"开始检索高潜客户线索。过滤条件: {filters}")

    items = get_recommendations(filters)
    
    if items:
        try:
            items = asyncio.run(_async_generate_all_reasons(items))
        except Exception as e:
            db.log_event(user_id, "potential", "WARNING", f"大模型润色推荐理由失败: {e}")
            
    district_label = filters.get("district") or "全市"
    industry_label = filters.get("industry")
    title_parts = [district_label]
    if industry_label:
        title_parts.append(industry_label)
    title = "".join(title_parts) + "高潜客户推荐"

    if items:
        strong_count = sum(1 for item in items if int(item.get("score") or 0) >= int(filters.get("score_min") or DEFAULT_SCORE_MIN))
        if strong_count:
            summary = f"已为您筛选出 {len(items)} 家{district_label if district_label != '全市' else ''}高潜客户，排序综合考虑企业资质、收入增长、政策补贴和近期新闻信号。"
        else:
            summary = f"暂未发现评分超过 {filters.get('score_min')} 分的严格高潜客户，已为您返回{district_label if district_label != '全市' else ''}综合得分靠前的候选企业供参考。"
    else:
        summary = "暂未筛选到符合条件的高潜客户，建议放宽区域、行业或评分条件后重试。"

    actions = []
    if items:
        safe_scope = filters.get("district") or filters.get("industry") or filters.get("keyword") or "全市"
        import os
        excel_path = write_items_to_excel(items, safe_scope)
        excel_url = f"/static/generated/{os.path.basename(excel_path)}"
        
        actions.append({
            "label": "导出高潜客户 Excel",
            "type": "download",
            "url": excel_url,
        })

    payload = {
        "type": "high_potential_customers",
        "title": title,
        "summary": summary,
        "filters": filters,
        "items": items,
        "actions": actions,
        "count": len(items),
    }
    db.log_event(user_id, "potential", "INFO", f"高潜客户推荐生成完成，数量: {len(items)}")
    return payload


def _apply_excel_hyperlinks(excel_path: str, link_columns: List[str]) -> None:
    """将指定列中的 URL 文本转换为 Excel 可点击超链接。"""
    try:
        workbook = load_workbook(excel_path)
        sheet = workbook.active
        header_map = {
            str(cell.value or "").strip(): idx
            for idx, cell in enumerate(sheet[1], start=1)
        }
        for column_name in link_columns:
            column_idx = header_map.get(column_name)
            if not column_idx:
                continue
            for row_idx in range(2, sheet.max_row + 1):
                cell = sheet.cell(row=row_idx, column=column_idx)
                url = _clean_text(cell.value)
                if not (url.startswith("http://") or url.startswith("https://")):
                    continue
                cell.hyperlink = url
                cell.value = "查看原文"
                cell.style = "Hyperlink"
                cell.font = Font(color="0563C1", underline="single")
        workbook.save(excel_path)
    except Exception as exc:
        db.log_event(None, "potential", "WARNING", f"Excel 超链接格式化失败，保留原始 URL 文本: {exc}")


def export_excel(
    district: Optional[str] = None,
    industry: Optional[str] = None,
    keyword: Optional[str] = None,
    score_min: int = DEFAULT_SCORE_MIN,
    user_id: Optional[int] = None,
) -> str:
    filter_text = " ".join([value for value in [district, industry, keyword] if value])
    filters = parse_filters(filter_text, score_min=score_min)
    if district:
        filters["district"] = district
    if industry:
        filters["industry"] = industry
    if keyword:
        filters["keyword"] = keyword
    filters["score_min"] = score_min

    items = get_recommendations(filters, limit=500, skip_rag=True)

    safe_scope = district or industry or keyword or "全市"
    excel_path = write_items_to_excel(items, safe_scope)
    db.log_event(user_id, "potential", "INFO", f"高潜客户 Excel 导出成功: {excel_path}")
    return excel_path


async def _async_generate_reason(item: dict) -> dict:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    if not api_key or "your_api_key" in api_key:
        return item
        
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    
    rag_evidences = [e.get("title") for e in item.get("rag_evidence", [])]
    
    prompt = f"""
请作为顶级的大客户经理和售前架构师，为高潜企业“{item.get('name')}”撰写一段个性化的推荐理由和下一步行动建议。
【已知企业信息】：
行业：{item.get('industry', '未知')}
已知资质：{item.get('qualification', '无')}
收入增速：{item.get('growth_rate', '未知')}
命中信号标签：{','.join(item.get('signals', []))}
最新动态标题：{item.get('latest_title', '无')}
RAG补充证据：{rag_evidences}

【撰写要求】：
1. 根据上述信息，分析该企业的近期动态或资质意味着怎样的业务扩张、数字化转型等潜在需求。
2. 推荐理由（reason）：一到两句精炼的分析，说明为什么值得优先跟进。必须彻底摆脱模板化套话，要深度结合企业的具体行业和具体动态来写，例如“该企业近期完成了A轮融资，且具备专精特新资质，表明其研发投入将加大，可能有云算力扩容需求。”
3. 下一步动作（next_action）：结合行业给出下一步业务拓展建议（例如专线、云资源、5G专网、ICT集成或政策申报），一句话概括。如果新闻提到新办公楼，建议写“跟进园区专线建设”等。
4. 严格以 JSON 格式返回，包含 'reason' 和 'next_action' 两个字符串字段，不要有 ```json 标记。
"""
    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "你是一个顶级售前架构师，擅长用最敏锐的商业视角深度剖析企业新闻与资质背后的商机。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            timeout=15.0
        )
        res = json.loads(response.choices[0].message.content)
        if "reason" in res and res["reason"]:
            item["reason"] = res["reason"]
        if "next_action" in res and res["next_action"]:
            item["next_action"] = res["next_action"]
    except Exception as e:
        print(f"Generate reason error for {item.get('name')}: {e}")
    return item

async def _async_generate_all_reasons(items: list) -> list:
    tasks = [_async_generate_reason(item) for item in items[:10]] # 只润色前10个，避免过载
    await asyncio.gather(*tasks)
    return items

