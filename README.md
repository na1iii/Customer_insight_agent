# 客户洞察智能体 (Customer Insight Agent)

**客户洞察智能体** 是一款基于 FastAPI 与大语言模型（DeepSeek）构建的智能业务助理系统。该系统能够通过自然语言交互，实时解析业务人员的查询意图，并结合底层行业数据库（模拟企业内部数据中台），自动生成多维度的数据研报、区域商机画像与高潜客户名单。

## ✨ 核心功能特性

1. **智能意图路由 (Intelligent Routing)**
   - 采用大语言模型作为大脑（默认对接 DeepSeek API），精准识别用户的自然语言指令。
   - 支持多级意图穿透：客户画像查询、区域商机检索、全行业/特定行业深度报告生成、高潜客户挖掘等。

2. **自动生成动态研报 (Dynamic Reports)**
   - **区域商机报告**：一键生成覆盖全上海市及 16 个区的宏观经济与商机图文报告。
   - **行业深度分析**：基于底层政策、微信舆情、新闻动态库，利用 LLM 的内容生成能力自动汇总编写高质量、高颜值的全行业或单一行业 HTML 报告。
   - **支持一键导出 PDF 供业务层汇报使用**。

3. **高潜客户挖掘与导出 (Lead Generation)**
   - 根据“区域 + 行业 + 关键词”等复合条件，一键检索命中商机信号的高潜力企业。
   - 支持前端流式卡片展示，支持一键下载 100% 匹配展示结果的 Excel 明细清单（附带新闻原文链接自动解析）。

4. **流式交互前端 (SSE Chat UI)**
   - 内置轻量级、无需编译的原生 HTML/CSS/JS 前端控制台。
   - 采用 Server-Sent Events (SSE) 技术，实现打字机效果的流式输出，配合现代化微动效，具备极佳的用户交互体验。

---

## 🛠️ 技术栈与依赖架构

- **后端框架**: [FastAPI](https://fastapi.tiangolo.com/) (极速的异步 Python Web 框架)
- **底层大模型**: [OpenAI 兼容接口] (推荐接入 DeepSeek / Kimi / MiniMax 等基座大模型)
- **数据处理**: Pandas, Openpyxl (用于结构化数据过滤与 Excel 生成)
- **前端页面**: 原生 Vanilla JS + CSS (采用响应式布局，支持暗色模式微调，内置 HTML2PDF 引擎)
- **数据库支撑**: **MySQL** (通过 `PyMySQL` 和 `SQLAlchemy` 连接，在 `utils/db_helper.py` 中接入企业内部数据中台结构，并内置连接池实现高并发)

---

## 🚀 快速启动指南 (Quick Start)

### 1. 环境准备
请确保您的计算机或服务器上已安装 **Python 3.10+**。

克隆或下载本项目至本地后，安装必要的依赖：
```bash
pip install -r requirements.txt
```

### 2. 配置环境变量
在项目根目录下创建一个 `.env` 文件（可参考现有代码），填入您的大模型 API 密钥信息：
```ini
# 大模型配置
DEEPSEEK_API_KEY="your-deepseek-api-key"
DEEPSEEK_API_BASE="https://api.deepseek.com"
OPENAI_MODEL_NAME="deepseek-chat"

# 业务数据库连接配置 (必填)
DB_HOST="127.0.0.1"
DB_PORT="3306"
DB_USER="root"
DB_PASSWORD="your_password"
DB_NAME="zq_ai"
DB_CHARSET="utf8mb4"
DATABASE_URL="mysql+pymysql://root:your_password@127.0.0.1:3306/zq_ai?charset=utf8mb4"

# Elasticsearch 日志存储配置 (可选)
ES_HOST="https://your-es-endpoint:9200"
ES_USER="elastic"
ES_PASSWORD="your_es_password"
ES_INDEX="customer_insight_agent_logs"
```
*(注：如果未配置 API Key，系统内置了强大的本地字典树回退路由引擎（Fallback Parser），依然可以完成大部分基本演示流程。)*

### 3. 运行服务
在终端运行以下命令启动服务：
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 访问系统
服务启动后，打开浏览器访问：
- **智能交互终端**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## 📂 项目目录结构说明

```text
├── app.py                     # FastAPI 核心入口程序与 SSE 流处理逻辑
├── router.py                  # AI 路由引擎 (处理意图分类与实体提取)
├── requirements.txt           # 项目运行依赖库
├── services/                  # 核心业务逻辑层
│   ├── industry.py            # 行业报告生成模块
│   ├── potential.py           # 高潜客户挖掘与 Excel 导出模块
│   └── regional.py            # 区域商机分析报告模块
├── utils/                     # 工具类
│   ├── db_helper.py           # 数据库统一操作网关与连接池
│   ├── mock_db.py             # 静态全备数据 / 兜底模板
│   └── file_helper.py         # 磁盘操作与企业机器人 Webhook 推送等工具
├── static/                    # 静态资源存放目录
│   ├── index.html             # 业务人员使用的前端主视图界面
│   ├── ui_1.html              # 扩展的详细图表 / 大屏展示页
│   └── generated/             # 系统自动生成产出的 HTML 报告与 Excel 下载文件(gitignore)
└── data/                      # 存放 sqlite 等本地化数据库源文件 (若有)
```

---

## 📦 生产环境部署建议

如果您需要将此项目部署到企业级云主机上供长期使用：
1. **Linux 服务器**：支持 Ubuntu / CentOS / Debian 等主流 Linux 发行版。
2. **守护进程**：推荐使用 `Systemd` 或 `Supervisor` 托管 Uvicorn 进程，确保 7x24 小时运行。
3. **反向代理**：推荐在 8000 端口前置一台 **Nginx**，通过配置 `proxy_pass` 进行转发，并挂载正式域名及 SSL 证书。

---

> **Design by:** 交付团队
> **License:** 内部商业交付代码，未经授权请勿开源散播。
