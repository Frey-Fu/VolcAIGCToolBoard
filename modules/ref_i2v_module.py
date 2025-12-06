# -*- coding: utf-8 -*-
import json
import urllib.request
import urllib.error
import re
import traceback
from typing import Dict, Any

from .base_module import BaseModule
from .tos_utils import TOSUploader

class RefI2VModule(BaseModule):
    def __init__(self, config: Dict[str, Any] = None):
        BaseModule.__init__(self, "ref_i2v_module", config)
        node = self.config.get('ref_i2v_module', {})
        self.api_endpoint = node.get('endpoint', 'https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks')
        self.api_timeout = node.get('timeout', 30)
        self.config_api_key = node.get('api_key', '').strip()
        tos_config = self.config.get('tos', {})
        self.tos_uploader = TOSUploader(bucket=tos_config.get('bucket_name'), region=tos_config.get('region'), enable_cache=True)
        limits = self.config.get('limits', {})
        self.max_file_size = limits.get('max_file_size_mb', 10) * 1024 * 1024
        self.max_images = limits.get('max_images', 4)

    def get_routes(self) -> Dict[str, callable]:
        return {
            '/generate_video': self.handle_generate_video,
            '/task_status/': self.handle_task_status,
            '/upload_image': self.handle_upload_image,
            '/upload_and_create_task': self.handle_upload_and_create_task
        }

    def handle_request(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        try:
            self._log_if_enabled('request_log', 'info', f"path={path} method={method} content_type={headers.get('Content-Type') or headers.get('content-type')} body_len={len(body) if body else 0}")
            if path.startswith('/task_status/'):
                return self.handle_task_status(path, method, headers, body)
            elif path == '/generate_video' and method == 'POST':
                return self.handle_generate_video(path, method, headers, body)
            elif path == '/upload_image' and method == 'POST':
                return self.handle_upload_image(path, method, headers, body)
            elif path == '/upload_and_create_task' and method == 'POST':
                return self.handle_upload_and_create_task(path, method, headers, body)
            else:
                return self.send_error_response(404, "路径未找到")
        except Exception as e:
            if self._should_log('error_traceback'):
                self.logger.error(traceback.format_exc())
            return self.send_error_response(500, f"服务器内部错误: {str(e)}")

    def handle_task_status(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        try:
            task_id = path.split('/task_status/')[-1]
            if not task_id:
                return self.send_error_response(400, "缺少任务ID")
            query_url = f"{self.api_endpoint}/{task_id}"
            api_key = self.config_api_key
            if not api_key and 'authorization' in headers:
                api_key = headers['authorization'].replace('Bearer ', '')
            if not api_key:
                return self.send_error_response(400, "缺少API Key")
            req = urllib.request.Request(query_url)
            req.add_header('Authorization', f'Bearer {api_key}')
            req.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req, timeout=self.api_timeout) as response:
                result = json.loads(response.read().decode('utf-8'))
                return self.send_json_response(200, result)
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8') if e.fp else str(e)
            upstream = self.parse_upstream_error(raw)
            self._log_if_enabled('error_traceback', 'error', f"status_http_error code={e.code} raw={raw}")
            return self.build_error_response(e.code, "API请求失败", upstream, raw)
        except Exception as e:
            return self.send_error_response(500, f"查询任务状态失败: {str(e)}")

    def handle_generate_video(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        try:
            if not body:
                return self.send_error_response(400, "请求体为空")
            content_type = headers.get('Content-Type', '') or headers.get('content-type', '')
            self._log_if_enabled('request_log', 'info', f"generate content_type={content_type}")
            form_data = self.parse_multipart_form_data(content_type, body)
            if not form_data:
                return self.send_error_response(400, "无法解析表单数据")
            prompt = form_data.get('prompt', [''])[0]
            api_key = form_data.get('api_key', [''])[0] or self.config_api_key
            if not api_key:
                return self.send_error_response(400, "缺少API Key")
            if not prompt:
                return self.send_error_response(400, "缺少提示词")
            image_urls = []
            for i in range(1, self.max_images + 1):
                file_key = f'reference_image_{i}'
                if file_key in form_data:
                    file_info = form_data[file_key][0]
                    if isinstance(file_info, dict) and 'content' in file_info:
                        upload_result = self.upload_to_tos(file_info['content'], file_info.get('filename', f'image_{i}.jpg'))
                        if upload_result['success']:
                            image_urls.append(upload_result['url'])
                        else:
                            self._log_if_enabled('error_traceback', 'error', f"upload_failed i={i} error={upload_result['error']}")
                            return self.send_error_response(500, f"图片上传失败: {upload_result['error']}")
            if not image_urls:
                return self.send_error_response(400, "至少需要上传一张参考图片")
            api_data = {"model": "doubao-video-pro", "prompt": prompt, "reference_images": image_urls}
            req = urllib.request.Request(self.api_endpoint)
            req.add_header('Authorization', f'Bearer {api_key}')
            req.add_header('Content-Type', 'application/json')
            json_data = json.dumps(api_data).encode('utf-8')
            with urllib.request.urlopen(req, data=json_data, timeout=self.api_timeout) as response:
                result = json.loads(response.read().decode('utf-8'))
                return self.send_json_response(200, {"success": True, "task_id": result.get('id'), "message": "视频生成任务已提交", "data": result})
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8') if e.fp else str(e)
            upstream = self.parse_upstream_error(raw)
            self._log_if_enabled('error_traceback', 'error', f"generate_http_error code={e.code} raw={raw}")
            return self.build_error_response(e.code, "API请求失败", upstream, raw)
        except Exception as e:
            if self._should_log('error_traceback'):
                self.logger.error(f"生成视频时发生错误: {traceback.format_exc()}")
            return self.send_error_response(500, f"生成视频失败: {str(e)}")

    def handle_upload_image(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        try:
            if not body:
                return self.send_error_response(400, "请求体为空")
            content_type = headers.get('content-type', '')
            form_data = self.parse_multipart_form_data(content_type, body)
            if not form_data or 'image' not in form_data:
                return self.send_error_response(400, "未找到图片文件")
            file_info = form_data['image'][0]
            if not isinstance(file_info, dict) or 'content' not in file_info:
                return self.send_error_response(400, "图片文件格式错误")
            upload_result = self.upload_to_tos(file_info['content'], file_info.get('filename', 'uploaded_image.jpg'))
            if upload_result['success']:
                return self.send_json_response(200, {"success": True, "url": upload_result['url'], "message": "图片上传成功"})
            else:
                return self.send_error_response(500, f"图片上传失败: {upload_result['error']}")
        except Exception as e:
            return self.send_error_response(500, f"上传图片失败: {str(e)}")

    def handle_upload_and_create_task(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        try:
            content_type = headers.get('Content-Type', '') or headers.get('content-type', '')
            if 'multipart/form-data' not in content_type:
                return self.send_error_response(400, "需要multipart/form-data格式")
            form_data = self.parse_multipart_form_data(content_type, body)
            self._log_if_enabled('request_log', 'info', f"upload_create fields={list(form_data.keys())}")
            api_key = self.config_api_key if self.config_api_key else (form_data.get('api_key', [''])[0] if form_data.get('api_key') else '')
            prompt = form_data.get('prompt', [''])[0] if form_data.get('prompt') else ''
            if not api_key or not prompt:
                return self.send_error_response(400, "API Key和提示词不能为空")
            image_urls = []
            for field_name, file_list in form_data.items():
                if field_name.startswith('image_file'):
                    for file_info in file_list:
                        if isinstance(file_info, dict) and 'content' in file_info:
                            file_content = file_info['content']
                            if len(file_content) > self.max_file_size:
                                return self.send_error_response(400, f"文件大小不能超过{self.max_file_size // (1024*1024)}MB")
                            upload_result = self.upload_to_tos(file_content, file_info.get('filename', 'image.jpg'))
                            if not upload_result['success']:
                                self._log_if_enabled('error_traceback', 'error', f"upload_failed field={field_name} error={upload_result['error']}")
                                return self.send_error_response(500, f"上传图片失败: {upload_result['error']}")
                            url = upload_result['url']
                            self._log_if_enabled('upload_log', 'info', f"图片上传成功: {url}")
                            image_urls.append(url)
            if len(image_urls) == 0:
                return self.send_error_response(400, "至少需要一张参考图")
            if len(image_urls) > self.max_images:
                return self.send_error_response(400, f"最多支持{self.max_images}张参考图")
            request_data = {"model": "doubao-seedance-1-0-lite-i2v-250428", "content": [{"type": "text", "text": prompt}]}
            for url in image_urls:
                request_data["content"].append({"type": "image_url", "image_url": {"url": url}, "role": "reference_image"})
            try:
                self.logger.info(f"创建任务，请求: {json.dumps(request_data, ensure_ascii=False)}")
                req = urllib.request.Request(self.api_endpoint, data=json.dumps(request_data).encode('utf-8'), headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'})
                with urllib.request.urlopen(req, timeout=self.api_timeout) as response:
                    result = response.read().decode('utf-8')
                    api_response = json.loads(result)
                self.logger.info(f"API响应: {json.dumps(api_response, ensure_ascii=False)}")
                return self.send_json_response(200, api_response)
            except urllib.error.HTTPError as e:
                error_body = e.read().decode('utf-8')
                self.logger.error(f"API请求失败: {e.code} - {error_body}")
                upstream = self.parse_upstream_error(error_body)
                return self.build_error_response(e.code, "API错误", upstream, error_body)
            except Exception as e:
                self.logger.error(f"发送API请求时发生错误: {e}")
                return self.send_error_response(500, f"请求失败: {str(e)}")
        except Exception as e:
            if self._should_log('error_traceback'):
                self.logger.error(traceback.format_exc())
            return self.send_error_response(500, f"服务器内部错误: {str(e)}")

    def upload_to_tos(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        return self.tos_uploader.upload_file(file_content, filename, set_public_read=True)

    def parse_multipart_form_data(self, content_type: str, body: bytes) -> Dict[str, list]:
        try:
            if 'multipart/form-data' not in content_type:
                return {}
            boundary_match = re.search(r'boundary=([^;]+)', content_type)
            if not boundary_match:
                return {}
            boundary = boundary_match.group(1).strip('"')
            boundary_bytes = f'--{boundary}'.encode()
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
                    filename_match = re.search(r'filename="([^"]*)"', headers_text)
                    if name_match:
                        field_name = name_match.group(1)
                        if filename_match and filename_match.group(1):
                            form_data[field_name] = [{'content': content, 'filename': filename_match.group(1)}]
                        else:
                            form_data[field_name] = [content.decode('utf-8', errors='ignore')]
            return form_data
        except Exception as e:
            self.logger.error(f"解析multipart数据失败: {e}")
            return {}
