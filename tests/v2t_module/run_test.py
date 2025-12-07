#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests

def load_test_config():
    tests_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg_path = os.path.join(tests_dir, 'test_config.json')
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def test_video_comprehension():
    """测试视频理解接口"""
    
    # 测试数据
    cfg = load_test_config()
    api_key = (cfg.get('v2t_module', {}) or {}).get('api_key', '')
    test_data = {
        "api_key": api_key,
        "video_url": "https://fuwei-test.tos-cn-beijing.volces.com/yiwise/%E5%BE%85%E5%88%86%E6%9E%90%E8%A7%86%E9%A2%91.mp4",
        "prompt": "请描述这个视频的内容"
    }
    
    print("发送测试请求...")
    print(f"请求数据: {test_data}")
    
    try:
        response = requests.post(
            "http://localhost:8000/video_comprehension_gen_text",
            headers={"Content-Type": "application/json"},
            json=test_data,
            timeout=10
        )
        
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        if response.headers.get('content-type', '').startswith('application/json'):
            try:
                response_json = response.json()
                print(f"解析后的JSON: {json.dumps(response_json, indent=2, ensure_ascii=False)}")
            except:
                print("无法解析为JSON")
                
    except Exception as e:
        print(f"请求失败: {e}")

if __name__ == "__main__":
    test_video_comprehension()
