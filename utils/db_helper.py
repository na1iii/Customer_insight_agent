# -*- coding: utf-8 -*-
"""
db_helper.py - 数据库管理层，提供 SQLAlchemy 初始化、用户鉴权、会话历史管理以及系统日志落库逻辑。
支持直连配置的目标关系型数据库并进行严格初始化校验。
"""

import os
import hashlib
import uuid
import json
import asyncio
from openai import AsyncOpenAI
from collections import Counter
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, text, Index, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker

# 初始化 Elasticsearch 客户端 (忽略 SSL 自签名证书警告)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from elasticsearch import Elasticsearch

ES_HOST = os.getenv("ES_HOST", "")
ES_USER = os.getenv("ES_USER", "")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")
ES_INDEX = os.getenv("ES_INDEX", "customer_insight_agent_logs")

es_client = None
if ES_HOST:
    try:
        auth = (ES_USER, ES_PASSWORD) if ES_USER and ES_PASSWORD else None
        es_client = Elasticsearch(
            ES_HOST,
            basic_auth=auth,
            verify_certs=False, # 本地自签名证书默认为 False
            ssl_show_warn=False
        )
    except Exception as es_init_err:
        print(f"【Elasticsearch Warning】初始化 ES 客户端失败: {es_init_err}")

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

class OpportunityArticle(Base):
    __tablename__ = "opportunity_articles"
    __table_args__ = (
        UniqueConstraint("article_uid", "source_type", "ent_name", name="uk_article_source_ent"),
        Index("idx_opportunity_district_score_time", "district", "score", "release_time"),
        Index("idx_opportunity_ent_name", "ent_name"),
        Index("idx_opportunity_release_time", "release_time"),
        Index("idx_opportunity_is_valid", "is_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    article_uid = Column(String(128), nullable=False)
    source_type = Column(String(50), nullable=False)
    source_name = Column(String(255), nullable=True)
    title = Column(Text, nullable=True)
    link = Column(Text, nullable=True)
    release_time = Column(String(50), nullable=True)
    district = Column(String(50), nullable=True)
    ent_name = Column(String(255), nullable=False)
    industry = Column(String(255), nullable=True)
    abstract = Column(Text, nullable=True)
    score = Column(Integer, default=0)
    score_label = Column(String(50), nullable=True)
    score_class = Column(String(50), nullable=True)
    display_tags = Column(Text, nullable=True)
    matched_rules = Column(Text, nullable=True)
    sources = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True)
    is_valid = Column(Integer, default=1)
    noise_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
        conn.execute(text("SELECT 1 FROM conversations LIMIT 1"))
        conn.execute(text("SELECT 1 FROM messages LIMIT 1"))
        conn.execute(text("SELECT 1 FROM logs LIMIT 1"))
        try:
            conn.execute(text("SELECT 1 FROM opportunity_articles LIMIT 1"))
        except Exception:
            Base.metadata.create_all(bind=engine, tables=[OpportunityArticle.__table__])
            conn.execute(text("SELECT 1 FROM opportunity_articles LIMIT 1"))
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
                "created_at": (r.created_at + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S") if r.created_at else ""
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

def update_conversation_title(conv_id: str, new_title: str) -> bool:
    """更新会话记录的标题"""
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if conv:
            conv.title = new_title
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
    """系统业务运行日志落库，同时同步打印到标准控制台并上传至 Elasticsearch"""
    try:
        print(f"【System Log】【{level}】{message} | 详情: {details or ''}")
    except Exception:
        try:
            safe_msg = message.encode('gbk', errors='replace').decode('gbk')
            safe_det = details.encode('gbk', errors='replace').decode('gbk') if details else ''
            print(f"【System Log】【{level}】{safe_msg} | 详情: {safe_det}")
        except Exception:
            pass

    # ES 写入
    es_success = False
    if es_client:
        try:
            doc = {
                "user_id": user_id,
                "scene": scene,
                "level": level,
                "message": message,
                "details": details,
                "timestamp": datetime.utcnow().isoformat()
            }
            es_client.index(index=ES_INDEX, document=doc)
            es_success = True
        except Exception as e:
            print(f"【System Log Error】写入 ES 失败: {e}")

    # 兜底/双写写入 SQL 数据库
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
        print(f"【System Log Error】写入本地日志表失败: {e}")
        if db:
            try:
                db.rollback()
            except Exception as rollback_err:
                print(f"【System Log Rollback Error】回滚失败: {rollback_err}")
        return es_success
    finally:
        if db:
            try:
                db.close()
            except Exception as close_err:
                print(f"【System Log Close Error】关闭失败: {close_err}")

def get_logs(limit: int = 60):
    """获取最新的系统运行日志，优先从 ES 查询，如果失败或未配置则从 SQL 数据库查询"""
    if es_client:
        try:
            # 检查索引是否存在，如果不存在先不报错直接返回空
            if es_client.indices.exists(index=ES_INDEX):
                res = es_client.search(
                    index=ES_INDEX,
                    query={"match_all": {}},
                    sort=[{"timestamp": {"order": "desc"}}],
                    size=limit
                )
                logs = []
                for hit in res['hits']['hits']:
                    source = hit['_source']
                    ts_str = source.get("timestamp", "")
                    try:
                        # 格式化展示时间，去除 Z 或毫秒并转为北京时间格式显示
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        ts_display = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        ts_display = ts_str
                    
                    logs.append({
                        "id": hit.get('_id', ''),
                        "user_id": source.get("user_id"),
                        "scene": source.get("scene"),
                        "level": source.get("level"),
                        "message": source.get("message"),
                        "details": source.get("details"),
                        "timestamp": ts_display
                    })
                return logs
        except Exception as e:
            print(f"【System Log Error】从 ES 读取日志失败，将使用本地数据库兜底: {e}")

    # 兜底查询关系型数据库
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



# 3. 公众号商机文章分析配置

DISTRICTS = [
    "浦东新区", "黄浦区", "徐汇区", "长宁区", "静安区", "普陀区", "虹口区", "杨浦区",
    "闵行区", "宝山区", "嘉定区", "金山区", "松江区", "青浦区", "奉贤区", "崇明区"
]

REGION_ALIASES = {
    "上海徐汇": "徐汇区",
    "徐汇": "徐汇区",
    "浦东": "浦东新区",
}

CATERING_KEYWORDS = [
    "餐饮", "餐厅", "饭店", "酒店餐饮", "火锅", "烧烤", "咖啡", "奶茶", "茶饮", "糖水", "烘焙",
    "面包", "甜品", "小吃", "美食", "食品服务", "连锁餐饮", "餐饮服务", "餐饮企业"
]

SCORING_RULES = [
    ("投资落地", 25, ["企业投资", "投资落地", "落户", "开工", "投产", "入驻", "设立", "总部落地", "新设", "成立", "扩产", "落地"]),
    ("重大签约", 20, ["企业签约", "签约", "战略合作", "合作协议", "签约仪式", "对接", "达成合作", "合作"]),
    ("领导调研", 15, ["领导走访", "领导", "调研", "考察", "视察", "走访", "座谈", "书记", "区长", "主任"]),
    ("资本融资", 15, ["企业融资", "融资", "IPO", "上市", "基金", "注资", "增资", "战略投资", "完成融资", "挂牌", "科创板", "港交所", "北交所", "收购", "并购", "股权", "领投", "跟投"]),
    ("技术突破", 15, ["研发突破", "技术突破", "获奖认证", "首发", "首创", "发布", "研发", "攻克", "创新成果", "首款", "首台", "认证", "获奖", "入选", "荣获", "专精特新", "高新技术企业", "小巨人", "瞪羚", "百强"]),
    ("具化数据", 10, ["明确金额", "规模等数据", "金额", "投资额", "融资额", "面积", "产值", "规模", "数量", "亿元", "万元", "平方米", "亩"]),
    ("会议论坛", 10, ["行业大会", "会议", "论坛", "峰会", "推介会", "发布会", "展会", "博览会", "对接会", "路演"]),
]

EVENT_PRIORITY = ["投资落地", "重大签约", "领导调研", "资本融资", "技术突破", "具化数据", "会议论坛"]

def has_any(text_value: str, keywords: list[str]) -> bool:
    """判断文本是否命中任一关键词。"""
    return any(keyword and keyword in text_value for keyword in keywords)

def detect_article_region(row: dict) -> str:
    """根据文章字段识别上海行政区。"""
    text_all = "".join([
        row.get("Scope") or "",
        row.get("name") or "",
        row.get("title") or "",
        row.get("Abstract") or "",
        row.get("content") or "",
    ])
    for alias, district in REGION_ALIASES.items():
        if alias in text_all:
            return district
    for district in DISTRICTS:
        if district in text_all:
            return district
        short_name = district.replace("新区", "").replace("区", "")
        if short_name and short_name in text_all:
            return district
    return ""

def calc_article_opportunity_score(row: dict) -> dict:
    """计算公众号文章商机分数与采集等级。"""
    abstract = (row.get("Abstract") or "").strip()
    content = (row.get("content") or "").strip()
    title = (row.get("title") or "").strip()
    scope = (row.get("Scope") or "").strip()
    ind1 = (row.get("Industry1") or "").strip()
    ind2 = (row.get("Industry2") or "").strip()
    ind3 = (row.get("Industry3") or "").strip()
    topic = (row.get("Topic") or "").strip()
    tag_ss = (row.get("Tag_SS") or "").strip()
    tag_ipo = (row.get("Tag_IPO") or "").strip()
    tag_rz = (row.get("Tag_RZ") or "").strip()
    ent_nature = (row.get("EnterpriseNature") or "").strip()
    other_nature = (row.get("OtherNature") or "").strip()
    ent_name = (row.get("EntName") or "").strip()
    ent_short = (row.get("EntShortName") or "").strip()
    region = detect_article_region(row)

    if ent_nature == "非企" or (not ent_name and not ent_short):
        return {
            "score": 0,
            "decision": "否",
            "level": "不符合采集标准",
            "type": "",
            "region": region,
            "hit": [],
            "reason": "未涉及具体企业" if not ent_name and not ent_short else "涉及对象为非企业",
        }

    text_all = "".join([title, abstract, content, scope, topic, ind1, ind2, ind3, ent_nature, other_nature])
    is_catering = has_any(text_all, CATERING_KEYWORDS)
    if is_catering:
        return {
            "score": 0,
            "decision": "否",
            "level": "不符合采集标准",
            "type": "",
            "region": region,
            "hit": ["餐饮行业"],
            "reason": "餐饮类相关内容不展示",
        }

    score = 10
    hit = ["企业提及"]
    for rule_name, points, keywords in SCORING_RULES:
        if has_any(text_all, keywords):
            score += points
            hit.append(rule_name)

    tag_sg = (row.get("Tag_SG") or "").strip()
    if tag_sg and "资本融资" not in hit:
        score += 15
        hit.append("资本融资")

    if (tag_ss == "是" or tag_ipo == "是") and "资本融资" not in hit:
        score += 15
        hit.append("资本融资")
    if tag_rz and "资本融资" not in hit:
        score += 15
        hit.append("资本融资")
        
    if other_nature and not has_any(other_nature, ["非企", "无"]):
        score += 10
        if "企业资质" not in hit:
            hit.append("企业资质")

    score = min(score, 100)
    hit = list(dict.fromkeys(hit))
    event_type = ""
    for event_name in EVENT_PRIORITY:
        if event_name in hit:
            event_type = event_name
            break

    if score >= 55:
        decision = "是"
        level = "推荐采集"
        reason = ""
    elif score >= 15:
        decision = "是"
        level = "建议采集"
        reason = ""
    else:
        decision = "否"
        level = "不符合采集标准"
        reason = "未命中足够的入选逻辑或评分维度"

    return {
        "score": score,
        "decision": decision,
        "level": level,
        "type": event_type,
        "region": region,
        "hit": hit,
        "reason": reason,
    }

def extract_article_display_tags(row: dict) -> list[str]:
    """提取前端展示用结构化标签。"""
    tags = []
    news_tag = (row.get("news_tag") or row.get("NewsTag") or "").strip()
    if news_tag and news_tag != "其他":
        tags.append(news_tag)

    topic = (row.get("Topic") or "").strip()
    tag_ss = (row.get("Tag_SS") or "").strip()
    tag_ipo = (row.get("Tag_IPO") or "").strip()
    tag_rz = (row.get("Tag_RZ") or "").strip()
    tag_sg = (row.get("Tag_SG") or "").strip()

    if topic == "上市" and tag_ss == "是":
        tags.append("上市")
    elif topic == "IPO" and tag_ipo == "是":
        tags.append("IPO")
    elif topic == "融资" and tag_rz:
        tags.append(tag_rz)
    elif topic == "收购" and tag_sg:
        tags.append(tag_sg)

    capital_nature = (row.get("CapitalNature") or "").strip()
    if capital_nature:
        tags.append(capital_nature)

    other_nature = (row.get("OtherNature") or "").strip()
    if other_nature:
        tags.append(other_nature)

    return list(dict.fromkeys(tags))

def score_to_display(score: int, level: str) -> tuple[str, str]:
    """将采集优先级映射为前端显示标签和 CSS class。"""
    if level == "推荐采集" or score >= 55:
        return "HOT", "score-red"
    if level == "建议采集" or score >= 15:
        return "关注", "score-blue"
    return "不采集", "score-gray"

def format_release_time(raw_time: str) -> str:
    """将发布时间格式化为前端展示文本。"""
    if not raw_time or not str(raw_time).strip():
        return ""
    raw_time = str(raw_time).strip()
    for time_format in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw_time, time_format)
            return f"{dt.month}月{dt.day}日"
        except ValueError:
            continue
    return raw_time

def get_today_display() -> str:
    """获取当前日期的中文展示。"""
    now = datetime.now()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return now.strftime(f"%Y年%m月%d日 · {weekdays[now.weekday()]}")

def parse_json_list(value) -> list:
    """安全解析数据库中的 JSON 数组字段。"""
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []

def fetch_article_rows(limit: int = 500, district: str = None) -> list[dict]:
    """
    读取基础新闻表，并在内存中与 ranking_ent_dtl_clue 进行实体链接，
    返回适配旧版业务逻辑的行格式（字典）。
    """
    ent_sql = text("""
        SELECT `企业名称`, `企业简称`, `工商行业`, `客户区局`, `资质名称`
        FROM ranking_ent_dtl_clue
        WHERE `企业名称` IS NOT NULL AND `企业名称` != ''
    """)
    
    district_short = (district or "").replace("新区", "").replace("区", "")
    district_patterns = []
    if district:
        district_patterns.append(f"%{district}%")
        if district_short and district_short != district:
            district_patterns.append(f"%{district_short}%")

    wx_where = "w.title IS NOT NULL AND w.title != ''"
    sh_where = "`标题` IS NOT NULL AND `标题` != ''"
    query_params = {"limit": limit}
    if district_patterns:
        pattern_parts = []
        for i, pattern in enumerate(district_patterns):
            key = f"district_pattern_{i}"
            query_params[key] = pattern
            pattern_parts.append(f"w.title LIKE :{key} OR w.content LIKE :{key} OR w.name LIKE :{key}")
        wx_where += " AND (" + " OR ".join(pattern_parts) + ")"

        sh_pattern_parts = []
        for i in range(len(district_patterns)):
            key = f"district_pattern_{i}"
            sh_pattern_parts.append(f"`项目落地地区` LIKE :{key} OR `标题` LIKE :{key} OR `内容` LIKE :{key} OR `来源` LIKE :{key}")
        sh_where += " AND (" + " OR ".join(sh_pattern_parts) + ")"

    wx_sql = text(f"""
        SELECT w.name, w.title, w.content, w.release_time, w.link, 'wechat' as source_type, '' as sh_region, p.Abstract
        FROM weixin_article_dtl_unique w
        LEFT JOIN wechat_article_ai_parse p ON w.title = p.title
        WHERE {wx_where}
        ORDER BY w.release_time DESC LIMIT :limit
    """)
    sh_sql = text(f"""
        SELECT 
            `来源` AS name,
            `标题` AS title,
            `内容` AS content,
            `发布日期` AS release_time,
            `URL` AS link,
            'shnews' AS source_type,
            `项目落地地区` AS sh_region,
            '' AS Abstract
        FROM zq_dtl_shnews_yyy
        WHERE {sh_where}
        ORDER BY `发布日期` DESC LIMIT :limit
    """)
    
    with engine.connect() as conn:
        ent_rows = conn.execute(ent_sql).mappings().all()
        ent_dict = {}
        for r in ent_rows:
            name = (r.get("企业名称") or "").strip()
            short = (r.get("企业简称") or "").strip()
            val = {"full": name, "short": short, "ind": r.get("工商行业"), "dist": r.get("客户区局"), "qual": r.get("资质名称")}
            if name:
                ent_dict[name] = val
            if short and len(short) > 2:
                ent_dict[short] = val
                
        wx_rows = conn.execute(wx_sql, query_params).mappings().all()
        sh_rows = conn.execute(sh_sql, query_params).mappings().all()
        all_articles = list(wx_rows) + list(sh_rows)
        
    result_rows = []
    
    for row in all_articles:
        title = (row.get("title") or "").strip()
        content = (row.get("content") or "").strip()
        text_all = title + " " + content[:2000]
        
        matched_ent = None
        text_len = len(text_all)
        
        for length in range(30, 2, -1):
            if matched_ent:
                break
            for i in range(text_len - length + 1):
                sub = text_all[i:i+length]
                if sub in ent_dict:
                    matched_ent = ent_dict[sub]
                    break
                
        if not matched_ent:
            ent_nature = "非企"
            ent_name = ""
            ent_short = ""
            ind1 = ""
            region = row.get("sh_region") or ""
            qual = ""
        else:
            ent_nature = "企业"
            ent_name = matched_ent["full"]
            ent_short = matched_ent["short"]
            ind1 = matched_ent["ind"] or ""
            region = matched_ent["dist"] or row.get("sh_region") or ""
            qual = matched_ent["qual"] or ""
            
        tag_ss = "是" if "上市" in text_all else ""
        tag_ipo = "是" if "IPO" in text_all.upper() else ""
        tag_rz = "融资" if "融资" in text_all else ""
        tag_sg = "收购" if ("收购" in text_all or "并购" in text_all) else ""
            
        abstract = row.get("Abstract") or ""
        
        if not abstract:
            if ent_short and ent_short in content:
                idx = content.find(ent_short)
                start = max(0, idx - 20)
                abstract = content[start:start+80].replace('\n', ' ').strip() + "..."
            else:
                abstract = content[:80].replace('\n', ' ').strip() + "..." if content else ""
            
        mocked_row = {
            "EntName": ent_name,
            "EntShortName": ent_short,
            "Abstract": abstract,
            "Scope": region,
            "Industry1": ind1,
            "Industry2": "",
            "Industry3": "",
            "Topic": "",
            "Tag_SS": tag_ss,
            "Tag_IPO": tag_ipo,
            "Tag_RZ": tag_rz,
            "Tag_SG": tag_sg,
            "EnterpriseNature": ent_nature,
            "CapitalNature": "",
            "OtherNature": qual,
            "news_tag": "",
            "name": row.get("name") or "",
            "title": title,
            "content": content,
            "release_time": row.get("release_time") or "",
            "link": row.get("link") or "",
            "source_type": row.get("source_type") or "",
        }
        
        result_rows.append(mocked_row)
        
    return result_rows

def get_articles_from_result_table(district: str = None) -> dict:
    """从商机预计算结果表读取前端展示数据，在线接口只走该轻量查询。"""
    sql = """
        SELECT
            ent_name, abstract, title, release_time, score, score_label, score_class,
            source_name, link, industry, district, display_tags, matched_rules, sources
        FROM opportunity_articles
        WHERE is_valid = 1
    """
    params = {}
    if district:
        sql += " AND district = :district"
        params["district"] = district
    sql += " ORDER BY release_time DESC, score DESC LIMIT 50000"

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    groups_dict = {district: []} if district else {district_name: [] for district_name in DISTRICTS}
    for row in rows:
        group_name = (row.get("district") or "其他").strip() or "其他"
        source_items = parse_json_list(row.get("sources"))
        if not source_items:
            release_time_raw = str(row.get("release_time") or "").strip()
            source_items = [{
                "source_name": row.get("source_name") or "其他",
                "release_time": format_release_time(release_time_raw),
                "release_time_raw": release_time_raw,
                "link": row.get("link") or "",
                "title": row.get("title") or "",
            }]

        article = {
            "ent_name": row.get("ent_name") or "未命名企业",
            "abstract": row.get("abstract") or "",
            "title": row.get("title") or "",
            "release_time": format_release_time(str(row.get("release_time") or "")),
            "release_time_raw": str(row.get("release_time") or ""),
            "score": row.get("score") or 0,
            "score_label": row.get("score_label") or "关注",
            "score_class": row.get("score_class") or "score-blue",
            "source_name": row.get("source_name") or "其他",
            "link": row.get("link") or "",
            "industry": row.get("industry") or "",
            "region": group_name,
            "sort_group": group_name,
            "hit": parse_json_list(row.get("matched_rules")),
            "sources": source_items,
            "display_tags": parse_json_list(row.get("display_tags")),
        }
        if group_name not in groups_dict:
            groups_dict[group_name] = []
        groups_dict[group_name].append(article)

    groups = []
    total_count = 0
    for group_name, articles in groups_dict.items():
        if group_name == "其他" and not articles:
            continue
        articles.sort(key=lambda article: article["release_time_raw"], reverse=True)
        groups.append({"name": group_name, "count": len(articles), "articles": articles})
        total_count += len(articles)

    def get_group_order(group_name: str) -> int:
        try:
            return DISTRICTS.index(group_name)
        except ValueError:
            return 999

    groups.sort(key=lambda group: get_group_order(group["name"]))
    return {"date": get_today_display(), "total_count": total_count, "group_count": len(groups), "groups": groups}

def get_articles_live(district: str = None, limit: int = 500) -> dict:
    """旧版实时计算逻辑，现已重构为大模型判别逻辑（供后台构建或应急调试使用）。"""
    rows = fetch_article_rows(limit=limit, district=district)
    
    # 策略3：在此处增加过滤逻辑，若文章已被处理过，就不再交由大模型判别
    existing_links = set()
    try:
        with SessionLocal() as session:
            for r in session.query(OpportunityArticle).all():
                if r.link:
                    existing_links.add(r.link)
                if r.sources:
                    try:
                        srcs = json.loads(r.sources)
                        for s in srcs:
                            if s.get("link"): existing_links.add(s["link"])
                    except:
                        pass
    except Exception as e:
        print("【Warning】获取已有链接失败，跳过过滤。")
        
    filtered_rows = [r for r in rows if r.get("link") not in existing_links]
    print(f"【Optimization】总计获取 {len(rows)} 条，其中 {len(existing_links)} 条已存在，需要 LLM 处理的增量条数为 {len(filtered_rows)} 条。")
    
    # 使用大模型并发判别所有新闻商机
    judgements = asyncio.run(_async_batch_llm_judge(filtered_rows))
    
    # 将 judgements 和已跳过的 row 补齐，但为了简单起见，既然已跳过，它就说明已经入库了，
    # 本次任务仅处理新产生的数据并生成增量记录写入 DB。前端会直接从 DB 读，所以这块没问题。
    companies_dict = {}

    for row, score_info in zip(filtered_rows, judgements):
        if score_info["decision"] != "是":
            continue
        if district and score_info["region"] != district:
            continue

        ent_short = (row.get("EntShortName") or "").strip()
        ent_full = (row.get("EntName") or "").strip()
        ent_display = ent_short if ent_short else ent_full
        if not ent_display:
            continue

        source_name = (row.get("name") or "").strip() or "其他"
        score = score_info["score"]
        label, css_class = score_to_display(score, score_info["level"])
        release_time_raw = str(row.get("release_time") or "").strip()
        source_item = {
            "source_name": source_name,
            "release_time": format_release_time(release_time_raw),
            "release_time_raw": release_time_raw,
            "link": (row.get("link") or "").strip(),
            "title": (row.get("title") or "").strip(),
        }

        if ent_display not in companies_dict:
            companies_dict[ent_display] = {
                "ent_name": ent_display,
                "abstract": (row.get("Abstract") or "").strip(),
                "title": (row.get("title") or "").strip(),
                "release_time": format_release_time(release_time_raw),
                "release_time_raw": release_time_raw,
                "score": score,
                "score_label": label,
                "score_class": css_class,
                "source_name": source_name,
                "link": (row.get("link") or "").strip(),
                "industry": (row.get("Industry1") or "").strip(),
                "topic": (row.get("Topic") or "").strip(),
                "enterprise_nature": (row.get("EnterpriseNature") or "").strip(),
                "decision": score_info["decision"],
                "level": score_info["level"],
                "type": score_info["type"],
                "region": score_info["region"],
                "hit": score_info["hit"],
                "sort_group": score_info["region"] or "其他",
                "sources": [source_item],
                "display_tags": extract_article_display_tags(row),
                "reason": score_info.get("reason", ""),
            }
            continue

        company = companies_dict[ent_display]
        company["sources"].append(source_item)
        company["hit"] = list(dict.fromkeys(company["hit"] + score_info["hit"]))
        company["display_tags"] = list(dict.fromkeys(company["display_tags"] + extract_article_display_tags(row)))

        if score > company["score"]:
            company["score"] = score
            company["score_label"] = label
            company["score_class"] = css_class
            company["level"] = score_info["level"]
            company["type"] = score_info["type"] or company["type"]

        if company["sort_group"] == "其他" and score_info["region"]:
            company["region"] = score_info["region"]
            company["sort_group"] = score_info["region"]

        if release_time_raw > company["release_time_raw"]:
            company["abstract"] = (row.get("Abstract") or "").strip()
            company["title"] = (row.get("title") or "").strip()
            company["release_time"] = format_release_time(release_time_raw)
            company["release_time_raw"] = release_time_raw
            company["source_name"] = source_name
            company["link"] = (row.get("link") or "").strip()
            if (row.get("Industry1") or "").strip():
                company["industry"] = (row.get("Industry1") or "").strip()

    if district:
        groups_dict = {district: []}
    else:
        groups_dict = {district_name: [] for district_name in DISTRICTS}

    for company in companies_dict.values():
        company["sources"].sort(key=lambda s: s["release_time_raw"], reverse=True)
        group_name = company["sort_group"]
        if district and group_name != district:
            continue
        if group_name not in groups_dict:
            groups_dict[group_name] = []
        groups_dict[group_name].append(company)

    groups = []
    total_count = 0
    for group_name, articles in groups_dict.items():
        if group_name == "其他" and not articles:
            continue
        articles.sort(key=lambda article: article["release_time_raw"], reverse=True)
        groups.append({
            "name": group_name,
            "count": len(articles),
            "articles": articles,
        })
        total_count += len(articles)

    def get_group_order(group_name: str) -> int:
        try:
            return DISTRICTS.index(group_name)
        except ValueError:
            return 999

    groups.sort(key=lambda group: get_group_order(group["name"]))
    return {
        "date": get_today_display(),
        "total_count": total_count,
        "group_count": len(groups),
        "groups": groups,
    }

def rebuild_opportunity_articles(district: str = None, limit: int = 500, clear_existing: bool = False) -> dict:
    """后台构建商机预计算结果表，供定时任务/手动刷新调用。"""
    live_data = get_articles_live(district=district, limit=limit)
    articles = []
    for group in live_data.get("groups", []):
        for article in group.get("articles", []):
            article["region"] = article.get("region") or group.get("name")
            articles.append(article)

    with SessionLocal() as session:
        if clear_existing:
            query = session.query(OpportunityArticle)
            if district:
                query = query.filter(OpportunityArticle.district == district)
            query.delete(synchronize_session=False)
            session.commit()
            
        existing_uids = {r[0] for r in session.query(OpportunityArticle.article_uid).all()}

        for article in articles:
            release_time_raw = str(article.get("release_time_raw") or "").strip()
            sources = article.get("sources") or []
            if len(sources) > 15:
                sources = sources[:15]
            content_hash_raw = "|".join([
                article.get("ent_name") or "",
                article.get("title") or "",
                article.get("abstract") or "",
                release_time_raw,
                json.dumps(sources, ensure_ascii=False, sort_keys=True),
            ])
            article_uid = hashlib.sha256(((article.get("link") or article.get("title") or article.get("ent_name") or "") + release_time_raw).encode("utf-8")).hexdigest()[:32]
            
            if article_uid in existing_uids:
                continue
                
            record = OpportunityArticle(
                article_uid=article_uid,
                source_type="aggregated",
                source_name=article.get("source_name") or "其他",
                title=article.get("title") or "",
                link=article.get("link") or "",
                release_time=release_time_raw,
                district=article.get("region") or article.get("sort_group") or "其他",
                ent_name=article.get("ent_name") or "未命名企业",
                industry=article.get("industry") or "",
                abstract=article.get("abstract") or "",
                score=article.get("score") or 0,
                score_label=article.get("score_label") or "关注",
                score_class=article.get("score_class") or "score-blue",
                display_tags=json.dumps(article.get("display_tags") or [], ensure_ascii=False),
                matched_rules=json.dumps(article.get("hit") or [], ensure_ascii=False),
                sources=json.dumps(sources, ensure_ascii=False),
                content_hash=hashlib.sha256(content_hash_raw.encode("utf-8")).hexdigest(),
                is_valid=1,
                noise_reason=article.get("reason") or "",
            )
            session.add(record)
        session.commit()
        
    return {
        "status": "success",
        "district": district,
        "count": len(articles),
        "group_count": live_data.get("group_count", 0),
    }

async def _async_batch_llm_judge(rows: list) -> list:
    """批量异步使用大模型提取新闻商机标签与推荐理由"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    
    if not api_key or "your_api_key" in api_key:
        print("【System】未配置有效的 API_KEY，降级为正则表达式商机打分。")
        return [calc_article_opportunity_score(row) for row in rows]
        
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    sem = asyncio.Semaphore(15) 
    
    final_results = [None] * len(rows)
    filtered_batch_items = []
    
    noise_keywords = ["党建", "走访慰问", "暖心驿站", "警务", "社区活动", "核酸", "志愿服务"]
    
    for idx, row in enumerate(rows):
        title = (row.get("title") or "").strip()
        abstract = (row.get("Abstract") or "").strip()
        content = (row.get("content") or "").strip()
        ent_name = (row.get("EntName") or row.get("EntShortName") or "").strip()
        region = detect_article_region(row)
        
        default_res = {
            "score": 0, "decision": "否", "level": "不符合采集标准",
            "type": "", "region": region, "hit": [], "reason": ""
        }
        
        text_all = title + " " + abstract + " " + content[:800]
        
        if not ent_name or row.get("EnterpriseNature") == "非企":
            default_res["reason"] = "未涉及具体企业或属于非企"
            final_results[idx] = default_res
            continue
            
        if has_any(text_all, noise_keywords) or has_any(text_all, CATERING_KEYWORDS):
            default_res["reason"] = "属于非核心关注内容(政务/党建/餐饮等)"
            final_results[idx] = default_res
            continue
            
        filtered_batch_items.append((idx, row))
        
    batch_size = 10
    batches = [filtered_batch_items[i:i + batch_size] for i in range(0, len(filtered_batch_items), batch_size)]
    
    async def process_batch(batch_tuple):
        batch_idxs = [b[0] for b in batch_tuple]
        batch = [b[1] for b in batch_tuple]
        
        async with sem:
            batch_text = ""
            for i, row in enumerate(batch):
                t = (row.get("title") or "").strip()
                e = (row.get("EntName") or row.get("EntShortName") or "").strip()
                c = (row.get("content") or "").strip()
                batch_text += f"\\n[ID: {i}] 企业: {e} | 标题: {t} | 内容: {c[:250]}"
                
            prompt = f"""
你是一个专业的政企大客户销售商机挖掘专家。请分析以下 {len(batch)} 篇新闻是否包含真正对通信运营商有价值的【企业商机】。
请忽略【暖心驿站、志愿服务、党建、仅为新闻来源】的内容。

{batch_text}

请严格返回一个 JSON 对象，包含一个名为 `results` 的数组，数组长度必须严格等于 {len(batch)}。对应顺序不可改变。
格式示例：
{{
  "results": [
    {{
      "is_valid": true,
      "tags": ["重大签约", "业务扩张"],
      "score": 85,
      "reason": "企业签约大单，有明确扩张倾向。"
    }}
  ]
}}
- is_valid: 若无商业价值为 false
- tags: 从 ["投资落地", "重大签约", "资本融资", "技术突破", "高管调研", "具化数据", "业务扩张", "企业资质"] 中选择
- score: 0到100
"""
            for attempt in range(4):
                try:
                    resp = await client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                        temperature=0.1,
                        timeout=30.0
                    )
                    content = resp.choices[0].message.content
                    res_json = json.loads(content)
                    items = res_json.get("results", [])
                    if len(items) != len(batch):
                        raise ValueError(f"Length mismatch: {len(items)} vs {len(batch)}")
                        
                    results = []
                    for i, item in enumerate(items):
                        is_valid = item.get("is_valid", False)
                        score = item.get("score", 0)
                        tags = item.get("tags", [])
                        reason = item.get("reason", "")
                        region = detect_article_region(batch[i])
                        
                        if is_valid and score >= 15:
                            level = "推荐采集" if score >= 55 else "建议采集"
                            results.append({
                                "score": score, "decision": "是", "level": level,
                                "type": tags[0] if tags else "其他商机", "region": region,
                                "hit": tags, "reason": reason
                            })
                        else:
                            results.append({
                                "score": 0, "decision": "否", "level": "不符合采集标准",
                                "type": "", "region": region, "hit": [], "reason": reason or "大模型判定非有效商机"
                            })
                    return (batch_idxs, results)
                except Exception as e:
                    print(f"【LLM Batch Warning】Attempt {attempt+1} failed: {e}")
                    await asyncio.sleep(2 ** attempt)
            
            # fallback
            print("【LLM Batch Error】Fallback to regex")
            return (batch_idxs, [calc_article_opportunity_score(r) for r in batch])

    if batches:
        batch_outputs = await asyncio.gather(*[process_batch(b) for b in batches])
        for idxs, results in batch_outputs:
            for i, res in zip(idxs, results):
                final_results[i] = res
                
    return final_results

    return {
        "status": "success",
        "district": district,
        "count": len(articles),
        "group_count": live_data.get("group_count", 0),
    }

def get_articles(district: str = None) -> dict:
    """返回前端商机列表所需的数据结构，兼容 /api/articles。"""
    return get_articles_from_result_table(district=district)

def get_articles_summary(district: str = None) -> dict:
    """获取商机汇总指标，供 regional.py 生成聊天卡片；district 为空时统计上海市全部区域。"""
    empty_summary = {
        "total": 0,
        "hot": 0,
        "watch": 0,
        "top_industries": [],
        "latest_titles": [],
        "district_counts": [],
    }
    try:
        articles_data = get_articles(district=district)
    except Exception as e:
        print(f"【Article Summary Error】获取 {district or '上海市'} 商机汇总失败: {e}")
        return empty_summary

    articles = []
    district_counter = Counter()
    for group in articles_data.get("groups", []):
        group_articles = group.get("articles", [])
        if group.get("name"):
            district_counter[group.get("name")] += len(group_articles)
        articles.extend(group_articles)

    hot_count = sum(1 for article in articles if article.get("score_label") == "HOT")
    watch_count = sum(1 for article in articles if article.get("score_label") == "关注")
    industry_counter = Counter(
        article.get("industry") for article in articles if article.get("industry")
    )
    latest_articles = sorted(
        articles,
        key=lambda article: article.get("release_time_raw") or "",
        reverse=True,
    )

    return {
        "total": len(articles),
        "hot": hot_count,
        "watch": watch_count,
        "top_industries": [name for name, _ in industry_counter.most_common(5)],
        "latest_titles": [article.get("title") for article in latest_articles[:5] if article.get("title")],
        "district_counts": [{"name": name, "count": district_counter.get(name, 0)} for name in DISTRICTS],
    }

def get_articles_summary_fast(district: str) -> dict:
    """
    获取区域商机聊天卡片所需的轻量汇总。

    该函数避免调用 get_articles()/fetch_article_rows() 的全量实体链接与全文滑动窗口逻辑，
    只基于政企新闻表中的区域、标题、内容做快速统计，保证聊天接口可以快速返回。
    明细页仍继续使用 get_articles() 展示完整列表。
    """
    empty_summary = {
        "total": 0,
        "hot": 0,
        "watch": 0,
        "top_industries": [],
        "latest_titles": [],
    }
    if not district:
        return empty_summary

    district_short = district.replace("新区", "").replace("区", "")
    like_patterns = [f"%{district}%"]
    if district_short and district_short != district:
        like_patterns.append(f"%{district_short}%")

    where_clause = " OR ".join([
        "`项目落地地区` LIKE :pattern_{0} OR `标题` LIKE :pattern_{0}".format(i)
        for i in range(len(like_patterns))
    ])
    params = {f"pattern_{i}": pattern for i, pattern in enumerate(like_patterns)}

    sql = text(f"""
        SELECT
            `标题` AS title,
            `内容` AS content,
            `发布日期` AS release_time,
            `项目落地地区` AS sh_region
        FROM zq_dtl_shnews_yyy
        WHERE ({where_clause})
          AND `标题` IS NOT NULL
          AND `标题` != ''
        ORDER BY `发布日期` DESC
        LIMIT 120
    """)

    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
    except Exception as e:
        print(f"【Article Fast Summary Error】获取 {district} 轻量商机汇总失败: {e}")
        return empty_summary

    hot_count = 0
    watch_count = 0
    industry_counter = Counter()
    latest_titles = []

    industry_keywords = [
        "人工智能", "生物医药", "集成电路", "软件", "信息技术", "数字经济", "智能制造",
        "新能源", "新材料", "机器人", "金融", "文创", "航运", "汽车", "半导体",
    ]

    for row in rows:
        title = (row.get("title") or "").strip()
        content = (row.get("content") or "").strip()
        text_all = title + content[:1000]

        score = 10
        for _, points, keywords in SCORING_RULES:
            if has_any(text_all, keywords):
                score += points
        score = min(score, 100)

        if score >= 55:
            hot_count += 1
        elif score >= 15:
            watch_count += 1

        for industry in industry_keywords:
            if industry in text_all:
                industry_counter[industry] += 1

        if title and len(latest_titles) < 5:
            latest_titles.append(title)

    return {
        "total": len(rows),
        "hot": hot_count,
        "watch": watch_count,
        "top_industries": [name for name, _ in industry_counter.most_common(5)],
        "latest_titles": latest_titles,
    }
