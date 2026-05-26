# -*- coding: utf-8 -*-
"""
db_helper.py - 数据库管理层，提供 SQLAlchemy 初始化、用户鉴权、会话历史管理以及系统日志落库逻辑。
支持直连配置的目标关系型数据库并进行严格初始化校验。
"""

import os
import hashlib
import uuid
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. 动态加载连接配置
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise ValueError("环境变量 DATABASE_URL 未配置，无法连接数据库！")

# 打印安全地址提示 (隐藏密码)
safe_url = DATABASE_URL
if "@" in DATABASE_URL:
    safe_url = DATABASE_URL.split("@")[-1]
print(f"【Database Connection】正在初始化数据库链接: {safe_url}")

# 创建连接引擎
def create_db_engine(url):
    engine_kwargs = {}
    if "sqlite" not in url:
        engine_kwargs = {
            "pool_recycle": 3600,
            "pool_pre_ping": True,
            "pool_size": 10,
            "max_overflow": 20
        }
    else:
        engine_kwargs = {
            "connect_args": {"check_same_thread": False}
        }
    return create_engine(url, **engine_kwargs)

engine = create_db_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. 数据库模型定义
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String(100), primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    scene = Column(String(100), nullable=False)  # "customer", "regional", "industry", "potential"
    created_at = Column(DateTime, default=datetime.utcnow)

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(100), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False)  # "user", "assistant"
    content = Column(Text, nullable=False)
    data_payload = Column(Text, nullable=True)  # 存储长图/PDF/表格的 JSON 数据包
    created_at = Column(DateTime, default=datetime.utcnow)

class SystemLog(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    scene = Column(String(100), nullable=True)
    level = Column(String(50), nullable=False)  # "INFO", "WARNING", "ERROR"
    message = Column(String(500), nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

# 自动建表与验证
try:
    # 尝试建表 (在生产/受限环境可能没有 CREATE 权限)
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as create_err:
        print(f"【Database Warning】尝试自动建表失败 (可能无建表权限，如只读或受限账号): {create_err}")
        
    # 额外测试表的可访问性
    with engine.connect() as conn:
        conn.execute(text("SELECT 1 FROM users LIMIT 1"))
    print("【Database Initialized】数据库表结构验证与初始化成功。")
except Exception as e:
    print(f"【Database Error】数据库初始化或表验证失败 (表可能不存在，或无读取权限): {e}")
    raise e

# 3. 业务管理 API 函数

def hash_password(password: str) -> str:
    """对密码进行 SHA-256 加密保存"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def register_user(username: str, password: str) -> dict:
    """注册用户"""
    db = SessionLocal()
    try:
        username = username.strip()
        if not username or not password:
            return {"status": "error", "message": "用户名和密码不能为空"}
        
        # 判断重名
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            return {"status": "error", "message": "该用户名已存在"}
            
        hashed = hash_password(password)
        new_user = User(username=username, password=hashed)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"status": "success", "user": {"id": new_user.id, "username": new_user.username}}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": f"注册失败: {str(e)}"}
    finally:
        db.close()

def verify_user(username: str, password: str) -> dict:
    """校验用户登录"""
    db = SessionLocal()
    try:
        username = username.strip()
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return {"status": "error", "message": "用户不存在"}
        if user.password != hash_password(password):
            return {"status": "error", "message": "密码不正确"}
        return {"status": "success", "user": {"id": user.id, "username": user.username}}
    finally:
        db.close()

def create_conversation(user_id: int, scene: str, title: str) -> dict:
    """创建会话"""
    db = SessionLocal()
    try:
        conv_id = str(uuid.uuid4())
        conv = Conversation(id=conv_id, user_id=user_id, scene=scene, title=title)
        db.add(conv)
        db.commit()
        return {"status": "success", "id": conv_id, "title": title, "scene": scene}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

def get_conversations(user_id: int, scene: str):
    """获取当前用户在当前场景下的所有历史会话，如果scene为all则返回所有会话"""
    db = SessionLocal()
    try:
        query = db.query(Conversation).filter(Conversation.user_id == user_id)
        if scene != "all":
            query = query.filter(Conversation.scene == scene)
        rows = query.order_by(Conversation.created_at.desc()).all()
        return [
            {
                "id": r.id, 
                "title": r.title, 
                "scene": r.scene, 
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S")
            } for r in rows
        ]
    finally:
        db.close()

def delete_conversation(user_id: int, conv_id: str) -> bool:
    """级联删除会话及其对应的聊天气泡"""
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(
            Conversation.user_id == user_id,
            Conversation.id == conv_id
        ).first()
        if conv:
            db.delete(conv)
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        return False
    finally:
        db.close()

def save_message(conv_id: str, role: str, content: str, data_payload: dict = None) -> dict:
    """保存单条对话气泡（支持附带 JSON 卡片负载数据）"""
    db = None
    try:
        db = SessionLocal()
        payload_str = json.dumps(data_payload, ensure_ascii=False) if data_payload else None
        msg = Message(conversation_id=conv_id, role=role, content=content, data_payload=payload_str)
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "data_payload": data_payload,
            "created_at": msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        print(f"【Message Error】保存对话失败: {e}")
        if db:
            try:
                db.rollback()
            except Exception as rollback_err:
                print(f"【Message Rollback Error】回滚失败: {rollback_err}")
        return {}
    finally:
        if db:
            try:
                db.close()
            except Exception as close_err:
                print(f"【Message Close Error】关闭失败: {close_err}")

def get_messages(conv_id: str):
    """拉取指定会话下的全部消息记录"""
    db = SessionLocal()
    try:
        rows = db.query(Message).filter(Message.conversation_id == conv_id).order_by(Message.id.asc()).all()
        result = []
        for r in rows:
            payload = None
            if r.data_payload:
                try:
                    payload = json.loads(r.data_payload)
                except Exception:
                    payload = None
            result.append({
                "id": r.id,
                "role": r.role,
                "content": r.content,
                "data_payload": payload,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S")
            })
        return result
    finally:
        db.close()

def log_event(user_id: int, scene: str, level: str, message: str, details: str = None) -> bool:
    """系统业务运行日志落库，同时同步打印到标准控制台"""
    try:
        print(f"【System Log】【{level}】{message} | 详情: {details or ''}")
    except Exception:
        try:
            safe_msg = message.encode('gbk', errors='replace').decode('gbk')
            safe_det = details.encode('gbk', errors='replace').decode('gbk') if details else ''
            print(f"【System Log】【{level}】{safe_msg} | 详情: {safe_det}")
        except Exception:
            pass

    db = None
    try:
        db = SessionLocal()
        sys_log = SystemLog(
            user_id=user_id,
            scene=scene,
            level=level,
            message=message,
            details=details
        )
        db.add(sys_log)
        db.commit()
        return True
    except Exception as e:
        print(f"【System Log Error】写入日志表失败: {e}")
        if db:
            try:
                db.rollback()
            except Exception as rollback_err:
                print(f"【System Log Rollback Error】回滚失败: {rollback_err}")
        return False
    finally:
        if db:
            try:
                db.close()
            except Exception as close_err:
                print(f"【System Log Close Error】关闭失败: {close_err}")

def get_logs(limit: int = 60):
    """获取最新的系统运行日志"""
    db = SessionLocal()
    try:
        rows = db.query(SystemLog).order_by(SystemLog.timestamp.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "user_id": r.user_id,
                "scene": r.scene,
                "level": r.level,
                "message": r.message,
                "details": r.details,
                "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            } for r in rows
        ]
    finally:
        db.close()

def decode_column_name(col_name: str) -> str:
    """
    对乱码列名进行无损解码还原。
    由于数据库中列名以 Latin1 编码或双重编码形式存在，而 PyMySQL 采用 utf8mb4 连接后，
    非 utf8mb4 字节会转化为特定的 Latin1 映射字符。通过将列名强制以 latin1 编码回原始字节，
    再使用 gbk 重新解码，可无损还原中文字段名。
    如果列名原本即为正确的中文字符，由于包含码点 > 255 的字符，encode('latin1') 将抛出异常，
    此时直接返回原字段名。
    """
    if not col_name:
        return ""
    try:
        b = col_name.encode('latin1')
        s = b.decode('gbk')
        return s
    except Exception:
        pass
    return col_name

def query_business_db(sql: str, params: dict = None) -> list:
    """
    通用业务数据库查询接口。
    强制使用 utf8mb4 字符集进行直连，执行 SQL 级过滤，
    拉取数据后在内存中进行轻量级列名还原，最终以干净的 dict 列表形式返回。
    """
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("【Database Business Query Error】DATABASE_URL 环境变量未配置")
        return []
        
    # 强制在 URL 参数中追加 charset=utf8mb4 字符集
    if "?" in db_url:
        base_url = db_url.split("?")[0]
        db_url = f"{base_url}?charset=utf8mb4"
    else:
        db_url = f"{db_url}?charset=utf8mb4"
        
    # 创建临时专用引擎以保障连接与资源隔离
    temp_engine = create_db_engine(db_url)
    try:
        with temp_engine.connect() as conn:
            res = conn.execute(text(sql), params or {})
            raw_keys = list(res.keys())
            clean_keys = [decode_column_name(k) for k in raw_keys]
            
            result = []
            for row in res:
                result.append(dict(zip(clean_keys, row)))
            return result
    except Exception as e:
        print(f"【Database Business Query Error】执行业务 SQL 失败: {e} | SQL: {sql}")
        return []

