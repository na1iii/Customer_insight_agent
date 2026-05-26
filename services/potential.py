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

SIGNAL_RULES = [
    ("融资上市", 8, ["融资", "战略投资", "增资", "IPO", "上市", "挂牌", "科创板", "港交所", "北交所"]),
    ("重大签约", 7, ["签约", "战略合作", "合作协议", "签约仪式", "达成合作"]),
    ("扩产落地", 6, ["扩产", "投产", "开工", "落地", "入驻", "设立总部", "总部落地", "新设", "成立"]),
    ("技术突破", 5, ["技术突破", "首发", "首创", "研发", "获奖", "认证", "专精特新", "高新技术企业", "创新成果"]),
    ("政府关注", 4, ["调研", "走访", "考察", "座谈", "书记", "区长", "主任", "领导"]),
]

DEFAULT_SCORE_MIN = 55
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
            `企业名称` AS name,
            `企业简称` AS short_name,
            `客户名称` AS customer_name,
            `客户区局` AS region,
            `省份` AS province,
            `城市` AS city,
            `工商行业` AS industry,
            `归属行业` AS industry_alt,
            `根营销行业一层` AS marketing_industry_l1,
            `集团行业一层` AS group_industry_l1,
            `榜单名称` AS ranking_name,
            `榜单类型` AS ranking_type,
            `资质名称` AS qualification,
            `2024年营业收入（万元）` AS revenue_2024,
            `企业25年收入_万元` AS revenue_2025,
            `营业收入增长率` AS growth_rate,
            `补贴金额万元` AS subsidy_amount,
            `补贴金额规则` AS subsidy_rule,
            `客户经理名称` AS account_manager,
            `客户经理所属部门` AS account_manager_department,
            `链接` AS ranking_link,
            `是否入选新希望客户` AS is_new_hope_customer,
            `企业注册时间` AS registered_at
        FROM ranking_ent_dtl_clue
        WHERE {' AND '.join(where_parts)}
        LIMIT :limit
    """)

    with db.engine.connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).mappings().all()]


def fetch_enterprise_signals(candidates: List[Dict[str, Any]], max_candidates: int = 100) -> Dict[str, Dict[str, Any]]:
    signals: Dict[str, Dict[str, Any]] = {}
    searchable = []
    for row in candidates[:max_candidates]:
        name = _clean_text(row.get("name"))
        short_name = _clean_text(row.get("short_name"))
        if name:
            searchable.append((name, short_name))
            signals[name] = {"signals": [], "score": 0, "latest_title": "", "latest_date": "", "link": ""}

    if not searchable:
        return signals

    sql = text("""
        SELECT
            `标题` AS title,
            `内容` AS content,
            `发布日期` AS release_time,
            `URL` AS link
        FROM zq_dtl_shnews_yyy
        WHERE `标题` IS NOT NULL AND `标题` != ''
        ORDER BY `发布日期` DESC
        LIMIT 800
    """)

    with db.engine.connect() as conn:
        news_rows = [dict(row) for row in conn.execute(sql).mappings().all()]

    for ent_name, short_name in searchable:
        signal_names: List[str] = []
        signal_score = 0
        latest_title = ""
        latest_date = ""
        latest_link = ""

        match_terms = [ent_name]
        if short_name and short_name not in match_terms:
            match_terms.append(short_name)

        for news in news_rows:
            title = _clean_text(news.get("title"))
            content = _clean_text(news.get("content"))
            text_all = title + content[:1200]
            if not any(term and term in text_all for term in match_terms):
                continue

            if not latest_title:
                latest_title = title
                latest_date = _clean_text(news.get("release_time"))
                latest_link = _clean_text(news.get("link"))

            for signal_name, points, keywords in SIGNAL_RULES:
                if signal_name not in signal_names and _contains_any(text_all, keywords):
                    signal_names.append(signal_name)
                    signal_score += points

            if len(signal_names) >= 4:
                break

        signals[ent_name] = {
            "signals": signal_names,
            "score": min(signal_score, 25),
            "latest_title": latest_title,
            "latest_date": latest_date,
            "link": latest_link,
        }

    return signals


def score_enterprise(row: Dict[str, Any], signal: Optional[Dict[str, Any]] = None) -> Tuple[int, List[str], Dict[str, int]]:
    signal = signal or {}
    score_parts: Dict[str, int] = {}
    tags: List[str] = []

    revenue = _parse_number(row.get("revenue_2024"))
    if revenue >= 100000:
        revenue_score = 20
    elif revenue >= 10000:
        revenue_score = 16
    elif revenue >= 5000:
        revenue_score = 12
    elif revenue > 0:
        revenue_score = 8
    else:
        revenue_score = 0
    if revenue_score:
        tags.append("高收入规模" if revenue_score >= 16 else "收入可观")
    score_parts["收入规模"] = revenue_score

    growth = _parse_percent(row.get("growth_rate"))
    if growth >= 50:
        growth_score = 20
    elif growth >= 30:
        growth_score = 16
    elif growth >= 15:
        growth_score = 12
    elif growth > 0:
        growth_score = 8
    else:
        growth_score = 0
    if growth_score:
        tags.append("增长较快" if growth_score >= 12 else "正增长")
    score_parts["增长表现"] = growth_score

    qualification = " ".join([
        _clean_text(row.get("qualification")),
        _clean_text(row.get("ranking_name")),
        _clean_text(row.get("ranking_type")),
    ])
    if _contains_any(qualification, ["专精特新", "小巨人", "独角兽", "瞪羚"]):
        qual_score = 20
    elif _contains_any(qualification, ["高新技术", "重点企业", "百强", "上市"]):
        qual_score = 16
    elif _contains_any(qualification, ["创新型", "科技型", "示范", "试点"]):
        qual_score = 12
    elif qualification:
        qual_score = 8
    else:
        qual_score = 0
    if qual_score:
        tags.append("优质资质")
    score_parts["榜单资质"] = qual_score

    subsidy_rule = _clean_text(row.get("subsidy_rule"))
    subsidy_amount = _parse_number(row.get("subsidy_amount"))
    if subsidy_amount > 0 or _contains_any(subsidy_rule, ["万元", "亿元", "奖励", "补贴", "扶持"]):
        subsidy_score = 10
    elif subsidy_rule:
        subsidy_score = 6
    else:
        subsidy_score = 0
    if subsidy_score:
        tags.append("政策补贴匹配")
    score_parts["政策补贴"] = subsidy_score

    signal_score = int(signal.get("score") or 0)
    signal_tags = signal.get("signals") or []
    tags.extend(signal_tags)
    score_parts["新闻信号"] = signal_score

    completeness = 0
    if _clean_text(row.get("account_manager")):
        completeness += 2
    if _clean_text(row.get("industry")) or _clean_text(row.get("industry_alt")) or _clean_text(row.get("marketing_industry_l1")):
        completeness += 1
    if _clean_text(row.get("region")) or _clean_text(row.get("city")) or _clean_text(row.get("province")):
        completeness += 1
    if _clean_text(row.get("short_name")):
        completeness += 1
    score_parts["可跟进性"] = completeness

    total = min(sum(score_parts.values()), 100)
    return total, list(dict.fromkeys(tags)), score_parts


def build_reason(row: Dict[str, Any], tags: List[str], signal: Optional[Dict[str, Any]]) -> str:
    signal = signal or {}
    tag_text = "、".join(tags[:4]) if tags else "基础企业信息完整"
    latest_title = _clean_text(signal.get("latest_title"))
    if latest_title:
        return f"企业具备{tag_text}等特征，近期动态“{latest_title}”显示其业务扩张或数字化投入意愿较强，适合优先跟进。"
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


def _normalize_candidate(row: Dict[str, Any], score: int, tags: List[str], score_parts: Dict[str, int], signal: Dict[str, Any]) -> Dict[str, Any]:
    region = _clean_text(row.get("region")) or _clean_text(row.get("city")) or _clean_text(row.get("province"))
    industry = (
        _clean_text(row.get("industry"))
        or _clean_text(row.get("industry_alt"))
        or _clean_text(row.get("marketing_industry_l1"))
        or _clean_text(row.get("group_industry_l1"))
        or "未标注"
    )
    level = "HOT" if score >= 80 else "关注"
    return {
        "name": _clean_text(row.get("name")),
        "short_name": _clean_text(row.get("short_name")),
        "score": score,
        "level": level,
        "industry": industry,
        "region": region or "未标注",
        "signals": tags[:6],
        "reason": build_reason(row, tags, signal),
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
        "latest_title": _clean_text(signal.get("latest_title")),
        "latest_date": _clean_text(signal.get("latest_date")),
        "link": _clean_text(signal.get("link")),
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


def get_recommendations(filters: Dict[str, Any], limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    try:
        candidates = fetch_candidate_enterprises(filters)
        signals = fetch_enterprise_signals(candidates)
        recommendations = []
        ranked_all = []
        score_min = int(filters.get("score_min") or DEFAULT_SCORE_MIN)

        for row in candidates:
            name = _clean_text(row.get("name"))
            signal = signals.get(name, {})
            score, tags, score_parts = score_enterprise(row, signal)
            normalized = _normalize_candidate(row, score, tags, score_parts, signal)
            ranked_all.append(normalized)
            if score >= score_min:
                recommendations.append(normalized)

        recommendations.sort(key=lambda item: item["score"], reverse=True)
        if recommendations:
            return recommendations[:limit]

        # 行政区类查询如果没有超过阈值的企业，不直接返回空；保底返回该区域综合得分最高的若干企业。
        ranked_all.sort(key=lambda item: item["score"], reverse=True)
        if ranked_all and (filters.get("district") or filters.get("industry") or filters.get("keyword")):
            return ranked_all[: min(limit, 10)]
        return []
    except Exception as exc:
        import traceback
        db.log_event(None, "potential", "ERROR", f"高潜客户数据库检索失败，启用兜底数据: {exc}", traceback.format_exc())
        return _fallback_from_mock(filters, limit=limit)


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
    filters = parse_filters(keyword)
    db.log_event(user_id, "potential", "INFO", f"开始检索高潜客户线索。过滤条件: {filters}")

    items = get_recommendations(filters)
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
        actions.append({
            "label": "导出高潜客户 Excel",
            "type": "download",
            "url": _build_export_url(filters),
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

    items = get_recommendations(filters, limit=500)

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(base_dir, "static", "generated")
    ensure_dir(static_dir)

    safe_scope = district or industry or keyword or "全市"
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
    db.log_event(user_id, "potential", "INFO", f"高潜客户 Excel 导出成功: {excel_path}")
    return excel_path
