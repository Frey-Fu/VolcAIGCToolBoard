# -*- coding: utf-8 -*-
import json
import urllib.request
import urllib.error
import re
from typing import Dict, Any
import traceback

from .base_module import BaseModule
from .tos_utils import TOSUploader

class V2TModule(BaseModule):
    def __init__(self, config: Dict[str, Any] = None):
        BaseModule.__init__(self, "v2t_module", config)
        vc = self.config.get('v2t_module', {})
        self.api_endpoint = vc.get('endpoint', 'https://ark.cn-beijing.volces.com/api/v3/chat/completions')
        self.api_timeout = vc.get('timeout', 60)
        self.config_api_key = vc.get('api_key', '').strip()
        tos_config = self.config.get('tos', {})
        self.tos_uploader = TOSUploader(bucket=tos_config.get('bucket_name'), region=tos_config.get('region'), enable_cache=True)
        limits = self.config.get('limits', {})
        self.max_file_size = limits.get('max_file_size_mb', 100) * 1024 * 1024

    def get_routes(self) -> Dict[str, callable]:
        return {
            '/video_comprehension_gen_text': self.handle_video_comprehension_gen_text,
            '/upload_video': self.handle_upload_video
        }

    def handle_request(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        try:
            self._log_if_enabled('request_log', 'info', f"path={path} method={method} content_type={headers.get('Content-Type') or headers.get('content-type')} body_len={len(body) if body else 0}")
            if path == '/video_comprehension_gen_text' and method == 'POST':
                return self.handle_video_comprehension_gen_text(path, method, headers, body)
            elif path == '/upload_video' and method == 'POST':
                return self.handle_upload_video(path, method, headers, body)
            else:
                return self.send_error_response(404, "路径未找到")
        except Exception as e:
            if self._should_log('error_traceback'):
                self.logger.error(traceback.format_exc())
            return self.send_error_response(500, f"上传视频失败: {str(e)}")

    def upload_to_tos(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        return self.tos_uploader.upload_file(file_content, filename, set_public_read=True)

    def handle_video_comprehension_gen_text(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        try:
            content_type = headers.get('content-type', '')
            self._log_if_enabled('request_log', 'info', f"gen_text content_type={content_type} body_len={len(body) if body else 0}")
            try:
                if body:
                    data = json.loads(body.decode('utf-8'))
                    api_key = data.get('api_key', '').strip()
                    video_url = data.get('video_url', '').strip()
                    prompt = data.get('prompt', '').strip()
                    fps = data.get('fps', 1.0)
                else:
                    raise ValueError("请求体为空")
            except (json.JSONDecodeError, ValueError):
                if 'multipart/form-data' in content_type:
                    form_data = self.parse_multipart_form_data(content_type, body)
                    api_key = form_data.get('api_key', [''])[0].strip() if 'api_key' in form_data else ''
                    video_url = form_data.get('video_url', [''])[0].strip() if 'video_url' in form_data else ''
                    prompt = form_data.get('prompt', [''])[0].strip() if 'prompt' in form_data else ''
                    fps = float(form_data.get('fps', ['1.0'])[0]) if 'fps' in form_data else 1.0
                else:
                    return self.send_error_response(400, "无效的请求格式")
            if not api_key and not self.config_api_key:
                return self.send_error_response(400, "API Key 不能为空")
            if not video_url:
                return self.send_error_response(400, "视频URL不能为空")
            if not prompt:
                return self.send_error_response(400, "提示词不能为空")
            final_api_key = self.config_api_key if self.config_api_key else api_key
            result = self.call_video_comprehension_api(final_api_key, video_url, prompt, fps)
            if result['success']:
                return self.send_json_response(200, {'success': True, 'message': '视频理解完成', 'result': result['content']})
            else:
                self._log_if_enabled('error_traceback', 'error', f"gen_text_failed error={result.get('error')} upstream={result.get('upstream_error')} raw={result.get('error_response_content')}")
                return self.build_error_response(500, result.get('error', '视频理解失败'), result.get('upstream_error'), result.get('error_response_content'))
        except json.JSONDecodeError:
            return self.send_error_response(400, "JSON格式错误")
        except Exception as e:
            if self._should_log('error_traceback'):
                self.logger.error(traceback.format_exc())
            return self.send_error_response(500, f"处理请求失败: {str(e)}")

    def handle_upload_video(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        try:
            content_type = headers.get('content-type', '')
            self._log_if_enabled('request_log', 'info', f"upload_video content_type={content_type} body_len={len(body) if body else 0}")
            form_data = self.parse_multipart_form_data(content_type, body)
            if 'video' not in form_data:
                return self.send_error_response(400, "未找到视频文件")
            file_info = form_data['video'][0]
            if not isinstance(file_info, dict) or 'content' not in file_info:
                return self.send_error_response(400, "视频文件格式错误")
            filename = file_info.get('filename', '')
            if not any(filename.lower().endswith(ext) for ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']):
                return self.send_error_response(400, "不支持的视频格式，请上传mp4、avi、mov、mkv或webm格式的视频")
            file_content = file_info['content']
            if len(file_content) > 100 * 1024 * 1024:
                return self.send_error_response(400, "视频文件大小不能超过100MB")
            upload_result = self.upload_to_tos(file_content, filename)
            if upload_result['success']:
                return self.send_json_response(200, {"success": True, "url": upload_result['url'], "message": "视频上传成功"})
            else:
                self._log_if_enabled('error_traceback', 'error', f"upload_failed error={upload_result['error']}")
                return self.send_error_response(500, f"视频上传失败: {upload_result['error']}")
        except Exception as e:
            if self._should_log('error_traceback'):
                self.logger.error(traceback.format_exc())
            return self.send_error_response(500, f"上传失败: {str(e)}")

    def call_video_comprehension_api(self, api_key: str, video_url: str, prompt: str, fps: float = 1.0) -> Dict[str, Any]:
        try:
            request_data = {
                "model": self.config.get('v2t_module', {}).get('model', 'doubao-seed-1-6-vision-250815'),
                "messages": [
                    {
                        "content": [
                            {"video_url": {"url": video_url, "fps": fps}, "type": "video_url"},
                            {"text": prompt, "type": "text"}
                        ],
                        "role": "user"
                    }
                ],
            }
            request_json = json.dumps(request_data, indent=2, ensure_ascii=False).encode('utf-8')
            req = urllib.request.Request(self.api_endpoint, data=request_json, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'})
            with urllib.request.urlopen(req, timeout=self.api_timeout) as response:
                response_body = response.read().decode('utf-8')
                response_data = json.loads(response_body)
                if 'choices' in response_data and len(response_data['choices']) > 0:
                    content = response_data['choices'][0]['message']['content']
                    return {'success': True, 'content': content}
                else:
                    self._log_if_enabled('error_traceback', 'error', f"api_no_choices raw={response_body}")
                    return {'success': False, 'error': '未获取到有效响应'}
        except urllib.error.HTTPError as e:
            error_msg = f"API请求失败: HTTP {e.code}"
            try:
                error_body = e.read().decode('utf-8')
                error_response = json.loads(error_body)
                upstream = error_response.get('error') if isinstance(error_response.get('error'), dict) else None
                self._log_if_enabled('error_traceback', 'error', f"api_http_error code={e.code} raw={error_body}")
                return {'success': False, 'error': error_msg, 'upstream_error': upstream, 'error_response_content': error_body}
            except Exception:
                self._log_if_enabled('error_traceback', 'error', f"api_http_error_parse_failed code={e.code}")
                return {'success': False, 'error': error_msg, 'error_response_content': None}
        except urllib.error.URLError as e:
            error_msg = f"网络连接失败: {str(e)}"
            self._log_if_enabled('error_traceback', 'error', error_msg)
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"调用API时发生错误: {str(e)}"
            if self._should_log('error_traceback'):
                self.logger.error(traceback.format_exc())
            return {'success': False, 'error': error_msg}

    def parse_multipart_form_data(self, content_type: str, body: bytes) -> Dict[str, list]:
        try:
            if not content_type or 'multipart/form-data' not in content_type:
                if body and body.startswith(b'--'):
                    first_line = body.split(b'\r\n')[0]
                    if first_line.startswith(b'--'):
                        boundary = first_line[2:].decode('utf-8', errors='ignore')
                    else:
                        return {}
                else:
                    return {}
            else:
                boundary_match = re.search(r'boundary=([^;]+)', content_type)
                if not boundary_match:
                    return {}
                boundary = boundary_match.group(1).strip('"')
            boundary_bytes = ('--' + boundary).encode('utf-8')
            parts = body.split(boundary_bytes)
            form_data = {}
            for part in parts[1:-1]:
                if not part.strip():
                    continue
                if b'\r\n\r\n' in part:
                    headers_section, content = part.split(b'\r\n\r\n', 1)
                    content = content.rstrip(b'\r\n')
                    headers_text = headers_section.decode('utf-8', errors='ignore')
                    name_match = re.search(r'name="([^"]+)"', headers_text)
                    filename_match = re.search(r'filename="([^"]+)"', headers_text)
                    if name_match:
                        field_name = name_match.group(1)
                        if filename_match:
                            filename = filename_match.group(1)
                            form_data[field_name] = [{'content': content, 'filename': filename}]
                        else:
                            field_value = content.decode('utf-8', errors='ignore')
                            if field_name not in form_data:
                                form_data[field_name] = []
                            form_data[field_name].append(field_value)
            return form_data
        except Exception:
            return {}
