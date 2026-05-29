# -*- coding: utf-8 -*-
import os
import asyncio
from openai import AsyncOpenAI
from services.industry import ALL_26_INDUSTRIES
import utils.db_helper as db

async def handle_stream(user_text: str, user_id: int = None):
    """
    处理通用聊天/开放性问答意图，支持自动匹配本地行业库以增强上下文
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    
    # 1. 轻量级上下文增强（RAG）：扫描用户输入中是否提到了我们的 26 个行业
    matched_contexts = []
    user_text_lower = user_text.lower()
    
    # 简单的关键词匹配抽取行业内容
    for ind in ALL_26_INDUSTRIES:
        title = ind.get("title", "")
        # 从标题中提取行业名（例如 "一、 人工智能：..." -> "人工智能"）
        if "：" in title:
            name_part = title.split("：")[0]
            name = name_part.split("、")[-1].strip()
        else:
            name = title
            
        # 如果提到该行业，就把它的大纲加入上下文
        if name and name in user_text_lower:
            matched_contexts.append(f"【{name}行业背景参考】\n{ind.get('content', '')}")
            
    # 如果没提取出纯净的名字，也可以用一些常见关键词做二次嗅探
    keywords_mapping = {
        "人工智能": "人工智能", "ai": "人工智能", "新能源": "新新能源产业", "光伏": "新新能源产业",
        "半导体": "集成电路领域", "芯片": "集成电路领域", "医药": "生物医药领域", 
        "消费": "消费品牌", "机器人": "智能机器人", "空天": "空天经济", "数字": "数字经济领域"
    }
    
    for kw, target_ind in keywords_mapping.items():
        if kw in user_text_lower:
            for ind in ALL_26_INDUSTRIES:
                if target_ind in ind.get("title", ""):
                    context_str = f"【{target_ind}背景参考】\n{ind.get('content', '')}"
                    if context_str not in matched_contexts:
                        matched_contexts.append(context_str)

    # 组装上下文
    context_injection = ""
    if matched_contexts:
        context_injection = "\n\n以下是系统内部有关用户提问涉及行业的参考资料，请结合这些资料进行深度分析和对比：\n" + "\n---\n".join(matched_contexts)
        db.log_event(user_id, "general_chat", "INFO", f"通用问答触发行业资料增强，匹配到 {len(matched_contexts)} 份参考报告。")

    if not api_key or "your_api_key" in api_key:
        fallback = "⚠️ **提示**：未检测到有效大模型密钥。无法为您提供自由对话和深度分析，请在 `.env` 中配置 `DEEPSEEK_API_KEY`。"
        chunk_size = 5
        for i in range(0, len(fallback), chunk_size):
            yield fallback[i:i+chunk_size]
            await asyncio.sleep(0.015)
        return

    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        system_instructions = (
            "你是一个资深的产业分析师和商业大客户经理。用户可能会向你咨询行业对比、业务建议、宏观分析或日常交流。\n"
            "请直接、专业、热情地回答用户的问题。如果系统提供了【行业背景参考】，请务必基于参考资料中的数据和事件进行总结和对比。\n"
            "回答要求排版精美（使用 Markdown 列表、加粗），条理清晰，有深度商业洞见。"
        )
        
        prompt = user_text + context_injection
        
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            timeout=30.0,
            stream=True
        )
        
        async for chunk in response:
            delta_content = chunk.choices[0].delta.content
            if delta_content:
                yield delta_content
                
    except Exception as e:
        import traceback
        db.log_event(user_id, "general_chat", "ERROR", f"通用对话流式过程出错: {str(e)}", traceback.format_exc())
        yield f"\n\n⚠️ 大模型响应出错: {str(e)}"
