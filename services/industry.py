# -*- coding: utf-8 -*-
"""
industry.py - 场景3：行业报告。AI 生成大纲，输出精美 HTML 报告，并调用 Webhook 发送到群里。
"""

import os
import json
from openai import OpenAI
from utils.mock_db import INDUSTRIES
from utils.file_helper import ensure_dir, send_to_webhook
import utils.db_helper as db

def generate_html_report(dest_path: str, title: str, summary: str, chapters: list) -> str:
    """
    生成高颜值的 A4 排版 HTML 报告，集成打印功能，避免中文字体乱码问题。
    """
    chapters_html = ""
    for ch in chapters:
        ch_title = ch.get("title", "")
        ch_content = ch.get("content", "").replace("\n", "<br/>")
        chapters_html += f"""
        <div class="chapter">
            <h2>{ch_title}</h2>
            <p>{ch_content}</p>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Noto+Sans+SC:wght@300;400;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --primary: #1e3a8a;
            --primary-dark: #0f172a;
            --secondary: #2563eb;
            --text-main: #334155;
            --text-dark: #0f172a;
            --bg-light: #f8fafc;
            --border-color: #e2e8f0;
        }}
        body {{
            font-family: 'Outfit', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: var(--text-main);
            background-color: var(--bg-light);
            line-height: 1.6;
            margin: 0;
            padding: 40px 20px;
        }}
        .report-card {{
            max-width: 800px;
            margin: 0 auto;
            background: #ffffff;
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 50px 60px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.05);
        }}
        .header {{
            text-align: center;
            border-bottom: 2px solid var(--border-color);
            padding-bottom: 30px;
            margin-bottom: 30px;
        }}
        h1 {{
            font-size: 28px;
            color: var(--primary-dark);
            margin: 0 0 15px 0;
            font-weight: 700;
        }}
        .metadata {{
            font-size: 14px;
            color: #64748b;
        }}
        .summary-box {{
            background-color: #f8fafc;
            border-left: 4px solid var(--secondary);
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 40px;
            font-size: 15px;
            color: var(--text-dark);
            border: 1px solid var(--border-color);
            border-left-width: 4px;
        }}
        .summary-box h3 {{
            margin: 0 0 10px 0;
            color: var(--primary);
            font-size: 16px;
        }}
        .chapter {{
            margin-bottom: 35px;
        }}
        .chapter h2 {{
            font-size: 18px;
            color: var(--primary);
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
            margin-top: 0;
            margin-bottom: 15px;
        }}
        .chapter p {{
            margin: 0;
            font-size: 14.5px;
            text-align: justify;
            color: var(--text-main);
            line-height: 1.8;
        }}
        .footer {{
            margin-top: 50px;
            border-top: 1px solid var(--border-color);
            padding-top: 20px;
            text-align: center;
            font-size: 12px;
            color: #94a3b8;
        }}
        
        /* Floating print button styling */
        .actions-bar {{
            max-width: 800px;
            margin: 0 auto 20px auto;
            display: flex;
            justify-content: flex-end;
        }}
        .btn {{
            background: linear-gradient(135deg, var(--secondary) 0%, var(--primary) 100%);
            color: white;
            border: none;
            padding: 10px 20px;
            font-size: 14px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 6px rgba(37, 99, 235, 0.2);
        }}
        .btn:hover {{
            transform: translateY(-1px);
            box-shadow: 0 6px 12px rgba(37, 99, 235, 0.3);
        }}
        
        /* Print rules */
        @media print {{
            body {{
                background-color: white;
                padding: 0;
                color: black;
            }}
            .report-card {{
                border: none;
                box-shadow: none;
                padding: 0;
                max-width: 100%;
            }}
            .no-print {{
                display: none !important;
            }}
            @page {{
                size: A4;
                margin: 20mm;
            }}
            .chapter {{
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
    <div class="actions-bar no-print">
        <button class="btn" onclick="window.print()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"></polyline><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path><rect x="6" y="14" width="12" height="8"></rect></svg>
            打印或保存为 PDF
        </button>
    </div>
    
    <div class="report-card">
        <div class="header">
            <h1>{title}</h1>
            <div class="metadata">AI智能体客户洞察项目组 | 行业深度研究报告</div>
        </div>
        
        <div class="summary-box">
            <h3>前言导读</h3>
            <p>{summary}</p>
        </div>
        
        {chapters_html}
        
        <div class="footer">
            © 2026 AI智能体客户洞察项目组 | 本报告由大模型辅助生成，仅供决策参考
        </div>
    </div>
</body>
</html>
"""
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return dest_path

def handle(keyword: str, user_id: int = None) -> dict:
    """
    生成行业深度报告 HTML，并自动推送至机器人 Webhook。返回报告访问链接。
    """
    if not keyword:
        keyword = "通信行业"
        
    # 查找匹配的行业数据
    industry_data = None
    matched_key = None
    for k, v in INDUSTRIES.items():
        if keyword in k or k in keyword:
            industry_data = v
            matched_key = k
            break
            
    if not industry_data:
        industry_data = INDUSTRIES["通信行业"]
        matched_key = "通信行业"
        
    db.log_event(user_id, "industry", "INFO", f"开始为行业 '{matched_key}' 生成 HTML 深度分析报告。")
        
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    
    # HTML 文件物理保存路径
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(base_dir, "static", "generated")
    ensure_dir(static_dir)
    
    filename = f"industry_report_{matched_key}.html"
    dest_path = os.path.join(static_dir, filename)
    web_url = f"/static/generated/{filename}"
    
    title = industry_data["title"]
    summary = industry_data["summary"]
    chapters = industry_data["chapters"]
    
    # 1. 尝试使用 AI 深度扩写章节内容
    if api_key and "your_api_key" not in api_key:
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            prompt = (
                f"你是一个行业资深分析师。请针对行业报告《{title}》，根据以下大纲及要点信息，"
                f"进行内容深度充实与专业润色，每个章节字数扩写至 300 字左右。\n\n"
                f"【报告基本结构】:\n"
                f"导读摘要: {summary}\n"
                f"章节大纲: {json.dumps(chapters, ensure_ascii=False)}\n\n"
                f"要求：返回一个 JSON 数组，格式必须与章节大纲完全一致，仅包含 'title' 和 'content' 字段。例如：\n"
                f"[{{\"title\": \"一、...\", \"content\": \"扩写后的段落一...\"}}, ...]\n"
                f"注意：只返回标准的 JSON 数据，不要包含 ```json markdown 块包裹，也不要有任何其他解释性话语。"
            )
            
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "你是一个严谨的行业报告大牛，只会输出干净合法的 JSON 数据。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                timeout=10.0
            )
            
            content = response.choices[0].message.content
            parsed_chapters = json.loads(content)
            if isinstance(parsed_chapters, list) and len(parsed_chapters) > 0:
                chapters = parsed_chapters
            elif isinstance(parsed_chapters, dict) and "chapters" in parsed_chapters:
                chapters = parsed_chapters["chapters"]
            db.log_event(user_id, "industry", "INFO", "成功调用 DeepSeek 大模型对行业报告大纲进行了扩写与润色。")
        except Exception as e:
            db.log_event(user_id, "industry", "WARNING", f"DeepSeek 行业报告 AI 扩写服务异常: {e}，降级使用本地预置大纲生成 HTML。")

    # 2. 渲染生成 HTML
    generate_html_report(dest_path, title, summary, chapters)
    db.log_event(user_id, "industry", "INFO", f"HTML 报告文档编译成功，已写入本地: {dest_path}")
    
    # 3. 触发 Webhook 机器人推送
    webhook_url = os.getenv("ROBOT_WEBHOOK_URL", "")
    full_download_url = f"http://127.0.0.1:8000{web_url}"
    
    push_text = (
        f"**报告名称**：《{title}》\n"
        f"**覆盖行业**：{matched_key}\n"
        f"**核心摘要**：{summary[:90]}..."
    )
    
    webhook_status = send_to_webhook(webhook_url, push_text, full_download_url)
    db.log_event(user_id, "industry", "INFO", f"企业聊天机器人 Webhook 推送执行完毕，状态: {webhook_status['status']}", json.dumps(webhook_status, ensure_ascii=False))
    
    return {
        "type": "file_link",
        "file_type": "html",
        "title": title,
        "url": web_url,
        "full_url": full_download_url,
        "webhook_pushed": webhook_status["status"] == "success" or "mock" in webhook_status["status"]
    }
