# -*- coding: utf-8 -*-
"""
file_helper.py - 通用辅助库，处理文件目录、字体、绘图以及外部机器人推送
"""

import os
import requests

def ensure_dir(dir_path: str):
    """确保目标文件夹存在"""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)

def send_to_webhook(webhook_url: str, text: str, file_url: str = None) -> dict:
    """
    向群消息机器人（微信/飞书/钉钉）Webhook 发送消息通知
    """
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"### 📊 智能客户洞察报告已生成\n\n{text}"
        }
    }
    if file_url:
        payload["markdown"]["content"] += f"\n\n📎 **报告下载链接**: [点击下载]({file_url})"
        
    try:
        print("\n" + "="*50)
        print(f"【SIMULATED WEBHOOK】")
        print(f"Webhook URL: {webhook_url or '未配置（仅本地模拟）'}")
        try:
            print(f"Payload: {payload}")
        except Exception:
            try:
                safe_payload = str(payload).encode('gbk', errors='replace').decode('gbk')
                print(f"Payload: {safe_payload}")
            except Exception:
                print(f"Payload: <Unable to print due to encoding>")
        print("="*50 + "\n")
    except Exception:
        pass
    
    if not webhook_url or "your_webhook_here" in webhook_url:
        return {"status": "mock_success", "payload": payload}
        
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        return {
            "status": "success" if response.status_code == 200 else "failed",
            "code": response.status_code,
            "response": response.text
        }
    except Exception as e:
        print(f"【Webhook Error】发送失败: {e}")
        return {"status": "failed", "error": str(e)}
