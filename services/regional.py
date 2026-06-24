# -*- coding: utf-8 -*-
"""
regional.py - 场景2：区级报告。生成区域商机分析卡片与明细页跳转链接。
"""

import os
from urllib.parse import quote
from sqlalchemy import text
from utils.rag_engine import RAGEngine
import utils.db_helper as db


DEFAULT_DISTRICT = "静安区"
CITY_REPORT_NAME = "上海市"

DISTRICTS = [
    "浦东新区", "黄浦区", "徐汇区", "长宁区", "静安区", "普陀区", "虹口区", "杨浦区",
    "闵行区", "宝山区", "嘉定区", "金山区", "松江区", "青浦区", "奉贤区", "崇明区"
]

REGION_ALIASES = {
    "上海徐汇": "徐汇区",
    "徐汇": "徐汇区",
    "浦东": "浦东新区",
    "临港": "浦东新区",
    "临港新片区": "浦东新区",
}

CITY_KEYWORDS = ["上海市", "全上海", "全市", "上海", "16个区", "十六个区"]


def is_city_report_keyword(keyword: str) -> bool:
    """判断用户是否请求上海市全域商机报告。"""
    text = (keyword or "").strip()
    if not text:
        return False
    has_city_scope = any(word in text for word in CITY_KEYWORDS)
    has_specific_district = any(district in text or district.replace("新区", "").replace("区", "") in text for district in DISTRICTS)
    return has_city_scope and not has_specific_district


def normalize_district(keyword: str) -> str:
    """将用户输入的区域关键词标准化为上海行政区名称；上海市/全市返回 CITY_REPORT_NAME。"""
    text = (keyword or "").strip()
    if not text:
        return DEFAULT_DISTRICT

    if is_city_report_keyword(text):
        return CITY_REPORT_NAME

    for alias, district in REGION_ALIASES.items():
        if alias in text:
            return district

    for district in DISTRICTS:
        if district in text:
            return district
        short_name = district.replace("新区", "").replace("区", "")
        if short_name and short_name in text:
            return district

    return DEFAULT_DISTRICT


def build_summary_text(region_name: str, summary: dict, is_city_report: bool = False) -> str:
    """生成区域商机摘要文案。"""
    total = summary.get("total", 0)
    hot = summary.get("hot", 0)
    watch = summary.get("watch", 0)
    top_industries = summary.get("top_industries", [])

    if total <= 0:
        if is_city_report:
            return "暂未筛选到上海市符合采集标准的商机数据，可点击明细页查看 16 个区后续更新。"
        return f"暂未筛选到{region_name}符合采集标准的公众号商机数据，可点击明细页查看后续更新。"

    industry_text = "、".join(top_industries[:3]) if top_industries else "重点产业"
    if is_city_report:
        active_districts = sum(1 for item in summary.get("district_counts", []) if item.get("count", 0) > 0)
        return f"已为您筛选上海市商机数据，共 {total} 条，覆盖 {active_districts}/16 个区，其中 HOT {hot} 条、关注 {watch} 条，重点集中在{industry_text}等方向。"
    return f"已为您筛选{region_name}商机数据，共 {total} 条，其中 HOT {hot} 条、关注 {watch} 条，重点集中在{industry_text}等方向。"


def build_city_items(summary: dict) -> list[dict]:
    """生成上海市卡片中的 16 区概览项。"""
    district_counts = summary.get("district_counts", [])
    count_map = {item.get("name"): item.get("count", 0) for item in district_counts}
    return [
        {
            "label": district,
            "value": f"{count_map.get(district, 0)} 条商机",
            "meta": "点击明细页展开查看",
        }
        for district in DISTRICTS
    ]


def _clean_text(value) -> str:
    return str(value or "").strip()


def _fetch_regional_rag_documents(region_name: str, is_city_report: bool, limit: int = 80, days_limit: int = 30) -> list[dict]:
    """从 weixin_deepseek_extract_d_new 加载区域 RAG 文档，保持与明细页一致的数据口径。"""
    documents = []
    try:
        district_param = None if is_city_report else region_name
        rows = db.fetch_weixin_extract_data(limit=limit, district=district_param, days_limit=days_limit, require_db_region=True)
        rows.sort(key=lambda x: (x.get("score") or 0, x.get("release_time_raw") or ""), reverse=True)
    except Exception as exc:
        db.log_event(None, "regional", "WARNING", f"区域 RAG 文档加载失败: {exc}")
        return documents

    import json
    from utils.alias_helper import alias_helper
    for row in rows:
        district = _clean_text(row.get("district")) or region_name
        
        # 转换为公司全称
        raw_ent_name = _clean_text(row.get("ent_name"))
        full_ent_name = alias_helper.alias_to_official.get(raw_ent_name, raw_ent_name)
        
        title = _clean_text(row.get("title")) or full_ent_name or "区域商机"
        content = "\n".join([
            f"行政区：{district}",
            f"企业：{full_ent_name}",
            f"行业：{_clean_text(row.get('industry'))}",
            f"商机等级：{_clean_text(row.get('score_label'))}",
            f"商机评分：{_clean_text(row.get('score'))}",
            f"标题：{title}",
            f"摘要：{_clean_text(row.get('abstract'))}",
            f"标签：{json.dumps(row.get('tags'), ensure_ascii=False)}",
            f"命中规则：{json.dumps(row.get('hit'), ensure_ascii=False)}",
        ])
        documents.append({
            "title": title,
            "content": content,
            "publish_date": _clean_text(row.get("release_time_raw")),
            "source": "weixin_deepseek_extract_d_new",
            "link": _clean_text(row.get("link")),
            "company": district,
            "district": district,
            "industry": _clean_text(row.get("industry")),
            "doc_type": "regional_opportunity",
            "entity_name": full_ent_name,
        })
    return documents


def _build_regional_rag_query(keyword: str, region_name: str, is_city_report: bool, summary: dict) -> str:
    scope = "上海市16区" if is_city_report else region_name
    industries = "、".join(summary.get("top_industries", [])[:5]) or "重点产业"
    return (
        f"用户问题：{keyword or scope + '商机报告'}\n"
        f"区域范围：{scope}\n"
        f"重点产业：{industries}\n"
        f"任务：检索区域商机、HOT客户、关注客户、近期动态、产业机会和客户经理可跟进方向。"
    )


def _format_regional_evidence(retrieved_docs: list[dict], limit: int = 5) -> list[dict]:
    evidence = []
    seen = set()
    for doc in retrieved_docs:
        metadata = doc.get("metadata") or {}
        key = (metadata.get("title"), metadata.get("entity_name"), metadata.get("link"))
        if key in seen:
            continue
        seen.add(key)
        evidence.append({
            "title": metadata.get("title") or "区域商机",
            "entity_name": metadata.get("entity_name") or "",
            "district": metadata.get("district") or "",
            "industry": metadata.get("industry") or "",
            "source": metadata.get("source") or "",
            "link": metadata.get("link") or "",
            "score": round(float(doc.get("rerank_score", doc.get("final_score", 0.0)) or 0.0), 4),
        })
        if len(evidence) >= limit:
            break
    return evidence


def _render_regional_rag_summary(region_name: str, summary: dict, evidence: list[dict], documents: list[dict], is_city_report: bool) -> str:
    base = build_summary_text(region_name, summary, is_city_report=is_city_report)
    if not documents:
        return base

    sorted_docs = sorted(documents, key=lambda x: str(x.get("publish_date") or ""), reverse=True)
    
    title_links_map = {}
    entities_set = set()
    
    for doc in sorted_docs:
        title = doc.get("title")
        ent = doc.get("entity_name")
        link = doc.get("link")
        
        if title:
            if title not in title_links_map and len(title_links_map) < 3:
                title_links_map[title] = link
                
            # 如果当前文档的标题在我们选中的前3个标题中，则收集其关联的企业
            if title in title_links_map:
                if ent and ent not in {"-", "无", "未知", "不适用", "NA"} and len(ent) >= 2:
                    entities_set.add(ent)

    title_links = []
    for title, link in title_links_map.items():
        if link:
            title_links.append(f"[{title}]({link})")
        else:
            title_links.append(title)
                
    titles_str = "、".join(title_links)
    entities = "、".join(list(entities_set)[:5])

    if is_city_report:
        return f"{base} 最新商机数据进一步显示，近期较值得关注的线索包括{titles_str or '多条区域动态'}，涉及{entities or '多家企业'}，建议按 HOT 等级与产业方向优先分区跟进。"
    return f"{base} 最新商机数据进一步显示，{region_name}近期较值得关注的线索包括{titles_str or '多条区域动态'}，涉及{entities or '区域重点企业'}，建议结合商机等级、行业标签和最新动态优先触达。"


def _run_regional_rag(keyword: str, region_name: str, is_city_report: bool, summary: dict, user_id: int = None, days_limit: int = 30) -> dict:
    documents = _fetch_regional_rag_documents(region_name, is_city_report, days_limit=days_limit)
    if not documents:
        return {"source_type": "mysql_structured_summary", "evidence": [], "summary": ""}

    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    query = _build_regional_rag_query(keyword, region_name, is_city_report, summary)

    try:
        rag = RAGEngine(documents=documents)
        retrieved_docs = rag.retrieve(query, top_k=8)
        if api_key and "your_api_key" not in api_key:
            retrieved_docs = rag.rerank(query, retrieved_docs, api_key, base_url, model_name)
        else:
            for doc in retrieved_docs:
                doc["rerank_score"] = doc.get("final_score", 0.0)
        evidence = _format_regional_evidence(retrieved_docs)
        summary_text = _render_regional_rag_summary(region_name, summary, evidence, documents, is_city_report)
        db.log_event(user_id, "regional", "INFO", f"区域 RAG 检索完成，证据数: {len(evidence)}")
        return {"source_type": "mysql_db_bm25_rag", "evidence": evidence, "summary": summary_text}
    except Exception as exc:
        db.log_event(user_id, "regional", "WARNING", f"区域 RAG 检索失败，降级结构化摘要: {exc}")
        return {"source_type": "mysql_structured_summary", "evidence": [], "summary": ""}


def handle(keyword: str, user_id: int = None, raw_text: str = None) -> dict:
    """
    根据关键字识别行政区，返回结构化区域商机报告卡片。
    """
    region_name = normalize_district(keyword)
    is_city_report = region_name == CITY_REPORT_NAME

    if not keyword or (region_name == DEFAULT_DISTRICT and DEFAULT_DISTRICT not in keyword):
        db.log_event(user_id, "regional", "INFO", f"未能从输入 '{keyword}' 识别明确行政区，提示用户选择。")
        return {
            "type": "text",
            "content": "请问您需要生成哪个区的区域经济报告？（例如：浦东新区、静安区、黄浦区等，或者上海市）"
        }

    import re
    def extract_days_limit(k: str) -> int:
        if not k:
            return 30
        if re.search(r'(今年|本年度|这一年)', k):
            return 365
        if re.search(r'(半年|六个月|6个月)', k):
            return 180
        if re.search(r'(三个月|3个月)', k):
            return 90
        if re.search(r'(两个月|2个月)', k):
            return 60
        if re.search(r'(一周|一星期|7天|七天)', k):
            return 7
        if re.search(r'(全部|所有时间|不限时间)', k):
            return 3650
        return 30

    days_limit = extract_days_limit(raw_text if raw_text else keyword)

    db.log_event(user_id, "regional", "INFO", f"开始生成 {region_name} 区域商机分析卡片，时间限制: {days_limit}天。")

    # 与 /api/articles 明细页保持同一数据口径：均读取 weixin_deepseek_extract_d_new 大模型挖掘结果。
    # 上海市报告不传 district，明细页默认按 16 个区折叠展示全部商机。
    summary = db.get_articles_summary(None if is_city_report else region_name, days_limit=days_limit)
    detail_url = f"/ui_1.html?days={days_limit}" if is_city_report else f"/ui_1.html?district={quote(region_name)}&days={days_limit}"
    summary_text = build_summary_text(region_name, summary, is_city_report=is_city_report)
    rag_result = _run_regional_rag(keyword, region_name, is_city_report, summary, user_id=user_id, days_limit=days_limit)
    if rag_result.get("summary"):
        summary_text = rag_result["summary"]

    result = {
        "type": "regional_report",
        "title": f"{region_name}商机报告",
        "summary": summary_text,
        "district": region_name,
        "items": build_city_items(summary) if is_city_report else [
            {
                "label": region_name,
                "value": f"{summary.get('total', 0)} 条商机",
                "meta": f"HOT {summary.get('hot', 0)} · 关注 {summary.get('watch', 0)}",
            }
        ],
        "actions": [
            {
                "label": "查看上海市16区商机明细" if is_city_report else f"查看{region_name}商机明细",
                "type": "link",
                "url": detail_url,
            }
        ],
        "metrics": summary,
        "source_type": rag_result.get("source_type", "mysql_structured_summary"),
        "evidence": rag_result.get("evidence", []),
    }

    db.log_event(user_id, "regional", "INFO", f"{region_name} 区域商机分析卡片生成完毕。")
    return result
