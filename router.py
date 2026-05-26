# -*- coding: utf-8 -*-
"""
router.py - AI 路由器，负责意图分类和关键实体提取
"""

import os
import json
from typing import Literal, Optional
from pydantic import BaseModel, Field
from openai import OpenAI

class TaskCommand(BaseModel):
    intent: Literal["query_customer", "regional_report", "industry_report", "high_potential"] = Field(
        description="判断用户想进入的子业务场景"
    )
    keyword: Optional[str] = Field(None, description="提取主体名称。如公司名（上海电信）、行政区（静安区）、行业名（通信行业）")

def get_intent_router(user_input: str) -> TaskCommand:
    """
    通过 DeepSeek API 识别用户的意图并提取主体关键词
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    
    # 兜底解析逻辑，以防 API 调用失败
    def fallback_parse(text: str) -> TaskCommand:
        text_lower = text.lower()
        
        # 1. 高潜客户意图
        if any(w in text_lower for w in ["高潜", "线索", "表格", "名单", "excel", "导出"]):
            return TaskCommand(intent="high_potential", keyword=None)
            
        # 2. 区级报告意图
        for r in ["静安", "浦东", "黄浦"]:
            if r in text_lower and any(w in text_lower for w in ["区", "报告", "图表", "画像"]):
                return TaskCommand(intent="regional_report", keyword=f"{r}区")
                
        # 3. 行业报告意图
        for ind in ["通信", "人工智能", "ai", "医疗", "医药", "生物医药"]:
            if ind in text_lower and any(w in text_lower for w in ["行业", "pdf", "html", "发送", "群", "报告"]):
                keyword = "人工智能行业" if ind in ["人工智能", "ai"] else ("医药行业" if ind in ["医疗", "医药", "生物医药"] else f"{ind}行业")
                return TaskCommand(intent="industry_report", keyword=keyword)
                
        # 3.1 针对未指定行业但请求行业报告的兜底
        if "行业报告" in text_lower or "行业研报" in text_lower or (("报告" in text_lower or "研报" in text_lower) and ("生成" in text_lower or "帮我" in text_lower or "帮他" in text_lower or "一份" in text_lower)):
            return TaskCommand(intent="industry_report", keyword="全行业")

                
        # 4. 查询客户意图（判断公司名）
        for comp in ["电信", "移动", "联通", "钛度", "特斯拉"]:
            if comp in text_lower:
                keyword_map = {
                    "电信": "上海电信",
                    "移动": "上海移动",
                    "联通": "上海联通",
                    "钛度": "钛度智能",
                    "特斯拉": "特斯拉"
                }
                return TaskCommand(intent="query_customer", keyword=keyword_map[comp])
                
        # 更加通用的关键词模式匹配
        for indicator in ["怎么样", "画像", "痛点", "商机", "介绍", "情况", "动态"]:
            if indicator in text_lower:
                parts = text_lower.split(indicator)
                kw = parts[0].strip().replace("的", "")
                if kw:
                    return TaskCommand(intent="query_customer", keyword=kw)
                    
        if len(text_lower.strip()) < 10 and not any(w in text_lower for w in ["区", "行业", "pdf", "html", "报告", "高潜", "名单", "excel", "导出"]):
            return TaskCommand(intent="query_customer", keyword=text_lower.strip())
                
        # 最终兜底
        return TaskCommand(intent="query_customer", keyword="上海电信")

    # 如果没有配置 API KEY，直接执行本地兜底
    if not api_key or "your_api_key" in api_key:
        print("【Router】未配置有效的 DEEPSEEK_API_KEY，启用本地规则路由。")
        return fallback_parse(user_input)

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        system_prompt = (
            "你是一个严谨的业务路由专家。分析用户的输入，判断意图并提取核心实体，以标准的 JSON 格式返回。\n"
            "返回的 JSON 必须且只能包含以下两个字段：\n"
            "1. 'intent': 必须是以下四个之一:\n"
            "   - 'query_customer' (当用户询问某具体公司/客户的概况、画像、怎么样、痛点时)\n"
            "   - 'regional_report' (当用户要查看某行政区的经济指标、图表、长图或区级报告时)\n"
            "   - 'industry_report' (当用户需要生成行业深度分析、HTML/PDF 报告、或要求发送报告到群聊时)\n"
            "   - 'high_potential' (当用户要求查看高潜客户、推荐名单、展示客户表格或导出 Excel 时)\n"
            "2. 'keyword': 提取的主体名称，如公司名（如上海电信）、行政区（如静安区）、行业（如通信行业）。如果用户请求生成行业报告，但未指定具体行业（例如“帮我生成一份行业报告”、“生成一份行业报告”、“行业报告”），则 keyword 必须为“全行业”；如果没有提取到其他主体，则为 null。\n\n"
            "注意：你的回答必须是合法的 JSON 字符串，不能包含 ```json 这样的 markdown 标记，不要有任何多余的解释。"
        )
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            timeout=10.0
        )
        
        content = response.choices[0].message.content
        print(f"【Router JSON Response】: {content}")
        
        data = json.loads(content)
        return TaskCommand.model_validate(data)
        
    except Exception as e:
        print(f"【Router Error】大模型解析意图失败 ({e})，启用本地规则路由。")
        return fallback_parse(user_input)