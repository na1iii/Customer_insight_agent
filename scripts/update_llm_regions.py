# -*- coding: utf-8 -*-
"""
后台大模型行政区划提取脚本
该脚本定期扫描 weixin_deepseek_extract_d 中的增量数据，
使用大模型判断企业实际的所属行政区，并存入 ent_region_llm_cache。
"""
import os
import sys
import time
import json
import asyncio
from openai import AsyncOpenAI
from sqlalchemy import text

def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

load_env_file()

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import db_helper as db

async def update_regions():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")

    if not api_key or "your_api_key" in api_key:
        print("【AI District Worker】未配置 DEEPSEEK_API_KEY，无法使用大模型提取区域。")
        return

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    engine = db.create_db_engine(os.getenv("DATABASE_URL"))
    try:
        # 查找还未被缓存的近期企业记录 (LIMIT 100 避免单词处理过多)
        sql_fetch = text("""
            SELECT a.EntName, LEFT(a.article_content, 1000) as article_content_prefix, a.article_title, a.wechat_name 
            FROM weixin_deepseek_extract_d a
            LEFT JOIN ent_region_llm_cache c ON a.EntName = c.EntName
            WHERE c.District IS NULL 
              AND a.EntName IS NOT NULL AND a.EntName != ''
        ORDER BY a.publish_time DESC
        LIMIT 500
    """)
    
        with engine.connect() as conn:
            res = conn.execute(sql_fetch)
            rows = [dict(zip(res.keys(), r)) for r in res]
        
        if not rows:
            print("【AI District Worker】暂无需要 AI 处理的新企业。")
            return
        
        # Python 层去重，保证同一次批处理中每个企业只调一次大模型
        unique_rows = []
        seen_ents = set()
        for r in rows:
            if r["EntName"] not in seen_ents:
                seen_ents.add(r["EntName"])
                unique_rows.append(r)
            
        print(f"【AI District Worker】找到 {len(unique_rows)} 家独立企业待处理，开始调用 AI...")
    
        # 构建并发请求
        sem = asyncio.Semaphore(10)
    
        async def process_row(row):
            ent_name = row["EntName"]
            title = row["article_title"] or ""
            content = row["article_content_prefix"] or ""
            wechat_name = row.get("wechat_name") or ""
        
            # 1. 优先级最高：基于公众号名称硬规则匹配
            for district in db.DISTRICTS:
                if district in wechat_name or district.replace("区", "") in wechat_name:
                    return {"ent_name": ent_name, "district": district, "reason": f"公众号来源直接判定({wechat_name})"}
        
            # 特殊园区映射
            special_maps = {
                "临港": "浦东新区",
                "张江": "浦东新区",
                "金桥": "浦东新区",
                "外高桥": "浦东新区",
                "浦东": "浦东新区",
                "漕河泾": "徐汇区"
            }
            for key, dist in special_maps.items():
                if key in wechat_name:
                    return {"ent_name": ent_name, "district": dist, "reason": f"公众号特征直接判定({wechat_name} -> {key})"}

            prompt = f"""
    请分析以下关于“{ent_name}”的新闻信息，判断该企业在上海市所属的准确行政区。
    提示：
    - 很多企业总部在一个区，但在其他区有项目（比如“临港集团”属于浦东新区，即使文章提到“临港奉贤园区”也是属于临港新片区/浦东新区主导）。请以企业总部/主导的行政区为准。
    - 如果文章未涉及上海任何区域，或确实无法判断，请返回“其他”。
    - 行政区必须是以下之一：黄浦区、徐汇区、长宁区、静安区、普陀区、虹口区、杨浦区、闵行区、宝山区、嘉定区、浦东新区、金山区、松江区、青浦区、奉贤区、崇明区、其他。

    新闻标题：{title}
    新闻正文(前1000字)：{content}

    请以严格的 JSON 格式返回（不要输出任何其他说明）：
    {{"district": "提取的行政区", "reason": "你的判断理由"}}
    """
            async with sem:
                try:
                    await asyncio.sleep(0.2) # 加入小缓冲防并发限流
                    resp = await client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                        temperature=0.1
                    )
                    res_str = resp.choices[0].message.content
                    res_json = json.loads(res_str)
                    district = res_json.get("district", "其他")
                    if district not in db.DISTRICTS and district != "其他":
                        district = "其他"
                    reason = res_json.get("reason", "")

                    if district == "其他":
                        # 发起二次检索兜底
                        fallback_prompt = f"""
    在之前的新闻分析中无法确定企业“{ent_name}”的所属行政区。现在请你凭借内在知识库，推理并判断该企业总部（或主要经营地）位于上海市的哪个行政区。
    必须严格在以下16个区中选择其一，绝对不允许返回“其他”或“未知”。
    选项：黄浦区、徐汇区、长宁区、静安区、普陀区、虹口区、杨浦区、闵行区、宝山区、嘉定区、浦东新区、金山区、松江区、青浦区、奉贤区、崇明区。

    请以严格的 JSON 格式返回（不要输出任何其他说明）：
    {{"district": "提取的行政区", "reason": "你的判断理由"}}
    """
                        resp_fallback = await client.chat.completions.create(
                            model=model_name,
                            messages=[{"role": "user", "content": fallback_prompt}],
                            response_format={"type": "json_object"},
                            temperature=0.1
                        )
                        # 兼容处理大模型返回的空字符或非合法 JSON
                        content_fallback = (resp_fallback.choices[0].message.content or "").strip()
                        if content_fallback.startswith("```json"):
                            content_fallback = content_fallback[7:-3].strip()
                        if content_fallback:
                            res_json_fallback = json.loads(content_fallback)
                            district = res_json_fallback.get("district", "浦东新区")
                            reason = reason + " | " + res_json_fallback.get("reason", "") + " (AI知识库兜底检索)"
                        else:
                            district = "浦东新区"

                    # 最后的强制物理兜底，确保数据库里绝对没有“其他”
                    if district not in db.DISTRICTS:
                        district = "浦东新区"

                    return {"ent_name": ent_name, "district": district, "reason": reason}
                except Exception as e:
                    print(f"处理 {ent_name} 失败: {e}")
                    return {"ent_name": ent_name, "district": "浦东新区", "reason": f"处理失败强制兜底: {str(e)}"}

        tasks = [process_row(r) for r in unique_rows]
        results = await asyncio.gather(*tasks)
    
        # 存入数据库
        sql_insert = text("""
            INSERT INTO ent_region_llm_cache (EntName, District, reason) 
            VALUES (:ent_name, :district, :reason)
            ON DUPLICATE KEY UPDATE District=VALUES(District), reason=VALUES(reason)
        """)
    
        with engine.connect() as conn:
            for res in results:
                if res:
                    conn.execute(sql_insert, res)
            conn.commit()
            print(f"【AI District Worker】成功缓存 {len(results)} 家企业的 AI 行政区判定。")
    finally:
        await client.close()

async def run_worker():
    print("【AI District Worker】自动归属后台常驻任务已启动...")
    while True:
        try:
            await update_regions()
        except Exception as e:
            print(f"【AI District Worker】执行异常: {e}")
        print("【AI District Worker】本次处理完毕，休息6小时后检查下一批...")
        await asyncio.sleep(6*60*60)

if __name__ == "__main__":
    asyncio.run(run_worker())
