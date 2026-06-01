# -*- coding: utf-8 -*-
"""
app.py - FastAPI 核心网关与服务端主入口
"""

import os
import sys
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import asyncio
import json
from pydantic import BaseModel
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

# 手动载入环境变量的轻量级函数（不依赖 python-dotenv）
def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()
        print("【System】成功从本地 .env 文件加载环境变量。")
    else:
        print("【System】未找到 .env 文件，使用系统默认环境变量。")

# 1. 载入环境变量
load_env_file()

# 将根目录添加到 sys.path 中以支持相对导入
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入业务处理模块
# 导入业务处理模块
from router import get_intent_router
import services.customer as customer
import services.regional as regional
import services.industry as industry
import services.potential as potential
import services.general_chat as general_chat
import utils.db_helper as db

@asynccontextmanager
async def lifespan(app: FastAPI):
    def init_db():
        session = db.SessionLocal()
        try:
            latest = session.query(db.OpportunityArticle).order_by(db.OpportunityArticle.updated_at.desc()).first()
            needs_rebuild = False
            if not latest:
                print("【System】商机库为空，开始后台静默执行商机数据库梳理...")
                needs_rebuild = True
            elif datetime.utcnow() - latest.updated_at > timedelta(hours=24):
                print("【System】商机库数据已过期（>24小时），开始后台静默执行商机数据库梳理...")
                needs_rebuild = True
            else:
                print("【System】商机库数据是最新的，跳过自动梳理。")
            
            if needs_rebuild:
                db.rebuild_opportunity_articles(limit=50000, clear_existing=False)
                print("【System】后台商机数据库梳理完成！")
        except Exception as e:
            print(f"【System】商机数据库梳理发生错误: {e}")
        finally:
            session.close()

    # 在独立的后台线程中执行，不阻塞主线程启动
    asyncio.get_event_loop().run_in_executor(None, init_db)
    yield

app = FastAPI(title="AI 客户智能洞察智能体 API", lifespan=lifespan)

# 2. 挂载静态文件目录，提供长图、HTML/Excel 文件的本地 HTTP 访问
static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if not os.path.exists(static_path):
    os.makedirs(static_path, exist_ok=True)
    
app.mount("/static", StaticFiles(directory=static_path), name="static")

# 3. 定义请求和响应模型
class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class UpdateTitleRequest(BaseModel):
    title: str

class ChatRequest(BaseModel):
    message: str
    scene: str
    conversation_id: str
    user_id: int

# 4. 用户鉴权接口
@app.post("/api/auth/register")
async def register_endpoint(req: RegisterRequest):
    res = db.register_user(req.username, req.password)
    if res["status"] == "error":
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@app.post("/api/auth/login")
async def login_endpoint(req: LoginRequest):
    res = db.verify_user(req.username, req.password)
    if res["status"] == "error":
        raise HTTPException(status_code=400, detail=res["message"])
    return res

# 5. 会话历史记录管理接口
@app.get("/api/conversations")
async def get_conversations_endpoint(user_id: int, scene: str):
    return db.get_conversations(user_id, scene)

@app.post("/api/conversations")
async def create_conversation_endpoint(user_id: int, scene: str, title: str):
    res = db.create_conversation(user_id, scene, title)
    if res["status"] == "error":
        raise HTTPException(status_code=500, detail=res["message"])
    return res

@app.get("/api/conversations/{conv_id}")
async def get_messages_endpoint(conv_id: str):
    return db.get_messages(conv_id)

@app.delete("/api/conversations/{conv_id}")
async def delete_conversation_endpoint(user_id: int, conv_id: str):
    success = db.delete_conversation(user_id, conv_id)
    if not success:
        raise HTTPException(status_code=400, detail="会话不存在或删除失败")
    return {"status": "success"}

@app.put("/api/conversations/{conv_id}")
async def update_conversation_title_endpoint(conv_id: str, req: UpdateTitleRequest):
    success = db.update_conversation_title(conv_id, req.title)
    if not success:
        raise HTTPException(status_code=400, detail="会话不存在或更新失败")
    return {"status": "success"}

# 6. 系统运行日志查询接口
@app.get("/api/system/logs")
async def get_system_logs_endpoint():
    return db.get_logs()

# 7. 路由与分流场景对话主接口 (流式返回)
async def chat_generator(user_text: str, scene: str, conv_id: str, user_id: int):
    resolved_scene = scene
    try:
        # A. 保存用户输入的消息到数据库
        db.save_message(conv_id, "user", user_text)
        
        # 立即发送初始状态，避免前端长时间等待
        yield f"data: {json.dumps({'type': 'router_start'}, ensure_ascii=False)}\n\n"
        
        # B. AI 路由器提取实体与意图 (在线程池中执行以防止阻塞事件循环)
        history = db.get_messages(conv_id)
        
        def run_router():
            return get_intent_router(user_text, chat_history=history)
            
        command = await asyncio.to_thread(run_router)
        keyword = command.keyword if command.keyword else user_text
        
        # 智能分流路由映射
        if scene in ("general", "all", ""):
            intent = command.intent
            if intent == "query_customer":
                resolved_scene = "customer"
            elif intent == "regional_report":
                resolved_scene = "regional"
            elif intent == "industry_report":
                resolved_scene = "industry"
            elif intent == "high_potential":
                resolved_scene = "potential"
            elif intent == "general_chat":
                resolved_scene = "general_chat"
            else:
                resolved_scene = "general_chat"
        
        # 拦截：如果 keyword 是预设的提示语，将其置空，以便触发各服务的反问逻辑
        if keyword in ["我想看一家企业的精准画像", "我想生成一份区域经济报告", "我想查看行业发展趋势报告", "我想找一些高潜客户线索"]:
            keyword = ""
            
        # 修复：如果是反问实体的状态（即 keyword 为空），不需要在前台展示耗时的进度卡片
        display_scene = resolved_scene
        if not keyword and resolved_scene in ["customer", "regional", "industry", "potential"]:
            display_scene = "general_chat"
            
        # 发送意图解析首包
        yield f"data: {json.dumps({'type': 'info', 'resolved_scene': display_scene}, ensure_ascii=False)}\n\n"
        
        # C. 记录系统事件日志
        db.log_event(user_id, resolved_scene, "INFO", f"接收到提问，RAG实体提取: '{keyword}'，解析意图场景: '{resolved_scene}'")
        
        msg_content = ""
        data_payload = None
        
        if resolved_scene == "customer":
            # 企业画像流式输出
            async for chunk in customer.handle_stream(keyword, user_id=user_id):
                msg_content += chunk
                yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"
            
            db.log_event(user_id, resolved_scene, "INFO", f"画像查询成功，已流式输出 Markdown 报告。")
            
        elif resolved_scene == "general_chat":
            # 通用问答流式输出
            async for chunk in general_chat.handle_stream(user_text, user_id=user_id, history=history):
                msg_content += chunk
                yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"
                
            db.log_event(user_id, resolved_scene, "INFO", f"通用对话查询成功，已流式输出解答。")
            
        else:
            # 其它场景 (regional, industry, potential) 的处理
            # 1. 异步线程调用对应的同步处理器
            def run_sync_handler():
                if resolved_scene == "regional":
                    return regional.handle(keyword, user_id=user_id)
                elif resolved_scene == "industry":
                    return industry.handle(keyword, user_id=user_id)
                elif resolved_scene == "potential":
                    return potential.handle(keyword, user_id=user_id)
                else:
                    return customer.handle(keyword, user_id=user_id)
                    
            res = await asyncio.to_thread(run_sync_handler)
            data_payload = res
            
            # 2. 组装引导文字
            if res.get("type") == "html_link":
                guide_text = f"已成功为您生成 **{res.get('region_name', '')}** 经济运行分析报告网页，请点击下方卡片打开网页查看："
                db.log_event(user_id, resolved_scene, "INFO", f"区域分析报告网页生成成功: {res.get('url')}")
            elif res.get("type") == "regional_report":
                guide_text = res.get("summary") or f"已为您生成 **{res.get('district', '')}** 商机分析，请点击下方按钮查看明细。"
                db.log_event(user_id, resolved_scene, "INFO", f"区域商机报告生成成功: {res.get('district')}")
            elif res.get("type") == "file_link":
                guide_text = f"已成功为您编译生成行业研究报告：《{res.get('title', '')}》。"
                db.log_event(user_id, resolved_scene, "INFO", f"行业 HTML 报告生成并完成推送: {res.get('url')}")
            elif res.get("type") == "high_potential_customers":
                guide_text = res.get("summary") or f"已为您筛选出 {res.get('count', 0)} 家高潜客户。"
                db.log_event(user_id, resolved_scene, "INFO", f"高潜客户推荐卡片生成成功，数量: {res.get('count')}")
            elif res.get("type") == "table":
                guide_text = f"已为您筛选出与关键词最匹配的 {res.get('count', 0)} 家高潜客户列表，点击下方表格链接可直达详情，同时支持导出 Excel："
                db.log_event(user_id, resolved_scene, "INFO", f"高潜客户推荐表格编译成功，数量: {res.get('count')}")
            else:
                guide_text = res.get("content", "")
                data_payload = None
                
            # 3. 模拟打字机输出引导文字
            chunk_size = 12
            for i in range(0, len(guide_text), chunk_size):
                chunk = guide_text[i:i+chunk_size]
                msg_content += chunk
                yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.015)
                
            # 4. 推送 payload 数据包
            if data_payload:
                yield f"data: {json.dumps({'type': 'payload', 'payload': data_payload}, ensure_ascii=False)}\n\n"
                
        # F. 保存助手生成的应答消息到数据库并发送结束标志包
        saved_msg = db.save_message(conv_id, "assistant", msg_content, data_payload)
        yield f"data: {json.dumps({'type': 'done', 'message_id': saved_msg['id']}, ensure_ascii=False)}\n\n"
        
    except Exception as e:
        import traceback
        try:
            traceback.print_exc()
        except Exception:
            pass
        err_scene = resolved_scene if 'resolved_scene' in locals() else scene
        try:
            db.log_event(user_id, err_scene, "ERROR", f"流式服务处理异常: {str(e)}", traceback.format_exc())
        except Exception:
            pass
        # 推送错误信息包
        yield f"data: {json.dumps({'type': 'error', 'message': f'服务处理异常: {str(e)}'}, ensure_ascii=False)}\n\n"

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    user_text = request.message.strip()
    scene = request.scene.strip()
    conv_id = request.conversation_id.strip()
    user_id = request.user_id
    
    if not user_text:
        raise HTTPException(status_code=400, detail="输入内容不能为空")
    if not conv_id:
        raise HTTPException(status_code=400, detail="会话 ID 不能为空")
        
    return StreamingResponse(
        chat_generator(user_text, scene, conv_id, user_id),
        media_type="text/event-stream"
    )

# 7.5. 公众号商机文章及高潜 Excel 导出路由
@app.get("/api/articles")
async def get_articles_endpoint(district: Optional[str] = None):
    return db.get_articles(district=district)

@app.post("/api/articles/rebuild")
async def rebuild_articles_endpoint(
    district: Optional[str] = None,
    limit: int = 500,
    clear_existing: bool = True,
):
    """
    手动刷新商机预计算结果表。
    """
    try:
        safe_limit = max(1, min(limit, 2000))
        return await asyncio.wait_for(
            asyncio.to_thread(
                db.rebuild_opportunity_articles,
                district=district,
                limit=safe_limit,
                clear_existing=clear_existing,
            ),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="商机预计算刷新超过 120 秒，请降低 limit 或按区县分批刷新。")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"商机预计算刷新失败: {str(e)}")

@app.get("/api/potential/export")
async def export_potential_endpoint(
    district: Optional[str] = None,
    industry: Optional[str] = None,
    keyword: Optional[str] = None,
    score_min: int = 55,
    user_id: Optional[int] = None,
):
    try:
        excel_path = potential.export_excel(
            district=district,
            industry=industry,
            keyword=keyword,
            score_min=score_min,
            user_id=user_id,
        )
        filename = os.path.basename(excel_path)
        return FileResponse(
            excel_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.log_event(user_id, "potential", "ERROR", f"高潜客户 Excel 导出失败: {str(e)}", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"高潜客户 Excel 导出失败: {str(e)}")

@app.get("/ui_1.html")
async def get_regional_opportunity_page():
    ui_html = os.path.join(static_path, "ui_1.html")
    if os.path.exists(ui_html):
        return FileResponse(ui_html)
    raise HTTPException(status_code=404, detail="区域商机明细页未找到")

# 8. 默认主页跳转
@app.get("/")
async def get_index():
    index_html = os.path.join(static_path, "index.html")
    if os.path.exists(index_html):
        return FileResponse(index_html)
    raise HTTPException(status_code=404, detail="静态 index.html 主页面未找到")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
