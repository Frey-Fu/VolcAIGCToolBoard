# -*- coding: utf-8 -*-
"""
视频理解模块
调用 doubao-seed-1.6-vision 模型进行视频理解，按照提示词要求输出指定文案
"""

import json
import urllib.request
import urllib.error
import os
import urllib.parse
from urllib.parse import parse_qs
import uuid
from datetime import datetime
import re
import traceback
import mimetypes
import hashlib
from typing import Dict, Any

from .base_module import BaseModule
from .tos_utils import TOSUploader

class VideoComprehensionModule(BaseModule):
    """视频理解功能模块"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("video_comprehension", config)
        
        # API 配置
        self.api_endpoint = self.config.get('video_comprehension', {}).get('endpoint', 
            'https://ark.cn-beijing.volces.com/api/v3/chat/completions')
        self.api_timeout = self.config.get('video_comprehension', {}).get('timeout', 60)
        self.config_api_key = self.config.get('video_comprehension', {}).get('api_key', '').strip()
        
        # TOS 配置
        tos_config = self.config.get('tos', {})
        tos_bucket = tos_config.get('bucket_name')
        tos_region = tos_config.get('region')
        
        # 初始化TOS上传器
        self.tos_uploader = TOSUploader(bucket=tos_bucket, region=tos_region, enable_cache=True)
        
        # 限制配置
        limits = self.config.get('limits', {})
        self.max_file_size = limits.get('max_file_size_mb', 100) * 1024 * 1024  # 视频文件更大
        
        if self.config_api_key:
            self._log_if_enabled('initialization_log', 'info', f"使用配置文件中的API Key: {self.config_api_key[:8]}...")
        else:
            self._log_if_enabled('initialization_log', 'info', "配置文件未设置API Key，将使用前端页面配置的API Key")
    
    def get_routes(self) -> Dict[str, callable]:
        """获取模块路由"""
        return {
            '/video_comprehension_gen_text': self.handle_video_comprehension_gen_text,
            '/upload_video': self.handle_upload_video
        }
    
    def handle_request(self, path: str, method: str, headers: Dict[str, str], 
                      body: bytes = None) -> Dict[str, Any]:
        """处理HTTP请求"""
        try:
            if path == '/video_comprehension_gen_text' and method == 'POST':
                return self.handle_video_comprehension_gen_text(path, method, headers, body)
            elif path == '/upload_video' and method == 'POST':
                return self.handle_upload_video(path, method, headers, body)
            else:
                return self.send_error_response(404, "路径未找到")
        except Exception as e:
            self._log_if_enabled('error_traceback', 'error', f"上传视频失败: {e}")
            return self.send_error_response(500, f"上传视频失败: {str(e)}")

    def upload_to_tos(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """上传文件到TOS"""
        return self.tos_uploader.upload_file(file_content, filename, set_public_read=True)

    def handle_video_comprehension_gen_text(self, path: str, method: str, headers: Dict[str, str], 
                                 body: bytes = None) -> Dict[str, Any]:
        """处理视频理解请求"""
        try:
            # 解析请求数据
            content_type = headers.get('content-type', '')
            self._log_if_enabled('request_log', 'info', f"收到视频理解请求，Content-Type: {content_type}")
            
            # 尝试解析JSON数据
            try:
                if body:
                    data = json.loads(body.decode('utf-8'))
                    self._log_if_enabled('request_log', 'info', f"解析JSON数据: {data}")
                    api_key = data.get('api_key', '').strip()
                    video_url = data.get('video_url', '').strip()
                    prompt = data.get('prompt', '').strip()
                    fps = data.get('fps', 1.0)
                else:
                    raise ValueError("请求体为空")
            except (json.JSONDecodeError, ValueError):
                # 如果JSON解析失败，尝试解析表单数据
                if 'multipart/form-data' in content_type:
                    form_data = self.parse_multipart_form_data(content_type, body)
                    self._log_if_enabled('request_log', 'info', f"解析表单数据: {form_data}")
                    api_key = form_data.get('api_key', [''])[0].strip() if 'api_key' in form_data else ''
                    video_url = form_data.get('video_url', [''])[0].strip() if 'video_url' in form_data else ''
                    prompt = form_data.get('prompt', [''])[0].strip() if 'prompt' in form_data else ''
                    fps = float(form_data.get('fps', ['1.0'])[0]) if 'fps' in form_data else 1.0
                else:
                    self._log_if_enabled('error_traceback', 'error', f"无法解析请求数据，Content-Type: {content_type}")
                    return self.send_error_response(400, "无效的请求格式")
            
            self._log_if_enabled('request_log', 'info', f"解析后的参数 - api_key: {'***' if api_key else 'empty'}, video_url: {video_url}, prompt: {prompt[:50] if prompt else 'empty'}..., fps: {fps}")
            
            # 验证参数
            if not api_key and not self.config_api_key:
                return self.send_error_response(400, "API Key 不能为空")
            
            if not video_url:
                return self.send_error_response(400, "视频URL不能为空")
            
            if not prompt:
                return self.send_error_response(400, "提示词不能为空")
            
            # 使用配置的API Key或用户提供的API Key
            final_api_key = self.config_api_key if self.config_api_key else api_key
            
            # 调用视频理解API
            result = self.call_video_comprehension_api(final_api_key, video_url, prompt, fps)
            
            if result['success']:
                return self.send_json_response(200, {
                    'success': True,
                    'message': '视频理解完成',
                    'result': result['content']
                })
            else:
                return self.build_error_response(500, result.get('error', '视频理解失败'), result.get('upstream_error'), result.get('error_response_content'))
                
        except json.JSONDecodeError:
            return self.send_error_response(400, "JSON格式错误")
        except Exception as e:
            self._log_if_enabled('error_traceback', 'error', f"处理视频理解请求时发生错误: {e}")
            return self.send_error_response(500, f"处理请求失败: {str(e)}")
    
    def handle_upload_video(self, path: str, method: str, headers: Dict[str, str], 
                           body: bytes = None) -> Dict[str, Any]:
        """处理视频上传请求"""
        try:
            content_type = headers.get('content-type', '')
            self._log_if_enabled('request_log', 'info', f"收到视频上传请求，Content-Type: {content_type}")
            self._log_if_enabled('request_log', 'info', f"请求体大小: {len(body) if body else 0} bytes")
            
            form_data = self.parse_multipart_form_data(content_type, body)
            self._log_if_enabled('request_log', 'info', f"解析到的表单数据字段: {list(form_data.keys())}")
            
            if 'video' not in form_data:
                self._log_if_enabled('error_traceback', 'error', f"未找到video字段，可用字段: {list(form_data.keys())}")
                return self.send_error_response(400, "未找到视频文件")
            
            file_info = form_data['video'][0]
            if not isinstance(file_info, dict) or 'content' not in file_info:
                return self.send_error_response(400, "视频文件格式错误")
            
            # 检查文件格式
            filename = file_info.get('filename', '')
            if not any(filename.lower().endswith(ext) for ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']):
                return self.send_error_response(400, "不支持的视频格式，请上传mp4、avi、mov、mkv或webm格式的视频")
            
            # 检查文件大小（限制为100MB）
            file_content = file_info['content']
            if len(file_content) > 100 * 1024 * 1024:
                return self.send_error_response(400, "视频文件大小不能超过100MB")
            
            # 上传到TOS
            upload_result = self.upload_to_tos(file_content, filename)
            
            if upload_result['success']:
                return self.send_json_response(200, {
                    "success": True,
                    "url": upload_result['url'],
                    "message": "视频上传成功"
                })
            else:
                return self.send_error_response(500, f"视频上传失败: {upload_result['error']}")
                
        except Exception as e:
            self._log_if_enabled('error_traceback', 'error', f"处理视频上传请求时发生错误: {e}")
            return self.send_error_response(500, f"上传失败: {str(e)}")
    
    def call_video_comprehension_api(self, api_key: str, video_url: str, prompt: str, fps: float = 1.0) -> Dict[str, Any]:
        """调用视频理解API"""
        try:
            # 构建请求数据
            request_data = {
                "model": self.config.get('video_comprehension', {}).get('model', 'doubao-seed-1-6-vision-250815'),
                "messages": [
                    {
                        "content": [
                            {
                                "video_url": {
                                    "url": "https://fuwei-test.tos-cn-beijing.volces.com/20251206_143318_38529b83_02176284157923200000000000000000000ffffac1833802ac173.mp4",
                                    "fps": fps
                                },
                                "type": "video_url"
                            },
                            {
                                "text": prompt,
                                "type": "text"
                            }
                        ],
                        "role": "user"
                    }
                ],
            }
            
            # 构建请求
            request_json = json.dumps(request_data, indent=2, ensure_ascii=False).encode('utf-8')
            
            # 打印请求体日志
            if self._should_log('api_request_log'):
                self.logger.info(f"=== 视频理解API请求 ===")
                self.logger.info(f"请求URL: {self.api_endpoint}")
                self.logger.info(f"请求体: {request_json.decode('utf-8')}")
            
            req = urllib.request.Request(
                self.api_endpoint,
                data=request_json,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {api_key}'
                }
            )
            
            self._log_if_enabled('api_request_log', 'info', f"调用视频理解API: {video_url[:50]}...")
            
            # 发送请求
            with urllib.request.urlopen(req, timeout=self.api_timeout) as response:
                response_body = response.read().decode('utf-8')
                
                # 打印响应体日志
                if self._should_log('api_response_log'):
                    self.logger.info(f"=== 视频理解API响应 ===")
                    self.logger.info(f"响应状态码: {response.status}")
                    self.logger.info(f"响应体: {response_body}")
                
                response_data = json.loads(response_body)
                
                if 'choices' in response_data and len(response_data['choices']) > 0:
                    content = response_data['choices'][0]['message']['content']
                    return {
                        'success': True,
                        'content': content
                    }
                else:
                    return {
                        'success': False,
                        'error': '未获取到有效响应'
                    }
                    
        except urllib.error.HTTPError as e:
            error_msg = f"API请求失败: HTTP {e.code}"
            try:
                error_body = e.read().decode('utf-8')
                if self._should_log('error_traceback'):
                    self.logger.info(f"=== API错误响应 ===")
                    self.logger.info(f"错误状态码: {e.code}")
                    self.logger.info(f"错误响应体: {error_body}")
                error_response = json.loads(error_body)
                upstream = error_response.get('error') if isinstance(error_response.get('error'), dict) else None
                self._log_if_enabled('error_traceback', 'error', error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'upstream_error': upstream,
                    'error_response_content': error_body
                }
            except Exception as parse_error:
                self._log_if_enabled('error_traceback', 'error', f"解析错误响应失败: {parse_error}")
                self._log_if_enabled('error_traceback', 'error', error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'error_response_content': None
                }
            
        except urllib.error.URLError as e:
            error_msg = f"网络连接失败: {str(e)}"
            self._log_if_enabled('error_traceback', 'error', error_msg)
            return {
                'success': False,
                'error': error_msg
            }
            
        except Exception as e:
            error_msg = f"调用API时发生错误: {str(e)}"
            self._log_if_enabled('error_traceback', 'error', error_msg)
            return {
                'success': False,
                'error': error_msg
            }
    
    def parse_multipart_form_data(self, content_type: str, body: bytes) -> Dict[str, list]:
        """解析multipart/form-data"""
        try:
            # 如果Content-Type为空或不包含multipart/form-data，尝试从body中检测
            if not content_type or 'multipart/form-data' not in content_type:
                # 尝试从body开头检测boundary
                if body and body.startswith(b'--'):
                    # 从body的第一行提取boundary
                    first_line = body.split(b'\r\n')[0]
                    if first_line.startswith(b'--'):
                        boundary = first_line[2:].decode('utf-8', errors='ignore')
                        self.logger.info(f"从body中检测到boundary: {boundary}")
                    else:
                        return {}
                else:
                    return {}
            else:
                # 提取boundary
                boundary_match = re.search(r'boundary=([^;]+)', content_type)
                if not boundary_match:
                    return {}
                boundary = boundary_match.group(1).strip('"')
            boundary_bytes = ('--' + boundary).encode('utf-8')
            
            # 分割数据
            parts = body.split(boundary_bytes)
            form_data = {}
            
            for part in parts[1:-1]:  # 跳过第一个和最后一个空部分
                if not part.strip():
                    continue
                
                # 分离头部和内容
                if b'\r\n\r\n' in part:
                    headers_section, content = part.split(b'\r\n\r\n', 1)
                    content = content.rstrip(b'\r\n')
                    
                    # 解析Content-Disposition头
                    headers_text = headers_section.decode('utf-8', errors='ignore')
                    name_match = re.search(r'name="([^"]+)"', headers_text)
                    filename_match = re.search(r'filename="([^"]+)"', headers_text)
                    
                    if name_match:
                        field_name = name_match.group(1)
                        
                        if filename_match:
                            # 文件字段
                            filename = filename_match.group(1)
                            form_data[field_name] = [{
                                'content': content,
                                'filename': filename
                            }]
                        else:
                            # 普通字段
                            field_value = content.decode('utf-8', errors='ignore')
                            if field_name not in form_data:
                                form_data[field_name] = []
                            form_data[field_name].append(field_value)
            
            return form_data
            
        except Exception as e:
            self.logger.error(f"解析multipart数据失败: {e}")
            return {}