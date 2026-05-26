# -*- coding: utf-8 -*-
"""
regional.py - 场景2：区级报告。生成区域商机分析卡片与明细页跳转链接。
"""

from urllib.parse import quote
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


def handle(keyword: str, user_id: int = None) -> dict:
    """
    根据关键字识别行政区，返回结构化区域商机报告卡片。
    """
    region_name = normalize_district(keyword)
    is_city_report = region_name == CITY_REPORT_NAME

    if keyword and region_name == DEFAULT_DISTRICT and DEFAULT_DISTRICT not in keyword:
        db.log_event(user_id, "regional", "WARNING", f"未能从输入 '{keyword}' 识别明确行政区，默认使用 {DEFAULT_DISTRICT}。")

    db.log_event(user_id, "regional", "INFO", f"开始生成 {region_name} 区域商机分析卡片。")

    # 与 /api/articles 明细页保持同一数据口径：均读取 opportunity_articles 预计算结果表。
    # 上海市报告不传 district，明细页默认按 16 个区折叠展示全部商机。
    summary = db.get_articles_summary(None if is_city_report else region_name)
    detail_url = "/ui_1.html" if is_city_report else f"/ui_1.html?district={quote(region_name)}"
    summary_text = build_summary_text(region_name, summary, is_city_report=is_city_report)

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
    }

    db.log_event(user_id, "regional", "INFO", f"{region_name} 区域商机分析卡片生成完毕。")
    return result
