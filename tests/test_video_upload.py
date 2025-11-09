#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json

def test_video_comprehension():
    """测试视频理解接口"""
    
    # 测试数据
    test_data = {
        "api_key": "test_key",
        "video_url": "https://example.com/test.mp4",
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