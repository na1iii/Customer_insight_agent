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
    intent: Literal["query_customer", "regional_report", "industry_report", "high_potential", "general_chat"] = Field(
        description="判断用户想进入的子业务场景"
    )
    keyword: Optional[str] = Field(None, description="提取主体名称。如公司名（上海电信）、行政区（静安区）、行业名（通信行业）。对于general_chat，可以直接放入用户的关键实体或空着")

def get_intent_router(user_input: str, user_id: int = None, chat_history: list = None) -> TaskCommand:
    """
    根据用户输入，调用大模型分析其业务意图，并提取关键实体。
    如果未配置 API Key，将回退到基于规则的意图识别。
    """
    text = (user_input or "").strip()
    if not text:
        return TaskCommand(intent="general_chat", keyword="")
        
    # 0. 优先匹配数据库中的企业简称/别名/全称 (仅在输入相对简短且不含其他场景明确特征词时，以防误碰)
    text_lower = text.lower()
    has_other_intent_words = any(w in text_lower for w in ["区", "行业", "pdf", "html", "报告", "高潜", "名单", "excel", "导出", "趋势", "对比", "分析", "策略", "商机", "线索", "舆情", "规模", "竞争", "客户", "意向"])
    if len(text_lower) >= 2 and not has_other_intent_words:
        try:
            from utils.alias_helper import alias_helper
            # 1. 优先完全匹配别名/简称
            for k, v in alias_helper.alias_to_official.items():
                if k.lower() == text_lower:
                    print(f"【Router Quick Hit】完全匹配到简称: {k} -> {v}")
                    return TaskCommand(intent="query_customer", keyword=v)
            # 2. 优先完全匹配官方全称
            for k in alias_helper.official_to_alias.keys():
                if k.lower() == text_lower:
                    print(f"【Router Quick Hit】完全匹配到官方全称: {k}")
                    return TaskCommand(intent="query_customer", keyword=k)
            # 3. 模糊匹配 (当输入长度小于 15 时才允许，防止长提问被误碰)
            if len(text_lower) < 15:
                for k, v in alias_helper.alias_to_official.items():
                    if k.lower() in text_lower or text_lower in k.lower():
                        print(f"【Router Quick Hit】模糊匹配到简称: {k} -> {v}")
                        return TaskCommand(intent="query_customer", keyword=v)
        except Exception as route_err:
            print(f"【Router Quick Hit Error】 {route_err}")
        
    generic_prompts = {
        "我想看一家企业的精准画像": TaskCommand(intent="query_customer", keyword=None),
        "我想生成一份区域经济报告": TaskCommand(intent="regional_report", keyword=None),
        "我想查看行业发展趋势报告": TaskCommand(intent="industry_report", keyword=None),
        "我想找一些高潜客户线索": TaskCommand(intent="high_potential", keyword=None)
    }
    if text in generic_prompts:
        return generic_prompts[text]

    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    
    # 兜底解析逻辑，以防 API 调用失败
    def fallback_parse(text: str) -> TaskCommand:
        text_lower = text.lower()
        
        # 0. 结合上下文处理短回答（如仅输入地名或公司名）
        if chat_history and len(text_lower) < 15:
            last_msg = next((m for m in reversed(chat_history) if m.get("role") == "assistant"), None)
            if last_msg:
                content = last_msg.get("content", "")
                if "高潜客户" in content or "重点客户" in content:
                    return TaskCommand(intent="high_potential", keyword=text.strip())
                if "哪家企业" in content or "画像" in content:
                    return TaskCommand(intent="query_customer", keyword=text.strip())
                if "区域经济" in content or "哪个区" in content:
                    return TaskCommand(intent="regional_report", keyword=text.strip())
                if "发展趋势报告" in content or "哪个行业" in content:
                    return TaskCommand(intent="industry_report", keyword=text.strip())
                    
        if text_lower in ["我想看一家企业的精准画像", "我想生成一份区域经济报告", "我想查看行业发展趋势报告", "我想找一些高潜客户线索"]:
            mapping = {
                "我想看一家企业的精准画像": "query_customer",
                "我想生成一份区域经济报告": "regional_report",
                "我想查看行业发展趋势报告": "industry_report",
                "我想找一些高潜客户线索": "high_potential"
            }
            return TaskCommand(intent=mapping[text_lower], keyword=None)
        districts = [
            "浦东新区", "黄浦区", "徐汇区", "长宁区", "静安区", "普陀区", "虹口区", "杨浦区",
            "闵行区", "宝山区", "嘉定区", "金山区", "松江区", "青浦区", "奉贤区", "崇明区",
            "浦东", "黄浦", "徐汇", "长宁", "静安", "普陀", "虹口", "杨浦", "闵行", "宝山", "嘉定", "金山", "松江", "青浦", "奉贤", "崇明"
        ]
        # 完整覆盖数据中包含的所有 26 个行业的关键词，以及最新的数据库真实分类
        industries = [
            "现代服务业", "数字化转型", "未来产业", "先导产业", "重点支撑产业", "先进制造业",
            "通信", "人工智能", "ai", "医疗", "医药", "生物医药", "集成电路", "半导体", "芯片", 
            "新能源", "光伏", "风电", "储能", "机器人", "建筑", "建筑业", "汽车", "消费品牌", 
            "空天", "卫星", "数字经济", "战新", "战略性新兴产业", "装备制造", "装备", 
            "时尚消费", "新材料", "航天", "核电", "电子信息", "钢铁", "能源", "船舶", 
            "航空", "大飞机", "水务"
        ]
        
        # 优先级 1: 区域报告 (问题涉及“区域+线索/舆情/商机”等关键词，即使含具体客户)
        regional_keywords = ["线索", "舆情", "商机", "报告", "图表", "明细"]
        has_regional_word = False
        extracted_region = None
        
        for r in ["静安", "浦东", "黄浦", "徐汇", "长宁", "普陀", "虹口", "杨浦", "闵行", "宝山", "嘉定", "金山", "松江", "青浦", "奉贤", "崇明"]:
            if r in text_lower:
                has_regional_word = True
                extracted_region = f"{r}新区" if r == "浦东" else f"{r}区"
                break
        if not has_regional_word and any(w in text_lower for w in ["上海", "全市", "区域"]):
            has_regional_word = True
            extracted_region = "上海市" if any(w in text_lower for w in ["上海", "全市"]) else None

        if has_regional_word and any(w in text_lower for w in regional_keywords):
            return TaskCommand(intent="regional_report", keyword=extracted_region)
        
        # 针对未指定区县但明确请求区域报告的兜底
        if "区域报告" in text_lower or "区域经济" in text_lower:
            return TaskCommand(intent="regional_report", keyword=None)

        # 优先级 2: 企业画像 (问题中提到具体企业名称)
        for comp in ["电信", "移动", "联通", "钛度", "特斯拉"]:
            if comp in text_lower:
                keyword_map = {
                    "电信": "中国电信股份有限公司上海分公司",
                    "移动": "中国移动通信集团上海有限公司",
                    "联通": "中国联合网络通信有限公司上海市分公司",
                    "钛度": "钛度智能机器人设计与研发中心",
                    "特斯拉": "特斯拉"
                }
                return TaskCommand(intent="query_customer", keyword=keyword_map[comp])

        # 通用企业画像特征词
        for indicator in ["怎么样", "画像", "痛点", "介绍", "情况", "动态"]:
            if indicator in text_lower:
                parts = text_lower.split(indicator)
                kw = parts[0].strip()
                if kw.endswith("的"):
                    kw = kw[:-1].strip()
                if kw and len(kw) > 1 and kw not in ["行业", "区域", "客户"]:
                    return TaskCommand(intent="query_customer", keyword=kw)

        # 优先级 3: 高潜推荐 (问题涉及客户/高潜/意向等关键词，且不含具体企业名)
        if any(w in text_lower for w in ["高潜", "潜在", "重点客户", "推荐", "客户", "线索", "名单", "excel", "导出", "意向", "表格"]):
            extracted = []
            for r in districts:
                if r.lower() in text_lower and r not in extracted:
                    extracted.append(r)
                    break
            for ind in industries:
                if ind.lower() in text_lower and ind not in extracted:
                    extracted.append("人工智能" if ind == "ai" else ind)
                    break
            if not extracted:
                cleaned = text
                for noise in ["推荐", "高潜", "潜在", "重点", "客户", "名单", "线索", "导出", "excel", "Excel", "表格", "有哪些", "帮我", "给我", "意向"]:
                    cleaned = cleaned.replace(noise, " ")
                cleaned = " ".join(cleaned.split())
                if cleaned:
                    extracted.append(cleaned)
            return TaskCommand(intent="high_potential", keyword=" ".join(extracted) if extracted else None)

        # 优先级 4: 行业深度 (问题涉及行业趋势/规模/竞争等关键词)
        if any(w in text_lower for w in ["行业", "趋势", "规模", "竞争", "研报", "pdf", "html"]):
            extracted_ind = "全行业"
            for ind in industries:
                if ind in text_lower:
                    extracted_ind = "人工智能行业" if ind in ["人工智能", "ai"] else ("医药行业" if ind in ["医疗", "医药", "生物医药"] else f"{ind}行业" if not ind.endswith("行业") and not ind.endswith("业") else ind)
                    break
            return TaskCommand(intent="industry_report", keyword=extracted_ind)
            
        # 兜底：短文本无特征词视为查企业
        if len(text_lower.strip()) < 10 and not any(w in text_lower for w in ["区", "行业", "pdf", "html", "报告", "高潜", "名单", "excel", "导出", "线索", "舆情", "规模", "竞争", "客户"]):
            return TaskCommand(intent="query_customer", keyword=text_lower.strip())
                
        # 最终兜底
        return TaskCommand(intent="general_chat", keyword=text)

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
            "返回的 JSON 必须且只能包含以下两个字段：'intent' 和 'keyword'。\n\n"
            "【统一路由规则优先级】(请严格按照以下顺序判断)：\n"
            "1. 'regional_report' (区域报告): 当问题涉及“行政区域”并带有“线索/舆情/商机/报告”等关键词时（如'静安区的线索'，'上海市的区域商机'），即使提及了具体客户也必须去区域报告。\n"
            "2. 'query_customer' (企业画像): 如果不符合区域报告，且问题中明确提到具体的企业/公司名称时（如'莉莉丝游戏怎么样'，'特斯拉介绍'）。\n"
            "3. 'high_potential' (高潜推荐): 如果排除了具体企业名，且问题涉及'客户/高潜/意向/推荐/名单/线索'等关键词时（如'给我推荐一些高潜客户'，'通信行业的意向名单'）。\n"
            "4. 'industry_report' (行业深度): 当问题涉及'行业趋势/规模/竞争/行业研报'等关键词时。\n"
            "5. 'general_chat' (通用问答): 无法归入上述四类的通用聊天或跨行业对比。\n\n"
            "【keyword 提取规则】：\n"
            "   - 对于 'query_customer'，提取具体的公司名称。\n"
            "   - 对于 'regional_report'，提取具体的行政区名称（如'上海市'、'静安区'），若没有提取到具体区则为 null。\n"
            "   - 对于 'industry_report'，提取具体的行业名称。若无具体行业，则必须为'全行业'。\n"
            "   - 对于 'high_potential'，提取相关的行政区和/或行业名称。\n"
            "   - 对于 'general_chat'，提取关键实体或 null。\n\n"
            "【极端重要提示】：如果用户输入仅仅是一个地名或行业名（例如：'浦东新区'），你必须结合上下文中的 assistant 提问来决定 intent！如果上一轮 assistant 问的是“挖掘哪个区的高潜客户？”，则 intent 必须是 'high_potential'！不要因为有地名就盲目判定。\n"
            "你的回答必须是合法的 JSON 字符串，不能包含 markdown 标记，不加任何解释。"
        )
        
        messages = [{"role": "system", "content": system_prompt}]
        
        if chat_history:
            # 取最近的3-5条消息作为上下文
            recent_history = chat_history[-5:]
            for msg in recent_history:
                role = "user" if msg.get("role") == "user" else "assistant"
                messages.append({"role": role, "content": msg.get("content", "")[:500]})
                
        messages.append({"role": "user", "content": user_input})

        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0,
            timeout=10.0
        )
        
        content = response.choices[0].message.content
        print(f"【Router JSON Response】: {content}")
        
        data = json.loads(content)
        command = TaskCommand.model_validate(data)
        
    except Exception as e:
        print(f"【Router Error】大模型解析意图失败 ({e})，启用本地规则路由。")
        command = fallback_parse(user_input)

    # 后置修正：若提取出的意图为行业报告且关键词包含或等于上海市/各区等行政区划词，自动修正为全行业
    if command and command.intent == "industry_report":
        kw = (command.keyword or "").strip()
        regions_list = [
            "浦东新区", "黄浦区", "徐汇区", "长宁区", "静安区", "普陀区", "虹口区", "杨浦区",
            "闵行区", "宝山区", "嘉定区", "金山区", "松江区", "青浦区", "奉贤区", "崇明区",
            "浦东", "黄浦", "徐汇", "长宁", "静安", "普陀", "虹口", "杨浦", "闵行", "宝山", "嘉定", "金山", "松江", "青浦", "奉贤", "崇明",
            "上海", "上海市", "全市", "全区", "区域", "全市行业", "全市所有行业"
        ]
        if not kw or "全行业" in kw or kw in regions_list:
            command.keyword = "全行业"
            
    return command