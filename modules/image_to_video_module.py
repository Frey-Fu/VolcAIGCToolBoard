# -*- coding: utf-8 -*-
"""
参考图生视频模块
将现有的参考图生视频功能封装为可扩展的模块
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

class ImageToVideoModule(BaseModule):
    """参考图生视频功能模块"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("image_to_video", config)
        
        # API 配置
        self.api_endpoint = self.config.get('api', {}).get('endpoint', 
            'https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks')
        self.api_timeout = self.config.get('api', {}).get('timeout', 30)
        self.config_api_key = self.config.get('api', {}).get('api_key', '').strip()
        
        # TOS 配置
        tos_config = self.config.get('tos', {})
        tos_bucket = tos_config.get('bucket_name')
        tos_region = tos_config.get('region')

        # 初始化TOS上传器
        self.tos_uploader = TOSUploader(bucket=tos_bucket, region=tos_region, enable_cache=True)
        
        # 限制配置
        limits = self.config.get('limits', {})
        self.max_file_size = limits.get('max_file_size_mb', 10) * 1024 * 1024
        self.max_images = limits.get('max_images', 4)
        
        if self.config_api_key:
            self._log_if_enabled('initialization_log', 'info', f"使用配置文件中的API Key: {self.config_api_key[:8]}...")
        else:
            self._log_if_enabled('initialization_log', 'info', "配置文件未设置API Key，将使用前端页面配置的API Key")
    
    def get_routes(self) -> Dict[str, callable]:
        """获取模块路由"""
        return {
            '/generate_video': self.handle_generate_video,
            '/task_status/': self.handle_task_status,
            '/upload_image': self.handle_upload_image,
            '/upload_and_create_task': self.handle_upload_and_create_task
        }
    
    def handle_request(self, path: str, method: str, headers: Dict[str, str], 
                      body: bytes = None) -> Dict[str, Any]:
        """处理HTTP请求"""
        try:
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
            self._log_if_enabled('error_traceback', 'error', f"处理请求时发生错误: {e}")
            return self.send_error_response(500, f"服务器内部错误: {str(e)}")
    
    def handle_task_status(self, path: str, method: str, headers: Dict[str, str], 
                          body: bytes = None) -> Dict[str, Any]:
        """处理任务状态查询"""
        try:
            # 从路径中提取任务ID
            task_id = path.split('/task_status/')[-1]
            if not task_id:
                return self.send_error_response(400, "缺少任务ID")
            
            # 构造查询URL
            query_url = f"{self.api_endpoint}/{task_id}"
            
            # 获取API Key
            api_key = self.config_api_key
            if not api_key and 'authorization' in headers:
                api_key = headers['authorization'].replace('Bearer ', '')
            
            if not api_key:
                return self.send_error_response(400, "缺少API Key")
            
            # 发送查询请求
            req = urllib.request.Request(query_url)
            req.add_header('Authorization', f'Bearer {api_key}')
            req.add_header('Content-Type', 'application/json')
            
            with urllib.request.urlopen(req, timeout=self.api_timeout) as response:
                result = json.loads(response.read().decode('utf-8'))
                return self.send_json_response(200, result)
                
        except urllib.error.HTTPError as e:
            error_msg = e.read().decode('utf-8') if e.fp else str(e)
            return self.send_error_response(e.code, f"API请求失败: {error_msg}")
        except Exception as e:
            return self.send_error_response(500, f"查询任务状态失败: {str(e)}")
    
    def handle_generate_video(self, path: str, method: str, headers: Dict[str, str], 
                             body: bytes = None) -> Dict[str, Any]:
        """处理视频生成请求"""
        try:
            if not body:
                return self.send_error_response(400, "请求体为空")
            
            # 解析multipart form data
            content_type = headers.get('Content-Type', '') or headers.get('content-type', '')
            form_data = self.parse_multipart_form_data(content_type, body)
            
            if not form_data:
                return self.send_error_response(400, "无法解析表单数据")
            
            # 获取参数
            prompt = form_data.get('prompt', [''])[0]
            api_key = form_data.get('api_key', [''])[0] or self.config_api_key
            
            if not api_key:
                return self.send_error_response(400, "缺少API Key")
            
            if not prompt:
                return self.send_error_response(400, "缺少提示词")
            
            # 处理上传的图片
            image_urls = []
            for i in range(1, self.max_images + 1):
                file_key = f'reference_image_{i}'
                if file_key in form_data:
                    file_info = form_data[file_key][0]
                    if isinstance(file_info, dict) and 'content' in file_info:
                        # 上传图片到TOS
                        upload_result = self.upload_to_tos(
                            file_info['content'], 
                            file_info.get('filename', f'image_{i}.jpg')
                        )
                        if upload_result['success']:
                            image_urls.append(upload_result['url'])
                        else:
                            return self.send_error_response(500, f"图片上传失败: {upload_result['error']}")
            
            if not image_urls:
                return self.send_error_response(400, "至少需要上传一张参考图片")
            
            # 构造API请求
            api_data = {
                "model": "doubao-video-pro",
                "prompt": prompt,
                "reference_images": image_urls
            }
            
            # 发送API请求
            req = urllib.request.Request(self.api_endpoint)
            req.add_header('Authorization', f'Bearer {api_key}')
            req.add_header('Content-Type', 'application/json')
            
            json_data = json.dumps(api_data).encode('utf-8')
            
            with urllib.request.urlopen(req, data=json_data, timeout=self.api_timeout) as response:
                result = json.loads(response.read().decode('utf-8'))
                return self.send_json_response(200, {
                    "success": True,
                    "task_id": result.get('id'),
                    "message": "视频生成任务已提交",
                    "data": result
                })
                
        except urllib.error.HTTPError as e:
            error_msg = e.read().decode('utf-8') if e.fp else str(e)
            return self.send_error_response(e.code, f"API请求失败: {error_msg}")
        except Exception as e:
            if self._should_log('error_traceback'):
                self.logger.error(f"生成视频时发生错误: {traceback.format_exc()}")
            return self.send_error_response(500, f"生成视频失败: {str(e)}")
    
    def handle_upload_image(self, path: str, method: str, headers: Dict[str, str], 
                           body: bytes = None) -> Dict[str, Any]:
        """处理图片上传请求"""
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
            
            # 上传到TOS
            upload_result = self.upload_to_tos(
                file_info['content'],
                file_info.get('filename', 'uploaded_image.jpg')
            )
            
            if upload_result['success']:
                return self.send_json_response(200, {
                    "success": True,
                    "url": upload_result['url'],
                    "message": "图片上传成功"
                })
            else:
                return self.send_error_response(500, f"图片上传失败: {upload_result['error']}")
                
        except Exception as e:
            return self.send_error_response(500, f"上传图片失败: {str(e)}")
    
    def handle_upload_and_create_task(self, path: str, method: str, headers: Dict[str, str], 
                                     body: bytes = None) -> Dict[str, Any]:
        """处理文件上传并创建任务"""
        try:
            content_type = headers.get('Content-Type', '') or headers.get('content-type', '')
            if 'multipart/form-data' not in content_type:
                return self.send_error_response(400, "需要multipart/form-data格式")
            
            # 解析表单数据
            form_data = self.parse_multipart_form_data(content_type, body)
            
            # 优先使用配置文件中的API Key，如果没有则使用前端配置的
            api_key = self.config_api_key if self.config_api_key else (form_data.get('api_key', [''])[0] if form_data.get('api_key') else '')
            prompt = form_data.get('prompt', [''])[0] if form_data.get('prompt') else ''
            
            if not api_key or not prompt:
                return self.send_error_response(400, "API Key和提示词不能为空")
            
            # 收集参考图URL
            image_urls = []
            
            # 处理上传的文件
            for field_name, file_list in form_data.items():
                if field_name.startswith('image_file'):
                    for file_info in file_list:
                        if isinstance(file_info, dict) and 'content' in file_info:
                            file_content = file_info['content']
                            if len(file_content) > self.max_file_size:
                                return self.send_error_response(400, f"文件大小不能超过{self.max_file_size // (1024*1024)}MB")
                            
                            # 上传到TOS（TOSUploader内部会处理缓存）
                            upload_result = self.upload_to_tos(file_content, file_info.get('filename', 'image.jpg'))
                            if not upload_result['success']:
                                return self.send_error_response(500, f"上传图片失败: {upload_result['error']}")
                            url = upload_result['url']
                            self._log_if_enabled('upload_log', 'info', f"图片上传成功: {url}")
                            image_urls.append(url)
            
            if len(image_urls) == 0:
                return self.send_error_response(400, "至少需要一张参考图")
            
            if len(image_urls) > self.max_images:
                return self.send_error_response(400, f"最多支持{self.max_images}张参考图")
            
            # 构建请求数据（使用与原始server.py相同的格式）
            request_data = {
                "model": "doubao-seedance-1-0-lite-i2v-250428",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
            
            # 添加参考图
            for url in image_urls:
                request_data["content"].append({
                    "type": "image_url",
                    "image_url": {"url": url},
                    "role": "reference_image"
                })
            
            # 发送API请求
            try:
                self.logger.info(f"创建任务，请求: {json.dumps(request_data, ensure_ascii=False)}")
                
                req = urllib.request.Request(
                    self.api_endpoint,
                    data=json.dumps(request_data).encode('utf-8'),
                    headers={
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {api_key}'
                    }
                )
                
                with urllib.request.urlopen(req, timeout=self.api_timeout) as response:
                    result = response.read().decode('utf-8')
                    api_response = json.loads(result)
                
                self.logger.info(f"API响应: {json.dumps(api_response, ensure_ascii=False)}")
                
                return self.send_json_response(200, api_response)
                
            except urllib.error.HTTPError as e:
                error_body = e.read().decode('utf-8')
                self.logger.error(f"API请求失败: {e.code} - {error_body}")
                try:
                    error_data = json.loads(error_body)
                    return self.send_error_response(e.code, f"API错误: {error_data.get('message', '未知错误')}")
                except:
                    return self.send_error_response(e.code, f"API错误: {error_body}")
            except Exception as e:
                self.logger.error(f"发送API请求时发生错误: {e}")
                return self.send_error_response(500, f"请求失败: {str(e)}")
                
        except Exception as e:
            self.logger.error(f"处理上传和创建任务时发生错误: {e}")
            return self.send_error_response(500, f"服务器内部错误: {str(e)}")
    
    def upload_to_tos(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """上传文件到TOS"""
        return self.tos_uploader.upload_file(file_content, filename, set_public_read=True)
    
    def parse_multipart_form_data(self, content_type: str, body: bytes) -> Dict[str, list]:
        """解析multipart form data"""
        try:
            if 'multipart/form-data' not in content_type:
                return {}
            
            # 提取boundary
            boundary_match = re.search(r'boundary=([^;]+)', content_type)
            if not boundary_match:
                return {}
            
            boundary = boundary_match.group(1).strip('"')
            boundary_bytes = f'--{boundary}'.encode()
            
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
                    filename_match = re.search(r'filename="([^"]*)"', headers_text)
                    
                    if name_match:
                        field_name = name_match.group(1)
                        
                        if filename_match and filename_match.group(1):
                            # 文件字段
                            form_data[field_name] = [{
                                'content': content,
                                'filename': filename_match.group(1)
                            }]
                        else:
                            # 普通字段
                            form_data[field_name] = [content.decode('utf-8', errors='ignore')]
            
            return form_data
            
        except Exception as e:
            self.logger.error(f"解析multipart数据失败: {e}")
            return {}