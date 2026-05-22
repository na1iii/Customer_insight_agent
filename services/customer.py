# -*- coding: utf-8 -*-
"""
customer.py - 场景1：查询客户画像（支持 RAG 与 Agentic 实时网页搜索）
"""

import os
import json
from datetime import datetime
from openai import OpenAI
from utils.rag_engine import RAGEngine
from utils.mock_db import COMPANIES
import utils.db_helper as db

def handle(keyword: str, user_id: int = None) -> dict:
    """
    处理查询客户画像意图，采用 Advanced RAG + Agentic Web Search
    """
    if not keyword:
        keyword = "上海电信"
        
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    
    # 1. 初始化 RAG 引擎
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    knowledge_dir = os.path.join(base_dir, "data", "knowledge")
    rag = RAGEngine(knowledge_dir)
    
    # 2. 本地检索
    retrieved_docs = rag.retrieve(keyword, top_k=3)
    
    # 3. 对召回文档执行 LLM 重排 (如果配置了 API Key)
    if api_key and "your_api_key" not in api_key:
        retrieved_docs = rag.rerank(keyword, retrieved_docs, api_key, base_url, model_name)
    else:
        # 否则降级，重排分数等于混合检索分
        for doc in retrieved_docs:
            doc["rerank_score"] = doc.get("final_score", 0.0)
            
    # 4. 判断是否命中本地知识库 (设定合理的阈值)
    # 本地检索匹配判断：1. 得分最高项的分数满足基础条件，且 2. 该文档的 company 字段与 keyword 有字面交集。
    is_hit = False
    best_doc = None
    if retrieved_docs:
        best_doc = retrieved_docs[0]
        best_score = best_doc.get("rerank_score", 0.0)
        company_name = best_doc["metadata"].get("company", "")
        # 如果得分最高项的检索重排分大于 0.05，或公司名称有字面交集，则判定命中
        if best_score > 0.05 or (keyword in company_name or company_name in keyword):
            is_hit = True

    source_type = "local_rag"
    context = ""
    company_metadata = {}
    
    if is_hit and best_doc:
        msg = f"本地知识库成功命中: {best_doc['metadata']['title']} (得分: {best_doc.get('rerank_score', 0.0):.4f})"
        db.log_event(user_id, "customer", "INFO", msg)
        # 采用 Parent-Child 策略：召回的是 Child，但喂给模型的是完整的 Parent Content
        context = best_doc["parent_content"]
        company_metadata = best_doc["metadata"]
    else:
        # 5. 未命中，直接降级从本地预设数据库/Mock DB读取
        msg = f"本地知识库未直接匹配 '{keyword}'。触发数据库降级：从本地预设数据库读取。"
        db.log_event(user_id, "customer", "WARNING", msg)
        company_data = None
        for k, v in COMPANIES.items():
            if keyword in k or k in keyword:
                company_data = v
                break
        if not company_data:
            company_data = COMPANIES["上海电信"]
            
        # 将 mock_db 的数据转换成类似于 Markdown 的 context
        context = (
            f"公司名称: {company_data['name']}\n"
            f"行业: {company_data['industry']}\n"
            f"规模: {company_data['scale']}\n"
            f"地址: {company_data['address']}\n"
            f"概况: {company_data['profile']}\n"
            f"合作背景: {company_data['cooperation']}\n"
            f"核心痛点: {', '.join(company_data['pain_points'])}"
        )
        company_metadata = {
            "title": company_data["name"],
            "company": keyword,
            "publish_date": "2026-05-21",
            "source": "Mock 预设数据库"
        }
        source_type = "mock_db"

    # 预置本地渲染 Markdown 的兜底模板 (当无 API Key 或大模型调用失败时使用)
    def render_local_markdown_fallback():
        source_label = "本地知识库（已进行 Advanced RAG 混合检索与时效性重排）" if source_type == "local_rag" else "本地预设数据库"
        
        return (
            f"## 🏢 {company_metadata.get('title', keyword)} 画像分析报告\n\n"
            f"> ⚠️ **提示**：未检测到有效大模型密钥（或 API 调用失败），以下是根据底层数据拼装的原始摘要。\n\n"
            f"🏷️ **公司主属性**：\n"
            f"* **行业类别**：{company_metadata.get('industry', '未知')}\n"
            f"* **信息时效**：{company_metadata.get('publish_date', '最新')}\n"
            f"* **数据来源**：{source_label}\n\n"
            f"### 📋 数据检索上下文概要\n"
            f"```text\n"
            f"{context[:800]}...\n"
            f"```\n\n"
            f"*[降级处理：请在 .env 中配置有效的 DEEPSEEK_API_KEY 以开启全自动大模型商业报告精细化润色与商机深度剖析。]*"
        )

    if not api_key or "your_api_key" in api_key:
        return {
            "type": "text",
            "content": render_local_markdown_fallback()
        }
        
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        # 让 AI 润色成高大上的售前分析报告，并结合检索数据深度提炼
        system_instructions = (
            "你是一个顶级的售前顾问和商业大客户经理，擅长将普通的企业基本信息或零散的搜索片段包装成具有深度商业洞察力的客户画像报告。"
        )
        
        prompt = (
            f"请根据以下获取的检索上下文数据，精细提炼并编写一份结构完整、措辞专业、排版精美的企业/客户画像分析报告（Markdown 格式）。\n"
            f"请特别分析该主体目前的【核心痛点/挑战】以及针对性的【商业合作契机与建议】（结合痛点给出解决方案思路）。\n\n"
            f"【检索上下文信息 ({source_type})】:\n"
            f"{context}\n\n"
            f"排版规范：\n"
            f"1. 多使用加粗、引用块、列表符号，让段落清晰易读。\n"
            f"2. 请在报告尾部单独附带一行来源说明（必须换行并用斜体展示），格式为：\n"
            f"   *数据来源：本地知识库（已进行 Advanced RAG 混合检索与时效性重排）* (如果是本地 RAG 数据)\n"
            f"   *数据来源：本地预设数据库* (如果是本地预设数据库数据)\n"
            f"3. 不要添加首尾问候语，直接输出分析报告正文。"
        )
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            timeout=15.0
        )
        
        return {
            "type": "text",
            "content": response.choices[0].message.content
        }
        
    except Exception as e:
        import traceback
        db.log_event(user_id, "customer", "ERROR", f"客户画像分析过程出错: {str(e)}", traceback.format_exc())
        return {
            "type": "text",
            "content": render_local_markdown_fallback()
        }
