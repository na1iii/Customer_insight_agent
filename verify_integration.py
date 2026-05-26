# -*- coding: utf-8 -*-
import sys
import os
import requests
import json

def test_api():
    print("=== Testing API Endpoints ===")
    
    # 1. Register and Login a test user
    url_reg = "http://127.0.0.1:8000/api/auth/register"
    username = "test_user_integration_123"
    password = "password123"
    
    try:
        res = requests.post(url_reg, json={"username": username, "password": password})
        print(f"Register status: {res.status_code}, body: {res.json()}")
    except Exception as e:
        print(f"Register error (might already exist): {e}")

    url_login = "http://127.0.0.1:8000/api/auth/login"
    res = requests.post(url_login, json={"username": username, "password": password})
    print(f"Login status: {res.status_code}, body: {res.json()}")
    login_data = res.json()
    user_id = login_data["user"]["id"]
    
    # 2. Rebuild opportunity articles to make sure we have data
    print("Rebuilding articles via API...")
    url_rebuild = "http://127.0.0.1:8000/api/articles/rebuild"
    # Rebuild limit 10 for fast test
    res = requests.post(url_rebuild, json={}, params={"limit": 20, "clear_existing": True})
    print(f"Rebuild status: {res.status_code}")
    if res.status_code == 200:
        print(f"Rebuild body: {res.json()}")
    else:
        print(f"Rebuild error body: {res.text}")
        
    # Get articles count
    url_articles = "http://127.0.0.1:8000/api/articles"
    res = requests.get(url_articles)
    data = res.json()
    total_count = data.get("total_count", 0) if isinstance(data, dict) else len(data)
    print(f"Articles status: {res.status_code}, count: {total_count}")
    if res.status_code == 200:
        if isinstance(data, dict):
            groups = data.get("groups", [])
            if groups and groups[0].get("articles"):
                print(f"Sample article: {groups[0]['articles'][0]}")
        elif len(data) > 0:
            print(f"Sample article: {data[0]}")

    # 3. Create a conversation
    url_conv = f"http://127.0.0.1:8000/api/conversations?user_id={user_id}&scene=general&title=TestConv"
    res = requests.post(url_conv)
    print(f"Create conversation status: {res.status_code}, body: {res.json()}")
    conv_id = res.json()["id"]
    
    # 4. Send chat message: "全市商机" (for regional_report intent)
    print("\n--- Testing Chat: 全市商机 ---")
    url_chat = "http://127.0.0.1:8000/api/chat"
    payload = {
        "message": "全市商机",
        "scene": "general",
        "conversation_id": conv_id,
        "user_id": user_id
    }
    res = requests.post(url_chat, json=payload, stream=True)
    print(f"Chat status: {res.status_code}")
    for line in res.iter_lines():
        if line:
            decoded_line = line.decode('utf-8')
            if decoded_line.startswith("data: "):
                data_str = decoded_line[6:]
                try:
                    data = json.loads(data_str)
                    print(f"Event: {data.get('type')} -> {data.get('content') or data.get('resolved_scene') or data.get('payload') or data.get('message')}")
                except Exception as e:
                    print(f"Could not parse: {decoded_line}")
                    
    # 5. Send chat message: "高潜客户推荐" (for high_potential intent)
    print("\n--- Testing Chat: 高潜客户推荐 ---")
    payload["message"] = "高潜客户推荐"
    res = requests.post(url_chat, json=payload, stream=True)
    print(f"Chat status: {res.status_code}")
    for line in res.iter_lines():
        if line:
            decoded_line = line.decode('utf-8')
            if decoded_line.startswith("data: "):
                data_str = decoded_line[6:]
                try:
                    data = json.loads(data_str)
                    print(f"Event: {data.get('type')} -> {data.get('content') or data.get('resolved_scene') or data.get('payload') or data.get('message')}")
                except Exception as e:
                    print(f"Could not parse: {decoded_line}")

    # 6. Test Export excel
    print("\n--- Testing Export Excel ---")
    url_export = "http://127.0.0.1:8000/api/potential/export"
    res = requests.get(url_export, params={"score_min": 55, "user_id": user_id})
    print(f"Export Excel status: {res.status_code}, content-type: {res.headers.get('content-type')}, length: {len(res.content)}")

if __name__ == "__main__":
    test_api()
