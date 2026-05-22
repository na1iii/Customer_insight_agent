# -*- coding: utf-8 -*-
"""
app.py - FastAPI 核心网关与服务端主入口
"""

import os
import sys
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
import utils.db_helper as db

app = FastAPI(title="AI 客户智能洞察智能体 API")

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

# 6. 系统运行日志查询接口
@app.get("/api/system/logs")
async def get_system_logs_endpoint():
    return db.get_logs()

# 7. 路由与分流场景对话主接口
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
        
    try:
        # A. 保存用户输入的消息到数据库
        db.save_message(conv_id, "user", user_text)
        
        # B. AI 路由器提取实体
        command = get_intent_router(user_text)
        keyword = command.keyword if command.keyword else user_text
        
        # C. 记录系统事件日志
        db.log_event(user_id, scene, "INFO", f"接收到提问，RAG实体提取: '{keyword}'")
        
        # D. 执行具体场景服务逻辑
        res = None
        if scene == "customer":
            res = customer.handle(keyword, user_id=user_id)
        elif scene == "regional":
            res = regional.handle(keyword, user_id=user_id)
        elif scene == "industry":
            res = industry.handle(keyword, user_id=user_id)
        elif scene == "potential":
            res = potential.handle(keyword, user_id=user_id)
        else:
            res = customer.handle(keyword, user_id=user_id)
            
        # E. 组装标准消息文本和卡片数据负载 (data_payload)
        msg_content = ""
        data_payload = res
        
        if res.get("type") == "text":
            msg_content = res.get("content", "")
            data_payload = None
            db.log_event(user_id, scene, "INFO", f"画像查询成功，已通过大模型/模板生成 Markdown 报告。")
        elif res.get("type") == "html_link":
            msg_content = f"已成功为您生成 **{res.get('region_name', '')}** 经济运行分析报告网页，请点击下方卡片打开网页查看："
            db.log_event(user_id, scene, "INFO", f"区域分析报告网页生成成功: {res.get('url')}")
        elif res.get("type") == "file_link":
            msg_content = f"已成功为您编译生成行业研究报告：《{res.get('title', '')}》。我们已通过 Webhook 将其推送到了群聊机器人中。"
            db.log_event(user_id, scene, "INFO", f"行业 HTML 报告生成并完成推送: {res.get('url')}")
        elif res.get("type") == "table":
            msg_content = f"已为您筛选出与关键词最匹配的 {res.get('count', 0)} 家高潜客户列表，点击下方表格链接可直达详情，同时支持导出 Excel："
            db.log_event(user_id, scene, "INFO", f"高潜客户推荐表格编译成功，数量: {res.get('count')}")
            
        # F. 保存助手生成的应答消息到数据库
        saved_msg = db.save_message(conv_id, "assistant", msg_content, data_payload)
        
        return saved_msg
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.log_event(user_id, scene, "ERROR", f"服务处理异常: {str(e)}", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"服务处理异常: {str(e)}")

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
