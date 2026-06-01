# -*- coding: utf-8 -*-
"""
customer.py - 场景1：查询客户画像（支持 RAG 与 Agentic 实时网页搜索）
"""

import os
import json
import asyncio
from datetime import datetime
from openai import OpenAI, AsyncOpenAI
from utils.rag_engine import RAGEngine
import utils.db_helper as db

def handle(keyword: str, user_id: int = None) -> dict:
    """
    处理查询客户画像意图，采用 Advanced RAG + Agentic Web Search
    """
    if not keyword:
        return {
            "type": "text",
            "content": "请问您想分析哪家企业？（例如：上海电信、上海移动等）"
        }
        
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    
    # 1. 从业务数据库中检索企业基础线索、微信文章和项目合作新闻
    db_clue_info = None
    db_articles = []
    db_cooperations = []
    db_hit = False
    db_documents = []
    
    try:
        # A. 检索企业资质及营收属性 (ranking_ent_dtl_clue)
        # 用中文列名进行查询，并通过 AS 起别名保持兼容性
        clue_res = db.query_business_db(
            "SELECT `企业名称` AS EntName, `省份` AS Province, `城市` AS City, "
            "`2024年营业收入（万元）` AS Scale_revenue, `营业收入增长率` AS Growth_rate, "
            "`资质名称` AS Awards_list, `客户经理名称` AS Manager "
            "FROM ranking_ent_dtl_clue WHERE `企业名称` LIKE :keyword LIMIT 1",
            {"keyword": f"%{keyword}%"}
        )
        if clue_res:
            db_clue_info = clue_res[0]
            
        # B. 检索微信公众号动态 (wechat_article_ai_parse, weixin_article_dtl_unique)
        articles_parse = db.query_business_db(
            "SELECT `EntName`, `Abstract`, `Topic` FROM wechat_article_ai_parse WHERE `EntName` LIKE :keyword OR `Abstract` LIKE :keyword LIMIT 5",
            {"keyword": f"%{keyword}%"}
        )
        articles_unique = db.query_business_db(
            "SELECT `title`, `content`, `link`, `date` FROM weixin_article_dtl_unique WHERE `title` LIKE :keyword OR `content` LIKE :keyword LIMIT 5",
            {"keyword": f"%{keyword}%"}
        )
        
        # C. 检索项目合作签约动态 (zq_dtl_shnews_yyy)
        news_res = db.query_business_db(
            "SELECT `标题`, `内容`, `来源`, `URL`, `发布日期` FROM zq_dtl_shnews_yyy "
            "WHERE `标题` LIKE :keyword OR `内容` LIKE :keyword LIMIT 5",
            {"keyword": f"%{keyword}%"}
        )
        
        # 将拉取到的关系型文本拼装成 RAGEngine 需要的内存文档结构
        for a in articles_unique:
            db_documents.append({
                "title": a.get("title") or "微信文章",
                "content": a.get("content") or "",
                "publish_date": a.get("date") or "",
                "source": a.get("name") or "微信公众号",
                "link": a.get("link") or "",
                "company": keyword
            })
            
        for a in articles_parse:
            db_documents.append({
                "title": a.get("Topic") or "微信舆情摘要",
                "content": a.get("Abstract") or "",
                "publish_date": "",
                "source": "微信动态解析",
                "link": "",
                "company": keyword
            })
            
        for n in news_res:
            db_documents.append({
                "title": n.get("标题") or "重大合作项目",
                "content": n.get("内容") or "",
                "publish_date": n.get("发布日期") or "",
                "source": n.get("来源") or "新闻动态",
                "link": n.get("URL") or "",
                "company": keyword
            })
            
        # 格式化列表，以防后续还需要用到
        for a in articles_parse:
            ent = a.get("EntName", "")
            abst = a.get("Abstract", "")
            topic = a.get("Topic", "")
            db_articles.append(f"【微信动态解析】企业名称: {ent} | 主题: {topic} | 摘要: {abst}")
            
        for a in articles_unique:
            title = a.get("title", "")
            content = a.get("content", "")[:300]
            link = a.get("link", "")
            date = a.get("date", "")
            db_articles.append(f"【微信文章】标题: {title} | 发布时间: {date} | 正文片段: {content} | 链接: {link}")
            
        for n in news_res:
            title = n.get("标题") or "无标题"
            src = n.get("来源") or "未知来源"
            date = n.get("发布日期") or "未知日期"
            content = (n.get("内容") or "")[:200]
            db_cooperations.append(f"【合作签约动态】标题: {title} | 来源: {src} | 日期: {date} | 摘要: {content}")
            
        if db_clue_info or db_documents:
            db_hit = True
    except Exception as db_err:
        db.log_event(user_id, "customer", "ERROR", f"直连 MySQL 检索企业多源数据失败: {db_err}")

    # 2. 对从数据库加载的文本记录，在内存中初始化 RAG 引擎，并执行 BM25 检索与大模型重排
    retrieved_docs = []
    is_hit = False
    best_doc = None
    
    if db_documents:
        rag = RAGEngine(documents=db_documents)
        retrieved_docs = rag.retrieve(keyword, top_k=3)
        
        # 3. 对召回文档执行 LLM 重排 (如果配置了 API Key)
        if api_key and "your_api_key" not in api_key:
            retrieved_docs = rag.rerank(keyword, retrieved_docs, api_key, base_url, model_name)
        else:
            for doc in retrieved_docs:
                doc["rerank_score"] = doc.get("final_score", 0.0)
                
        if retrieved_docs:
            best_doc = retrieved_docs[0]
            best_score = best_doc.get("rerank_score", 0.0)
            
            # 由于已从数据库根据 keyword 过滤出来的文章做 BM25，这里已支持重排，设置 0.20 可有效过滤次要提及的噪音
            if best_score > 0.20:
                is_hit = True

    # 4. 融合与状态处理
    source_type = "mysql_structured_query"
    context = ""
    company_metadata = {}
    
    # 组装来自数据库的企业基础资质
    db_context_pieces = []
    if db_clue_info:
        ent = db_clue_info.get("EntName", keyword)
        prov = db_clue_info.get("Province", "")
        city = db_clue_info.get("City", "")
        scale = db_clue_info.get("Scale_revenue", "")
        growth = db_clue_info.get("Growth_rate", "")
        awards = db_clue_info.get("Awards_list", "")
        manager = db_clue_info.get("Manager", "")
        db_context_pieces.append(
            f"【企业基础资质与财务属性】:\n"
            f"企业名称: {ent}\n"
            f"行政归属: {prov}{city}\n"
            f"营收规模: {scale}\n"
            f"营业收入增长率: {growth}\n"
            f"所获榜单资质: {awards}\n"
            f"对接客户经理: {manager}"
        )
    db_context_str = "\n\n".join(db_context_pieces)

    if is_hit and best_doc:
        msg = f"关系型数据库 RAG 检索成功命中: {best_doc['metadata']['title']} (BM25评分: {best_doc.get('rerank_score', 0.0):.4f})"
        db.log_event(user_id, "customer", "INFO", msg)
        context = f"【高精度匹配的深度舆情/新闻文章】:\n标题: {best_doc['metadata']['title']}\n发布日期: {best_doc['metadata']['publish_date']}\n数据源: {best_doc['metadata']['source']}\n内容:\n{best_doc['parent_content']}"
        if db_context_pieces:
            context += "\n\n" + db_context_str
        source_type = "mysql_db_bm25_rag"
        company_metadata = best_doc["metadata"]
    elif db_hit:
        msg = f"未匹配到相关的深度文章/新闻，但已匹配到 '{keyword}' 的企业基础信息，执行数据库基础画像。"
        db.log_event(user_id, "customer", "INFO", msg)
        is_hit = True
        context = db_context_str
        
        # 填充基本元数据
        title_meta = keyword
        ind_meta = "动态企业"
        if db_clue_info:
            title_meta = db_clue_info.get("EntName", keyword)
            ind_meta = db_clue_info.get("Awards_list") or "优质线索企业"
        company_metadata = {"title": title_meta, "industry": ind_meta, "publish_date": "实时直连库"}
        source_type = "mysql_structured_query"
    else:
        msg = f"关系型业务数据库中未匹配到 '{keyword}'。已返回未检索到信息提示与推荐。"
        db.log_event(user_id, "customer", "WARNING", msg)
        
        apology_content = (
            f"### 🔍 检索反馈\n\n"
            f"很抱歉，我们目前的业务数据库中暂时没有收录与您查询的 **“{keyword}”** 相关的商业分析或画像数据。\n\n"
            f"💡 **推荐您尝试检索以下已收录的行业标杆企业：**\n"
            f"* 🏢 **上海电信**（中国电信股份有限公司上海分公司）\n"
            f"* 🏢 **上海移动**（中国移动通信集团上海有限公司）\n"
            f"* 🏢 **上海联通**（中国联合网络通信有限公司上海市分公司）\n"
            f"* 🏢 **钛度智能**（钛度智能机器人设计与研发中心）\n\n"
            f"*(提示：如需分析更多企业，请确保将数据录入到 MySQL 后台的 5 张业务表中，系统将自动支持检索。)*"
        )
        return {
            "type": "text",
            "content": apology_content
        }

    def render_local_markdown_fallback():
        return (
            f"## 🏢 {company_metadata.get('title', keyword)} 画像分析报告\n\n"
            f"> ⚠️ **提示**：未检测到有效大模型密钥（或 API 调用失败），以下是根据底层数据拼装的原始摘要。\n\n"
            f"🏷️ **公司主属性**：\n"
            f"* **行业类别**：{company_metadata.get('industry', '未知')}\n"
            f"* **信息时效**：{company_metadata.get('publish_date', '最新')}\n"
            f"* **数据来源**：本地知识库（已进行 Advanced RAG 混合检索与时效性重排）\n\n"
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
            f"请根据以下获取的检索上下文数据，针对 “{keyword}” 这一特定企业主体，精细提炼并编写一份结构完整、措辞专业、排版精美的企业/客户画像分析报告（Markdown 格式）。\n"
            f"请特别分析 “{keyword}” 目前的【核心痛点/挑战】以及针对性的【商业合作契机与建议】（结合痛点给出解决方案思路）。如果上下文包含其他无关企业的资料，请予以忽略，仅聚焦分析 “{keyword}” 本身。\n\n"
            f"【检索上下文信息 ({source_type})】:\n"
            f"{context}\n\n"
            f"排版规范：\n"
            f"1. 多使用加粗、引用块、列表符号，让段落清晰易读。\n"
            f"2. 请在报告尾部单独附带一行来源说明（必须换行并用斜体展示），格式为：\n"
            f"   *数据来源：本地知识库（已进行 Advanced RAG 混合检索与时效性重排）*\n"
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

async def handle_stream(keyword: str, user_id: int = None):
    """
    处理查询客户画像意图，采用异步流式输出方式返回
    """
    if not keyword:
        msg = "请问您想分析哪家企业？（例如：上海电信、上海移动等）"
        chunk_size = 5
        for i in range(0, len(msg), chunk_size):
            yield msg[i:i+chunk_size]
            await asyncio.sleep(0.015)
        return
        
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    
    # 1. 从业务数据库中检索企业基础线索、微信文章和项目合作新闻
    db_clue_info = None
    db_articles = []
    db_cooperations = []
    db_hit = False
    db_documents = []
    
    # 在线程池中执行关系数据库查询，避免阻塞事件循环
    def query_db_sync():
        nonlocal db_clue_info, db_hit
        try:
            clue_res = db.query_business_db(
                "SELECT `企业名称` AS EntName, `省份` AS Province, `城市` AS City, "
                "`2024年营业收入（万元）` AS Scale_revenue, `营业收入增长率` AS Growth_rate, "
                "`资质名称` AS Awards_list, `客户经理名称` AS Manager "
                "FROM ranking_ent_dtl_clue WHERE `企业名称` LIKE :keyword LIMIT 1",
                {"keyword": f"%{keyword}%"}
            )
            if clue_res:
                db_clue_info = clue_res[0]
                
            articles_parse = db.query_business_db(
                "SELECT `EntName`, `Abstract`, `Topic` FROM wechat_article_ai_parse WHERE `EntName` LIKE :keyword OR `Abstract` LIKE :keyword LIMIT 5",
                {"keyword": f"%{keyword}%"}
            )
            articles_unique = db.query_business_db(
                "SELECT `title`, `content`, `link`, `date` FROM weixin_article_dtl_unique WHERE `title` LIKE :keyword OR `content` LIKE :keyword LIMIT 5",
                {"keyword": f"%{keyword}%"}
            )
            news_res = db.query_business_db(
                "SELECT `标题`, `内容`, `来源`, `URL`, `发布日期` FROM zq_dtl_shnews_yyy "
                "WHERE `标题` LIKE :keyword OR `内容` LIKE :keyword LIMIT 5",
                {"keyword": f"%{keyword}%"}
            )
            
            for a in articles_unique:
                db_documents.append({
                    "title": a.get("title") or "微信文章",
                    "content": a.get("content") or "",
                    "publish_date": a.get("date") or "",
                    "source": a.get("name") or "微信公众号",
                    "link": a.get("link") or "",
                    "company": keyword
                })
                
            for a in articles_parse:
                db_documents.append({
                    "title": a.get("Topic") or "微信舆情摘要",
                    "content": a.get("Abstract") or "",
                    "publish_date": "",
                    "source": "微信动态解析",
                    "link": "",
                    "company": keyword
                })
                
            for n in news_res:
                db_documents.append({
                    "title": n.get("标题") or "重大合作项目",
                    "content": n.get("内容") or "",
                    "publish_date": n.get("发布日期") or "",
                    "source": n.get("来源") or "新闻动态",
                    "link": n.get("URL") or "",
                    "company": keyword
                })
                
            for a in articles_parse:
                ent = a.get("EntName", "")
                abst = a.get("Abstract", "")
                topic = a.get("Topic", "")
                db_articles.append(f"【微信动态解析】企业名称: {ent} | 主题: {topic} | 摘要: {abst}")
                
            for a in articles_unique:
                title = a.get("title", "")
                content = a.get("content", "")[:300]
                link = a.get("link", "")
                date = a.get("date", "")
                db_articles.append(f"【微信文章】标题: {title} | 发布时间: {date} | 正文片段: {content} | 链接: {link}")
                
            for n in news_res:
                title = n.get("标题") or "无标题"
                src = n.get("来源") or "未知来源"
                date = n.get("发布日期") or "未知日期"
                content = (n.get("内容") or "")[:200]
                db_cooperations.append(f"【合作签约动态】标题: {title} | 来源: {src} | 日期: {date} | 摘要: {content}")
                
            if db_clue_info or db_documents:
                db_hit = True
        except Exception as db_err:
            db.log_event(user_id, "customer", "ERROR", f"直连 MySQL 检索企业多源数据失败: {db_err}")

    await asyncio.to_thread(query_db_sync)

    # 2. 对从数据库加载的文本记录，在内存中初始化 RAG 引擎，并执行 BM25 检索与大模型重排
    retrieved_docs = []
    is_hit = False
    best_doc = None
    
    def run_rag_retrieve_and_rerank():
        nonlocal retrieved_docs
        if db_documents:
            from utils.rag_engine import RAGEngine
            rag = RAGEngine(documents=db_documents)
            retrieved_docs = rag.retrieve(keyword, top_k=3)
            if api_key and "your_api_key" not in api_key:
                retrieved_docs = rag.rerank(keyword, retrieved_docs, api_key, base_url, model_name)
            else:
                for doc in retrieved_docs:
                    doc["rerank_score"] = doc.get("final_score", 0.0)
        return retrieved_docs

    try:
        # Run synchronous RAG indexing in helper context
        retrieved_docs = await asyncio.to_thread(run_rag_retrieve_and_rerank)
    except Exception as e:
        import traceback
        db.log_event(user_id, "customer", "ERROR", f"RAG检索/重排过程出错: {str(e)}", traceback.format_exc())
        retrieved_docs = []
        
    if retrieved_docs:
        best_doc = retrieved_docs[0]
        best_score = best_doc.get("rerank_score", 0.0)
        
        # 由于已从数据库根据 keyword 过滤出来的文章做 BM25，这里已支持重排，设置 0.20 可有效过滤次要提及的噪音
        if best_score > 0.20:
            is_hit = True

    # 4. 融合与状态处理
    source_type = "mysql_structured_query"
    context = ""
    company_metadata = {}
    
    # 组装来自数据库的企业基础资质
    db_context_pieces = []
    if db_clue_info:
        ent = db_clue_info.get("EntName", keyword)
        prov = db_clue_info.get("Province", "")
        city = db_clue_info.get("City", "")
        scale = db_clue_info.get("Scale_revenue", "")
        growth = db_clue_info.get("Growth_rate", "")
        awards = db_clue_info.get("Awards_list", "")
        manager = db_clue_info.get("Manager", "")
        db_context_pieces.append(
            f"【企业基础资质与财务属性】:\n"
            f"企业名称: {ent}\n"
            f"行政归属: {prov}{city}\n"
            f"营收规模: {scale}\n"
            f"营业收入增长率: {growth}\n"
            f"所获榜单资质: {awards}\n"
            f"对接客户经理: {manager}"
        )
    db_context_str = "\n\n".join(db_context_pieces)

    if is_hit and best_doc:
        msg = f"关系型数据库 RAG 检索成功命中: {best_doc['metadata']['title']} (BM25评分: {best_doc.get('rerank_score', 0.0):.4f})"
        db.log_event(user_id, "customer", "INFO", msg)
        context = f"【高精度匹配的深度舆情/新闻文章】:\n标题: {best_doc['metadata']['title']}\n发布日期: {best_doc['metadata']['publish_date']}\n数据源: {best_doc['metadata']['source']}\n内容:\n{best_doc['parent_content']}"
        if db_context_pieces:
            context += "\n\n" + db_context_str
        source_type = "mysql_db_bm25_rag"
        company_metadata = best_doc["metadata"]
    elif db_hit:
        msg = f"未匹配到相关的深度文章/新闻，但已匹配到 '{keyword}' 的企业基础信息，执行数据库基础画像。"
        db.log_event(user_id, "customer", "INFO", msg)
        is_hit = True
        context = db_context_str
        
        # 填充基本元数据
        title_meta = keyword
        ind_meta = "动态企业"
        if db_clue_info:
            title_meta = db_clue_info.get("EntName", keyword)
            ind_meta = db_clue_info.get("Awards_list") or "优质线索企业"
        company_metadata = {"title": title_meta, "industry": ind_meta, "publish_date": "实时直连库"}
        source_type = "mysql_structured_query"
    else:
        msg = f"关系型业务数据库中未匹配到 '{keyword}'。已返回未检索到信息提示与推荐。"
        db.log_event(user_id, "customer", "WARNING", msg)
        
        apology_content = (
            f"### 🔍 检索反馈\n\n"
            f"很抱歉，我们目前的业务数据库中暂时没有收录与您查询的 **“{keyword}”** 相关的商业分析或画像数据。\n\n"
            f"💡 **推荐您尝试检索以下已收录的行业标杆企业：**\n"
            f"* 🏢 **上海电信**（中国电信股份有限公司上海分公司）\n"
            f"* 🏢 **上海移动**（中国移动通信集团上海有限公司）\n"
            f"* 🏢 **上海联通**（中国联合网络通信有限公司上海市分公司）\n"
            f"* 🏢 **钛度智能**（钛度智能机器人设计与研发中心）\n\n"
            f"*(提示：如需分析更多企业，请确保将数据录入到 MySQL 后台的 5 张业务表中，系统将自动支持检索。)*"
        )
        
        chunk_size = 12
        for i in range(0, len(apology_content), chunk_size):
            yield apology_content[i:i+chunk_size]
            await asyncio.sleep(0.015)
        return

    def render_local_markdown_fallback():
        return (
            f"## 🏢 {company_metadata.get('title', keyword)} 画像分析报告\n\n"
            f"> ⚠️ **提示**：未检测到有效大模型密钥（或 API 调用失败），以下是根据底层数据拼装的原始摘要。\n\n"
            f"🏷️ **公司主属性**：\n"
            f"* **行业类别**：{company_metadata.get('industry', '未知')}\n"
            f"* **信息时效**：{company_metadata.get('publish_date', '最新')}\n"
            f"* **数据来源**：关系型业务数据库（已进行 MySQL 直连 + 高精度内存 BM25 检索与重排）\n\n"
            f"### 📋 数据检索上下文概要\n"
            f"```text\n"
            f"{context[:800]}...\n"
            f"```\n\n"
            f"*[降级处理：请在 .env 中配置有效的 DEEPSEEK_API_KEY 以开启全自动大模型商业报告精细化润色与商机深度剖析。]*"
        )

    if not api_key or "your_api_key" in api_key:
        fallback = render_local_markdown_fallback()
        chunk_size = 12
        for i in range(0, len(fallback), chunk_size):
            yield fallback[i:i+chunk_size]
            await asyncio.sleep(0.015)
        return
        
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        system_instructions = (
            "你是一个顶级的售前顾问和商业大客户经理，擅长将普通的企业基本信息或零散的搜索片段包装成具有深度商业洞察力的客户画像报告。"
        )
        
        prompt = (
            f"请根据以下获取的检索上下文数据，针对 “{keyword}” 这一特定企业主体，精细提炼并编写一份结构完整、措辞专业、排版精美的企业/客户画像分析报告（Markdown 格式）。\n"
            f"请特别分析 “{keyword}” 目前的【核心痛点/挑战】以及针对性的【商业合作契机与建议】（结合痛点给出解决方案思路）。如果上下文包含其他无关企业的资料，请予以忽略，仅聚焦分析 “{keyword}” 本身。\n\n"
            f"【检索上下文信息 ({source_type})】:\n"
            f"{context}\n\n"
            f"排版规范：\n"
            f"1. 多使用加粗、引用块、列表符号，让段落清晰易读。\n"
            f"2. 请在报告尾部单独附带一行来源说明（必须换行并用斜体展示），格式为：\n"
            f"   *数据来源：关系型业务数据库（已进行 MySQL 直连 + 高精度内存 BM25 检索与重排）*\n"
            f"3. 不要添加首尾问候语，直接输出分析报告正文。"
        )
        
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            timeout=15.0,
            stream=True
        )
        
        async for chunk in response:
            delta_content = chunk.choices[0].delta.content
            if delta_content:
                yield delta_content
                
    except Exception as e:
        import traceback
        db.log_event(user_id, "customer", "ERROR", f"客户画像流式分析过程出错: {str(e)}", traceback.format_exc())
        fallback = render_local_markdown_fallback()
        chunk_size = 12
        for i in range(0, len(fallback), chunk_size):
            yield fallback[i:i+chunk_size]
            await asyncio.sleep(0.015)