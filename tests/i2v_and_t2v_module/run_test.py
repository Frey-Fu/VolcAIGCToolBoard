#!/usr/bin/env python3
import os
import sys
import time
import json
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from modules.tos_utils import TOSUploader
def log_info(message: str):
    """记录信息日志"""
    print(f"[INFO] {time.strftime('%Y-%m-%d %H:%M:%S')} - {message}")

def log_error(message: str):
    """记录错误日志"""
    print(f"[ERROR] {time.strftime('%Y-%m-%d %H:%M:%S')} - {message}")
def load_config():
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'test_config.json')
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def post_json(url, data, timeout=30):
    r = requests.post(url, headers={'Content-Type': 'application/json'}, json=data, timeout=timeout)
    return r.status_code, r.text, (r.headers.get('content-type') or '').lower(), (r.json() if r.headers.get('content-type','').startswith('application/json') else None)

def post_multipart(url, fields, files, timeout=30):
    r = requests.post(url, data=fields, files=files, timeout=timeout)
    return r.status_code, r.text, (r.headers.get('content-type') or '').lower(), (r.json() if r.headers.get('content-type','').startswith('application/json') else None)

def query_status(base_url, task_id, attempts=60, interval=10):
    for _ in range(attempts):
        rr = requests.get(f"{base_url}/video_task_status/{task_id}", timeout=10)
        if rr.status_code == 200:
            try:
                data = rr.json()
            except Exception:
                time.sleep(interval)
                continue
            status = data.get('status') or data.get('task_status') or data.get('state')
            if status in ['succeeded','completed','success']:
                return True, data
            if status in ['failed','error']:
                return False, data
            time.sleep(interval)
            continue
        time.sleep(interval)
    return False, None

def test_text_to_video(base_url, cfg):
    api_key = (cfg.get('i2v_and_t2v_module', {}) or {}).get('ark_api_key', '')
    data = {
        'api_key': api_key,
        'prompt': '一只猫',
        'resolution': '480p',
        'aspect_ratio': '16:9',
        'duration': 3,
        'seed': -1,
        'fixed_camera': False,
        'model_type': 'lite'
    }
    sc, txt, ct, js = post_json(f"{base_url}/text_to_video", data, timeout=int(os.environ.get('T2V_TEST_TIMEOUT','60')))
    if sc != 200:
        return False, {'status_code': sc, 'body': txt}
    task_id = (js or {}).get('task_id') or (js or {}).get('id')
    if not task_id:
        return False, {'error': 'no task_id', 'body': js}
    ok, result = query_status(base_url, task_id)
    return ok, result

def test_image_to_video_first_frame(base_url, cfg):
    api_key = (cfg.get('i2v_and_t2v_module', {}) or {}).get('ark_api_key', '')
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    # 优先使用本目录图片，其次尝试 tests/tosutil
    img_path = os.path.join(tests_dir, '人物 1.jpeg')
    if not os.path.exists(img_path):
        alt_path = os.path.join(os.path.dirname(tests_dir), 'tosutil', '人物 1.jpeg')
        img_path = alt_path if os.path.exists(alt_path) else img_path
    if not os.path.exists(img_path):
        return False, {'error': f'missing image {img_path}'}
    # 上传到TOS获取URL
    tos_cfg = cfg.get('tos', {})
    bucket = tos_cfg.get('bucket_name')
    region = tos_cfg.get('region')
    if not bucket or not region:
        return False, {'error': 'missing tos.bucket_name or tos.region in tests/test_config.json'}
    uploader = TOSUploader(bucket=bucket, region=region, enable_cache=True)
    with open(img_path, 'rb') as f:
        up = uploader.upload_file(f.read(), os.path.basename(img_path), set_public_read=True)
    if not up.get('success'):
        return False, {'error': f"tos upload failed: {up.get('error')}"}
    first_url = up.get('url')
    fields = {
        'prompt': '依据首帧生成视频',
        'video_type': 'image_to_video_first_frame',
        'api_key': api_key,
        'resolution': '480p',
        'aspect_ratio': '16:9',
        'duration': '3',
        'seed': '-1',
        'first_frame_url': first_url
    }
    log_info(f"fields: {fields}")

    sc, txt, ct, js = post_json(f"{base_url}/text_to_video", fields, timeout=int(os.environ.get('T2V_TEST_TIMEOUT','60')))
    # sc, txt, ct, js = post_json(f"{base_url}/image_to_video_advanced", fields, timeout=int(os.environ.get('I2V_TEST_TIMEOUT','60')))
    if sc != 200:
        return False, {'status_code': sc, 'body': txt}
    task_id = (js or {}).get('task_id') or (js or {}).get('id')
    if not task_id:
        return False, {'error': 'no task_id', 'body': js}
    ok, result = query_status(base_url, task_id)
    return ok, result

def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000'
    cfg = load_config()
    ok1, r1 = test_text_to_video(base_url, cfg)
    print(json.dumps({'case':'text_to_video','success': ok1, 'result': r1}, ensure_ascii=False, indent=2))
    ok2 = 1
    # ok2, r2 = test_image_to_video_first_frame(base_url, cfg)
    # print(json.dumps({'case':'image_to_video_first_frame','success': ok2, 'result': r2}, ensure_ascii=False, indent=2))
    sys.exit(0 if (ok1 and ok2) else 1)

if __name__ == '__main__':
    main()
