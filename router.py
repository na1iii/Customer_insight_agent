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
        
        # 0. 上海市/全市商机报告意图：展示 16 个区的汇总明细
        if any(w in text_lower for w in ["上海市", "全上海", "全市", "上海"]) and any(w in text_lower for w in ["报告", "商机", "区域", "明细"]):
            # 如果文本中同时包含特定行业，或者明确要求“行业报告”，则不判定为区域报告
            if not any(ind in text_lower for ind in industries) and "行业报告" not in text_lower and "行业研报" not in text_lower:
                return TaskCommand(intent="regional_report", keyword="上海市")

        # 1. 高潜客户意图：优先于区域报告，避免“推荐静安区高潜客户”被误判为区域分析
        if any(w in text_lower for w in ["高潜", "潜在客户", "重点客户", "推荐客户", "客户名单", "线索", "表格", "名单", "excel", "导出"]):
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
                for noise in ["推荐", "高潜", "潜在", "重点", "客户", "名单", "线索", "导出", "excel", "Excel", "表格", "有哪些", "帮我", "给我"]:
                    cleaned = cleaned.replace(noise, " ")
                cleaned = " ".join(cleaned.split())
                if cleaned:
                    extracted.append(cleaned)
            return TaskCommand(intent="high_potential", keyword=" ".join(extracted) if extracted else None)
            
        # 2. 区级报告意图
        for r in ["静安", "浦东", "黄浦", "徐汇", "长宁", "普陀", "虹口", "杨浦"]:
            if r in text_lower and any(w in text_lower for w in ["区", "报告", "图表", "画像", "商机"]):
                # 如果包含具体行业关键字，或明确要求“行业报告”，则不判断为区级报告
                if not any(ind in text_lower for ind in industries) and "行业报告" not in text_lower and "行业研报" not in text_lower:
                    suffix = "新区" if r == "浦东" else "区"
                    return TaskCommand(intent="regional_report", keyword=f"{r}{suffix}")
                    
        # 2.1 针对未指定区县但请求区域经济报告的兜底
        if "区域报告" in text_lower or "区域经济报告" in text_lower or "区域商机" in text_lower:
            return TaskCommand(intent="regional_report", keyword=None)
                
        # 3. 行业报告意图
        for ind in industries:
            if ind in text_lower and any(w in text_lower for w in ["行业", "业", "pdf", "html", "发送", "群", "报告"]):
                keyword = "人工智能行业" if ind in ["人工智能", "ai"] else ("医药行业" if ind in ["医疗", "医药", "生物医药"] else f"{ind}行业" if not ind.endswith("行业") and not ind.endswith("业") else ind)
                return TaskCommand(intent="industry_report", keyword=keyword)
                
        # 3.1 针对未指定行业但请求行业报告的兜底
        # 只要输入中包含"行业报告"或"行业研报"，或者"生成/帮我/一份"与"报告"并存，均视为全行业报告
        if ("行业报告" in text_lower or "行业研报" in text_lower
                or "发行业报告" in text_lower
                or (("报告" in text_lower or "研报" in text_lower)
                    and ("生成" in text_lower or "帮我" in text_lower
                         or "帮他" in text_lower or "一份" in text_lower
                         or "行业" in text_lower))):
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
                kw = parts[0].strip()
                # 去掉末尾的助词"的"，但保留公司名中有意义的词（如"游戏"、"科技"、"集团"）
                if kw.endswith("的"):
                    kw = kw[:-1].strip()
                if kw:
                    return TaskCommand(intent="query_customer", keyword=kw)
                    
        if len(text_lower.strip()) < 10 and not any(w in text_lower for w in ["区", "行业", "pdf", "html", "报告", "高潜", "名单", "excel", "导出"]):
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
            "返回的 JSON 必须且只能包含以下两个字段：\n"
            "1. 'intent': 必须是以下五个之一:\n"
            "   - 'query_customer' (当用户询问某具体公司/客户的概况、画像、怎么样、痛点时，例如：'莉莉丝游戏怎么样'、'米哈游的情况'、'特斯拉介绍')\n"
            "   - 'regional_report' (当用户要查看某行政区的经济指标、图表、长图或区级报告时。注意：仅限于无特定行业属性的区域宏观报告，如'上海市商机报告'、'静安区区域报告')\n"
            "   - 'industry_report' (当用户需要生成行业深度分析、HTML/PDF 报告、或明确包含'行业报告'、'行业研报'字眼时。)\n"
            "   - 'high_potential' (当用户要求查看高潜客户、重点客户、潜在客户、推荐名单、展示客户表格、线索或导出 Excel 时)\n"
            "   - 'general_chat' (当用户进行通用聊天、问候、跨行业对比、分析建议、询问业务策略、比较两个行业、为什么、怎么办等非具体报表查询的灵活开放性提问时)\n"
            "2. 'keyword': 根据意图提取最合适的主体名称：\n"
            "   - 对于 'query_customer'，提取具体的公司/企业/客户名称（如'莉莉丝游戏'、'上海电信'）。\n"
            "   - 对于 'regional_report'，提取具体的行政区名称（如'上海市'、'静安区'、'浦东新区'）。\n"
            "   - 对于 'industry_report'，必须且只能提取具体的行业名称（如'汽车行业'、'人工智能'）。若用户表达的是‘全行业报告’、‘上海市全行业’或未指定具体行业，则 keyword 必须为'全行业'，绝对不要单独将城市或行政区（如'上海市'、'静安区'）作为行业 keyword 提取。\n"
            "   - 对于 'high_potential'，提取行政区和/或行业名称。\n"
            "   - 对于 'general_chat'，请将用户提问中包含的实体（如'新能源'、'人工智能'等）作为 keyword 返回，没有则为 null。\n\n"
            "【极端重要提示】：如果用户输入仅仅是一个地名或行业名（例如：'浦东新区'、'通信行业'），你必须结合上下文中的 assistant 提问来决定 intent！如果上一轮 assistant 问的是“您想挖掘哪个行政区或行业的**高潜客户**？”，那么当前 intent 必须是 'high_potential'，而绝对不能判定为 'regional_report'！同理，如果是在问企业画像，那就是 'query_customer'。不要因为输入有地名就盲目判定为区域报告！\n\n"
            "注意：你的回答必须是合法的 JSON 字符串，不能包含 ```json 这样的 markdown 标记，不要有任何多余的解释。"
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