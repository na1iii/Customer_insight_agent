# -*- coding: utf-8 -*-
"""
time_parser.py - 智能时间参数提取器，支持正则快速提取与大模型自然语言提取混合使用。
"""
import os
import re
from datetime import datetime
import json
from openai import OpenAI
import utils.db_helper as db

def extract_days_limit_smart(query: str, default_days: int = 30) -> int:
    if not query:
        return default_days

    # 1. 快路径：正则匹配标准表达
    if re.search(r'(今年|本年度|这一年|一年|本年)', query):
        now = datetime.now()
        return (now - datetime(now.year, 1, 1)).days or 1
    if re.search(r'(半年|六个月|6个月)', query):
        return 180
    if re.search(r'(一个季度|1个季度|三个月|3个月)', query):
        return 90
    if re.search(r'(两个月|2个月)', query):
        return 60
    if re.search(r'(一个月|1个月|30天)', query):
        return 30
    if re.search(r'(一周|一星期|7天|七天)', query):
        return 7
    if re.search(r'(全部|所有时间|不限时间)', query):
        return 3650

    # 2. 探测是否包含可能的时间词汇
    time_keywords = ["近", "过去", "前", "天", "周", "月", "年", "内", "上个", "这几"]
    if not any(kw in query for kw in time_keywords):
        return default_days

    # 3. 慢路径：调用大模型解析复杂/非标准时间
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")

    if not api_key or "your_api_key" in api_key:
        return default_days

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        today_str = datetime.now().strftime("%Y-%m-%d")
        system_prompt = (
            f"你是一个时间参数提取助手。今天是 {today_str}。"
            "请从用户的查询文本中提取查询的时间范围，并将其转换为过去的天数。"
            "如果用户说“过去两个月”，返回 60。"
            "如果用户说“上个月”，返回 30。"
            "如果用户说“两周内”，返回 14。"
            "如果用户说“近10天”，返回 10。"
            "如果用户没有提到任何时间，或者无法确定，请返回 30。"
            "请注意，你必须输出且仅输出一个合法的 JSON 对象，格式如下：\n"
            "{\n"
            "  \"days\": 60\n"
            "}\n"
            "不要包含 markdown 标记，不要有解释性言论。"
        )
        
        user_prompt = f"用户查询: {query}"
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            timeout=10.0
        )
        
        content = response.choices[0].message.content
        data = json.loads(content)
        days = data.get("days", default_days)
        
        if isinstance(days, int) and days > 0:
            db.log_event(None, "time_parser", "INFO", f"LLM 解析时间成功: '{query}' -> {days}天")
            return days
            
    except Exception as e:
        db.log_event(None, "time_parser", "WARNING", f"LLM 解析时间失败: {e}，使用默认值 {default_days}")
        
    return default_days
