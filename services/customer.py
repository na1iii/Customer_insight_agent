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
from utils.alias_helper import alias_helper

def find_exact_company(keyword: str) -> str:
    """
    检查 keyword 是否能精确匹配（或通过别名映射精确匹配）到系统中的某家企业名称。
    """
    # 1. 优先从 alias_helper 查找
    official_name = alias_helper.alias_to_official.get(keyword)
    if official_name:
        return official_name
    
    # 2. 直连数据库查询精确匹配的企业名称或简称
    try:
        res = db.query_business_db(
            "SELECT `企业名称` FROM ranking_ent_dtl_clue WHERE `企业名称` = :keyword OR `企业简称` = :keyword LIMIT 1",
            {"keyword": keyword}
        )
        if res:
            return res[0].get("企业名称")
    except Exception as e:
        print(f"【find_exact_company Error】 {e}")
    return None

def search_companies_multidim(keyword: str) -> list:
    """
    多维度模糊检索企业，返回匹配到的去重后的企业列表。
    """
    try:
        res = db.query_business_db(
            "SELECT `企业名称` AS EntName, `企业简称` AS EntShortName, `工商行业` AS Industry, `客户区局` AS District, `资质名称` AS Qualification, `客户经理名称` AS Manager "
            "FROM ranking_ent_dtl_clue "
            "WHERE `企业名称` LIKE :kw "
            "OR `企业简称` LIKE :kw "
            "OR `工商行业` LIKE :kw "
            "OR `集团行业一层` LIKE :kw "
            "OR `根营销行业一层` LIKE :kw "
            "OR `资质名称` LIKE :kw "
            "OR `客户区局` LIKE :kw "
            "LIMIT 100",
            {"kw": f"%{keyword}%"}
        )
        
        seen = set()
        unique_companies = []
        for row in res:
            name = (row.get("EntName") or "").strip()
            if not name:
                continue
            if name not in seen:
                seen.add(name)
                short = (row.get("EntShortName") or "").strip()
                if not short and name in alias_helper.official_to_alias:
                    short = alias_helper.official_to_alias[name]
                unique_companies.append({
                    "EntName": name,
                    "EntShortName": short,
                    "Industry": row.get("Industry") or "",
                    "District": row.get("District") or "",
                    "Qualification": row.get("Qualification") or "",
                    "Manager": row.get("Manager") or ""
                })
        return unique_companies
    except Exception as e:
        print(f"【search_companies_multidim Error】 {e}")
        return []

def format_recommendation_table(keyword: str, companies: list) -> str:
    """
    将匹配到的企业列表格式化为 Markdown 推荐表格。
    """
    count = len(companies)
    display_companies = companies[:15]
    
    table_lines = [
        f"### 🔍 多维度客户推荐\n",
        f"根据您输入的关键词 **“{keyword}”**，系统在数据库中匹配到了以下 **{count}** 家相关企业。请问您想要查看哪家企业的精准画像？\n",
        f"| 企业名称 | 行业类别 | 客户区局 | 资质标签 | 对接客户经理 |",
        f"| :--- | :--- | :--- | :--- | :--- |"
    ]
    
    for c in display_companies:
        name = c["EntName"].replace("|", "\\|").strip()
        ind = (c["Industry"] or "暂无").replace("|", "\\|").strip()
        dist = (c["District"] or "暂无").replace("|", "\\|").strip()
        qual = (c["Qualification"] or "暂无").replace("|", "\\|").strip()
        mgr = (c["Manager"] or "暂无").replace("|", "\\|").strip()
        
        table_lines.append(f"| {name} | {ind} | {dist} | {qual} | {mgr} |")
        
    table_lines.append(
        f"\n💡 **提示**：请从列表中复制或输入您感兴趣的**具体企业全称**（例如：`{display_companies[0]['EntName']}`），系统将为您生成详尽的企业画像与商机分析报告。"
    )
    return "\n".join(table_lines)

def handle(keyword: str, user_id: int = None) -> dict:
    """
    处理查询客户画像意图，采用 Advanced RAG + Agentic Web Search
    """
    if not keyword:
        return {
            "type": "text",
            "content": "请问您想分析哪家企业？（例如：上海电信、上海移动等）"
        }

    # 1. 尝试精确匹配企业名称
    exact_name = find_exact_company(keyword)
    if exact_name:
        keyword = exact_name
    else:
        # 模糊推荐企业列表
        companies = search_companies_multidim(keyword)
        if not companies:
            # 返回未收录提示
            apology_content = (
                f"### 🔍 检索反馈\n\n"
                f"很抱歉，我们目前的业务数据库中暂时没有收录与您查询的 **“{keyword}”** 相关的商业分析或画像数据。\n\n"
                f"💡 **推荐您尝试检索以下已收录的行业标杆企业：**\n"
                f"* 🏢 **中国电信股份有限公司上海分公司**\n\n"
                f"*(提示：如需分析更多企业，请确保将数据录入到 MySQL 后台的 5 张业务表中，系统将自动支持检索。)*"
            )
            return {
                "type": "text",
                "content": apology_content
            }
        elif len(companies) == 1:
            # 唯一匹配，自动以该公司名字继续
            keyword = companies[0]["EntName"]
        else:
            # 多个匹配，展示选择表格
            recommend_content = format_recommendation_table(keyword, companies)
            return {
                "type": "text",
                "content": recommend_content
            }
        
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    
    # 从业务数据库中检索企业基础线索、微信文章和项目合作新闻
    db_clue_info = None
    db_snap_info = None
    db_articles = []
    db_cooperations = []
    db_hit = False
    db_documents = []
    
    official_name = alias_helper.alias_to_official.get(keyword, keyword)
    synonym_name = alias_helper.official_to_alias.get(keyword, keyword)
    
    try:
        # A. 检索企业资质及营收属性 (ranking_ent_dtl_clue)
        clue_res = db.query_business_db(
            "SELECT `企业名称` AS EntName, `省份` AS Province, `城市` AS City, "
            "`2024年营业收入（万元）` AS Scale_revenue, `营业收入增长率` AS Growth_rate, "
            "`资质名称` AS Awards_list, `客户经理名称` AS Manager, "
            "`企业注册时间` AS Establish_date, `集团行业一层` AS Industry "
            "FROM ranking_ent_dtl_clue WHERE `企业名称` = :official OR `企业名称` = :synonym OR `企业名称` LIKE :keyword LIMIT 1",
            {"official": official_name, "synonym": synonym_name, "keyword": f"%{keyword}%"}
        )
        if clue_res:
            db_clue_info = clue_res[0]
            
        # 新增：从 sgs_cust_snap 中检索工商基础信息
        snap_res = db.query_business_db(
            "SELECT `legal_representative`, `registered_capital`, `business_scope` "
            "FROM sgs_cust_snap WHERE `business_name` = :official OR `business_name` = :synonym OR `business_name` LIKE :keyword LIMIT 1",
            {"official": official_name, "synonym": synonym_name, "keyword": f"%{keyword}%"}
        )
        if snap_res:
            db_snap_info = snap_res[0]
            
        # B. 检索微信公众号动态与项目合作签约动态 (均从 weixin_deepseek_extract_d 统一获取)
        extract_res = db.query_business_db(
            "SELECT `EntName`, `Abstract`, `Topic`, "
            "`article_title` AS title, `article_content` AS content, `article_url` AS link, "
            "`publish_time` AS date, `wechat_name` AS source "
            "FROM weixin_deepseek_extract_d "
            "WHERE `EntName` = :official OR `EntName` = :synonym OR `EntShortName` = :official OR `EntShortName` = :synonym "
            "OR `EntName` LIKE :keyword OR `EntShortName` LIKE :keyword "
            "OR `article_title` LIKE :keyword OR `article_content` LIKE :keyword "
            "ORDER BY `publish_time` DESC LIMIT 15",
            {"official": official_name, "synonym": synonym_name, "keyword": f"%{keyword}%"}
        )
        
        for a in extract_res:
            db_documents.append({
                "title": a.get("title") or a.get("Topic") or "微信舆情/新闻",
                "content": a.get("content") or a.get("Abstract") or "",
                "publish_date": str(a.get("date") or ""),
                "source": a.get("source") or "微信舆情数据",
                "link": a.get("link") or "",
                "company": keyword
            })
            
        for a in extract_res:
            ent = a.get("EntName", "")
            abst = (a.get("Abstract") or "")[:200]
            topic = a.get("Topic", "")
            title = a.get("title", "")
            content = (a.get("content") or "")[:200]
            link = a.get("link", "")
            date = str(a.get("date") or "")
            source = a.get("source") or ""
            
            db_articles.append(f"【微信舆情动态】企业名称: {ent} | 标题: {title} | 主题: {topic} | 来源: {source} | 发布时间: {date} | 链接: {link} | 摘要: {abst or content}")
            db_cooperations.append(f"【合作签约动态】标题: {title} | 来源: {source} | 日期: {date} | 摘要: {content}")
            
        if db_clue_info or db_documents or db_snap_info:
            db_hit = True
    except Exception as db_err:
        db.log_event(user_id, "customer", "ERROR", f"直连 MySQL 检索企业多源数据失败: {db_err}")

    retrieved_docs = []
    is_hit = False
    
    if db_documents:
        rag = RAGEngine(documents=db_documents)
        retrieved_docs = rag.retrieve(keyword, top_k=3)
        
        if api_key and "your_api_key" not in api_key:
            retrieved_docs = rag.rerank(keyword, retrieved_docs, api_key, base_url, model_name)
        else:
            for doc in retrieved_docs:
                doc["rerank_score"] = doc.get("final_score", 0.0)
                
    # 筛选所有匹配分 > 0.20 且最多前 3 篇深度文章进行聚合
    valid_docs = [doc for doc in retrieved_docs if doc.get("rerank_score", 0.0) > 0.20]
    if valid_docs:
        is_hit = True
        valid_docs = valid_docs[:3]

    source_type = "mysql_structured_query"
    context = ""
    company_metadata = {}
    
    db_context_pieces = []
    ent_name = keyword
    if db_clue_info:
        ent_name = db_clue_info.get("EntName", keyword)
        
    legal_rep = db_snap_info.get("legal_representative") or "暂无" if db_snap_info else "暂无"
    reg_capital = db_snap_info.get("registered_capital") or "暂无" if db_snap_info else "暂无"
    biz_scope = db_snap_info.get("business_scope") or "暂无" if db_snap_info else "暂无"

    if db_clue_info:
        prov = db_clue_info.get("Province", "")
        city = db_clue_info.get("City", "")
        scale = db_clue_info.get("Scale_revenue", "")
        growth = db_clue_info.get("Growth_rate", "")
        awards = db_clue_info.get("Awards_list", "")
        manager = db_clue_info.get("Manager", "")
        establish_date = db_clue_info.get("Establish_date", "")
        industry = db_clue_info.get("Industry", "")
        db_context_pieces.append(
            f"【企业基础资质与财务属性】:\n"
            f"企业名称: {ent_name}\n"
            f"行政归属: {prov}{city}\n"
            f"营收规模: {scale}\n"
            f"营业收入增长率: {growth}\n"
            f"所获榜单资质: {awards}\n"
            f"对接客户经理: {manager}\n"
            f"成立日期: {establish_date}\n"
            f"所属行业: {industry}\n"
            f"法定代表人: {legal_rep}\n"
            f"注册资本: {reg_capital}\n"
            f"主营范围: {biz_scope}"
        )
    elif db_snap_info:
        db_context_pieces.append(
            f"【企业基础工商属性】:\n"
            f"企业名称: {ent_name}\n"
            f"法定代表人: {legal_rep}\n"
            f"注册资本: {reg_capital}\n"
            f"主营范围: {biz_scope}"
        )
    db_context_str = "\n\n".join(db_context_pieces)

    if is_hit and valid_docs:
        best_doc = valid_docs[0]
        msg = f"关系型数据库 RAG 检索成功命中 {len(valid_docs)} 篇深度文章/新闻 (首篇评分: {best_doc.get('rerank_score', 0.0):.4f})"
        db.log_event(user_id, "customer", "INFO", msg)
        
        context_pieces = []
        for idx, doc in enumerate(valid_docs):
            context_pieces.append(
                f"【深度舆情/新闻文章片段 {idx + 1}】:\n"
                f"标题: {doc['metadata']['title']}\n"
                f"发布日期: {doc['metadata']['publish_date']}\n"
                f"数据源: {doc['metadata']['source']}\n"
                f"内容:\n{doc['parent_content']}"
            )
        context = "\n\n".join(context_pieces)
        
        if db_context_pieces:
            context += "\n\n" + db_context_str
        source_type = "mysql_db_bm25_rag"
        company_metadata = best_doc["metadata"]
    elif db_hit:
        msg = f"未匹配到相关的深度文章/新闻，但已匹配到 '{keyword}' 的企业基础信息，执行数据库基础画像。"
        db.log_event(user_id, "customer", "INFO", msg)
        is_hit = True
        context = db_context_str
        
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
            f"* 🏢 **中国电信股份有限公司上海分公司**\n\n"
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
            f"* **数据来源**：关系型业务数据库（已进行 MySQL 直连 + 高精度内存 BM25 检索与重排）\n\n"
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
        
        system_instructions = (
            "你是一个顶级的售前顾问和商业大客户经理，擅长将普通的企业基本信息或零散的搜索片段包装成具有深度商业洞察力的客户画像报告。"
        )
        
        prompt = (
            f"请根据以下获取的检索上下文数据，针对 “{keyword}” 这一特定企业主体，精细提炼并编写一份结构完整、措辞专业、排版精美的企业/客户画像分析报告（Markdown 格式）。\n"
            f"如果上下文包含其他无关企业的资料，请予以忽略，仅聚焦分析 “{keyword}” 本身。\n\n"
            f"【检索上下文信息 ({source_type})】:\n"
            f"{context}\n\n"
            f"报告必须严格按照以下结构输出，且不得包含任何多余的开场白、问候语或首尾总结词：\n"
            f"1. **一、企业概括**：展示企业基本属性。必须以标准的 Markdown 表格形式展示（表头为：| 维度 | 内容 |）。包含的维度必须且仅有：企业名称、法定代表人、注册资本、企业规模、成立日期、行业、主营范围、核心资质（注意：绝对不要包含“对接客户经理”）。如果上下文数据中没有提供某些属性，请结合你检索到的上下文和你的知识库补充或显示“本次检索未提供”。\n"
            f"2. **二、近期舆情动态**：按时间倒序展现近期该企业的舆情线索与新闻（如果有多条，必须且最多只显示最新的前五条）。每一条动态需包含：发布日期、主题/标题、数据源、内容摘要。\n"
            f"3. **三、与上海电信参与合作的内容**：请深度挖掘作为上海电信（运营商与数字化使能者），在面对该企业时可以与其参与和开展的合作内容（结合其行业属性、痛点和近期动态，从算力网络、5G-A、云网融合、工业互联网或安全交付等方面给出针对性的合作契机与方案）。\n"
            f"4. **四、总结**：针对上述企业概况、舆情及合作内容做一小段精炼的简要总结。\n\n"
            f"排版规范：\n"
            f"1. 第一部分必须且只能以 Markdown 表格呈现，多使用加粗、引用块、列表符号让后续部分清晰易读。\n"
            f"2. 请在报告尾部单独附带一行来源说明（必须换行并用斜体展示），格式为：\n"
            f"   *数据来源：关系型业务数据库（已进行 MySQL 直连 + 高精度内存 BM25 检索与重排）*\n"
            f"3. 不要添加首尾问候语，直接输出报告正文。"
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
        
    # 1. 尝试精确匹配企业名称 (在线程池中运行数据库)
    def check_exact_sync():
        return find_exact_company(keyword)
    
    exact_name = await asyncio.to_thread(check_exact_sync)
    if exact_name:
        keyword = exact_name
    else:
        # 模糊推荐企业列表
        def search_companies_sync():
            return search_companies_multidim(keyword)
        
        companies = await asyncio.to_thread(search_companies_sync)
        if not companies:
            apology_content = (
                f"### 🔍 检索反馈\n\n"
                f"很抱歉，我们目前的业务数据库中暂时没有收录与您查询的 **“{keyword}”** 相关的商业分析或画像数据。\n\n"
                f"💡 **推荐您尝试检索以下已收录的行业标杆企业：**\n"
                f"* 🏢 **中国电信股份有限公司上海分公司**\n\n"
                f"*(提示：如需分析更多企业，请确保将数据录入到 MySQL 后台的 5 张业务表中，系统将自动支持检索。)*"
            )
            chunk_size = 12
            for i in range(0, len(apology_content), chunk_size):
                yield apology_content[i:i+chunk_size]
                await asyncio.sleep(0.015)
            return
        elif len(companies) == 1:
            keyword = companies[0]["EntName"]
        else:
            recommend_content = format_recommendation_table(keyword, companies)
            chunk_size = 12
            for i in range(0, len(recommend_content), chunk_size):
                yield recommend_content[i:i+chunk_size]
                await asyncio.sleep(0.015)
            return

    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    
    # 再次根据最终确定的 keyword 映射 official 和 synonym 名
    official_name = alias_helper.alias_to_official.get(keyword, keyword)
    synonym_name = alias_helper.official_to_alias.get(keyword, keyword)
    
    # 2. 从业务数据库中检索企业基础线索、微信文章和项目合作新闻
    db_clue_info = None
    db_snap_info = None
    db_articles = []
    db_cooperations = []
    db_hit = False
    db_documents = []
    
    # 在线程池中执行关系数据库查询，避免阻塞事件循环
    def query_db_sync():
        nonlocal db_clue_info, db_snap_info, db_hit
        try:
            clue_res = db.query_business_db(
                "SELECT `企业名称` AS EntName, `省份` AS Province, `城市` AS City, "
                "`2024年营业收入（万元）` AS Scale_revenue, `营业收入增长率` AS Growth_rate, "
                "`资质名称` AS Awards_list, `客户经理名称` AS Manager, "
                "`企业注册时间` AS Establish_date, `集团行业一层` AS Industry "
                "FROM ranking_ent_dtl_clue WHERE `企业名称` = :official OR `企业名称` = :synonym OR `企业名称` LIKE :keyword LIMIT 1",
                {"official": official_name, "synonym": synonym_name, "keyword": f"%{keyword}%"}
            )
            if clue_res:
                db_clue_info = clue_res[0]
                
            # 新增：从 sgs_cust_snap 中检索工商基础信息
            snap_res = db.query_business_db(
                "SELECT `legal_representative`, `registered_capital`, `business_scope` "
                "FROM sgs_cust_snap WHERE `business_name` = :official OR `business_name` = :synonym OR `business_name` LIKE :keyword LIMIT 1",
                {"official": official_name, "synonym": synonym_name, "keyword": f"%{keyword}%"}
            )
            if snap_res:
                db_snap_info = snap_res[0]
                
            # 检索微信公众号动态与项目合作签约动态 (均从 weixin_deepseek_extract_d 统一获取)
            extract_res = db.query_business_db(
                "SELECT `EntName`, `Abstract`, `Topic`, "
                "`article_title` AS title, `article_content` AS content, `article_url` AS link, "
                "`publish_time` AS date, `wechat_name` AS source "
                "FROM weixin_deepseek_extract_d "
                "WHERE `EntName` = :official OR `EntName` = :synonym OR `EntShortName` = :official OR `EntShortName` = :synonym "
                "OR `EntName` LIKE :keyword OR `EntShortName` LIKE :keyword "
                "OR `article_title` LIKE :keyword OR `article_content` LIKE :keyword "
                "ORDER BY `publish_time` DESC LIMIT 15",
                {"official": official_name, "synonym": synonym_name, "keyword": f"%{keyword}%"}
            )
            
            for a in extract_res:
                db_documents.append({
                    "title": a.get("title") or a.get("Topic") or "微信舆情/新闻",
                    "content": a.get("content") or a.get("Abstract") or "",
                    "publish_date": str(a.get("date") or ""),
                    "source": a.get("source") or "微信舆情数据",
                    "link": a.get("link") or "",
                    "company": keyword
                })
                
            for a in extract_res:
                ent = a.get("EntName", "")
                abst = (a.get("Abstract") or "")[:200]
                topic = a.get("Topic", "")
                title = a.get("title", "")
                content = (a.get("content") or "")[:200]
                link = a.get("link", "")
                date = str(a.get("date") or "")
                source = a.get("source") or ""
                
                db_articles.append(f"【微信舆情动态】企业名称: {ent} | 标题: {title} | 主题: {topic} | 来源: {source} | 发布时间: {date} | 链接: {link} | 摘要: {abst or content}")
                db_cooperations.append(f"【合作签约动态】标题: {title} | 来源: {source} | 日期: {date} | 摘要: {content}")
                
            if db_clue_info or db_documents or db_snap_info:
                db_hit = True
        except Exception as db_err:
            db.log_event(user_id, "customer", "ERROR", f"直连 MySQL 检索企业多源数据失败: {db_err}")

    await asyncio.to_thread(query_db_sync)

    # 3. 对从数据库加载的文本记录，在内存中初始化 RAG 引擎，并执行 BM25 检索与大模型重排
    retrieved_docs = []
    is_hit = False
    
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
        retrieved_docs = await asyncio.to_thread(run_rag_retrieve_and_rerank)
    except Exception as e:
        import traceback
        db.log_event(user_id, "customer", "ERROR", f"RAG检索/重排过程出错: {str(e)}", traceback.format_exc())
        retrieved_docs = []
        
    # 筛选所有匹配分 > 0.20 且最多前 3 篇深度文章进行聚合
    valid_docs = [doc for doc in retrieved_docs if doc.get("rerank_score", 0.0) > 0.20]
    if valid_docs:
        is_hit = True
        valid_docs = valid_docs[:3]

    # 4. 融合与状态处理
    source_type = "mysql_structured_query"
    context = ""
    company_metadata = {}
    
    db_context_pieces = []
    ent_name = keyword
    if db_clue_info:
        ent_name = db_clue_info.get("EntName", keyword)
        
    legal_rep = db_snap_info.get("legal_representative") or "暂无" if db_snap_info else "暂无"
    reg_capital = db_snap_info.get("registered_capital") or "暂无" if db_snap_info else "暂无"
    biz_scope = db_snap_info.get("business_scope") or "暂无" if db_snap_info else "暂无"

    if db_clue_info:
        prov = db_clue_info.get("Province", "")
        city = db_clue_info.get("City", "")
        scale = db_clue_info.get("Scale_revenue", "")
        growth = db_clue_info.get("Growth_rate", "")
        awards = db_clue_info.get("Awards_list", "")
        manager = db_clue_info.get("Manager", "")
        establish_date = db_clue_info.get("Establish_date", "")
        industry = db_clue_info.get("Industry", "")
        db_context_pieces.append(
            f"【企业基础资质与财务属性】:\n"
            f"企业名称: {ent_name}\n"
            f"行政归属: {prov}{city}\n"
            f"营收规模: {scale}\n"
            f"营业收入增长率: {growth}\n"
            f"所获榜单资质: {awards}\n"
            f"对接客户经理: {manager}\n"
            f"成立日期: {establish_date}\n"
            f"所属行业: {industry}\n"
            f"法定代表人: {legal_rep}\n"
            f"注册资本: {reg_capital}\n"
            f"主营范围: {biz_scope}"
        )
    elif db_snap_info:
        db_context_pieces.append(
            f"【企业基础工商属性】:\n"
            f"企业名称: {ent_name}\n"
            f"法定代表人: {legal_rep}\n"
            f"注册资本: {reg_capital}\n"
            f"主营范围: {biz_scope}"
        )
    db_context_str = "\n\n".join(db_context_pieces)

    if is_hit and valid_docs:
        best_doc = valid_docs[0]
        msg = f"关系型数据库 RAG 检索成功命中 {len(valid_docs)} 篇深度文章/新闻 (首篇评分: {best_doc.get('rerank_score', 0.0):.4f})"
        db.log_event(user_id, "customer", "INFO", msg)
        
        context_pieces = []
        for idx, doc in enumerate(valid_docs):
            context_pieces.append(
                f"【深度舆情/新闻文章片段 {idx + 1}】:\n"
                f"标题: {doc['metadata']['title']}\n"
                f"发布日期: {doc['metadata']['publish_date']}\n"
                f"数据源: {doc['metadata']['source']}\n"
                f"内容:\n{doc['parent_content']}"
            )
        context = "\n\n".join(context_pieces)
        
        if db_context_pieces:
            context += "\n\n" + db_context_str
        source_type = "mysql_db_bm25_rag"
        company_metadata = best_doc["metadata"]
    elif db_hit:
        msg = f"未匹配到相关的深度文章/新闻，但已匹配到 '{keyword}' 的企业基础信息，执行数据库基础画像。"
        db.log_event(user_id, "customer", "INFO", msg)
        is_hit = True
        context = db_context_str
        
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
            f"* 🏢 **中国电信股份有限公司上海分公司**\n\n"
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
            f"如果上下文包含其他无关企业的资料，请予以忽略，仅聚焦分析 “{keyword}” 本身。\n\n"
            f"【检索上下文信息 ({source_type})】:\n"
            f"{context}\n\n"
            f"报告必须严格按照以下结构输出，且不得包含任何多余的开场白、问候语或首尾总结词：\n"
            f"1. **一、企业概括**：展示企业基本属性。必须以标准的 Markdown 表格形式展示（表头为：| 维度 | 内容 |）。包含的维度必须且仅有：企业名称、法定代表人、注册资本、企业规模、成立日期、行业、主营范围、核心资质（注意：绝对不要包含“对接客户经理”）。如果上下文数据中没有提供某些属性，请结合你检索到的上下文 and 你的知识库补充或显示“本次检索未提供”。\n"
            f"2. **二、近期舆情动态**：按时间倒序展现近期该企业的舆情线索与新闻（如果有多条，必须且最多只显示最新的前五条）。每一条动态需包含：发布日期、主题/标题、数据源、内容摘要。\n"
            f"3. **三、与上海电信参与合作的内容**：请深度挖掘作为上海电信（运营商与数字化使能者），在面对该企业时可以与其参与和开展的合作内容（结合其行业属性、痛点和近期动态，从算力网络、5G-A、云网融合、工业互联网或安全交付等方面给出针对性的合作契机与方案）。\n"
            f"4. **四、总结**：针对上述企业概况、舆情及合作内容做一小段精炼的简要总结。\n\n"
            f"排版规范：\n"
            f"1. 第一部分必须且只能以 Markdown 表格呈现，多使用加粗、引用块、列表符号让后续部分清晰易读。\n"
            f"2. 请在报告尾部单独附带一行来源说明（必须换行并用斜体展示），格式为：\n"
            f"   *数据来源：关系型业务数据库（已进行 MySQL 直连 + 高精度内存 BM25 检索与重排）*\n"
            f"3. 不要添加首尾问候语，直接输出报告正文。"
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