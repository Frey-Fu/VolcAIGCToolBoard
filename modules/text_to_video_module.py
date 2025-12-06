# -*- coding: utf-8 -*-
"""
文生视频模块
实现文生视频和图生视频功能
"""

import json
import urllib.request
import urllib.error
import os
import uuid
from datetime import datetime
import re
import traceback
from typing import Dict, Any, List

from .base_module import BaseModule
from .tos_utils import TOSUploader

class TextToVideoModule(BaseModule):
    """文生视频模块"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("text_to_video", config)
        
        # API配置
        text_to_video_module_config = self.config.get('text_to_video_module', {})
        self.api_endpoint = text_to_video_module_config.get('endpoint', '')
        self.api_key = text_to_video_module_config.get('ark_api_key', '')
        self.timeout = text_to_video_module_config.get('timeout', 30)
        
        # TOS配置
        tos_config = self.config.get('tos', {})
        self.tos_uploader = TOSUploader(
            bucket=tos_config.get('bucket_name'),
            region=tos_config.get('region'),
            enable_cache=True
        )
        
        # 限制配置
        limits = self.config.get('limits', {})
        self.max_file_size = limits.get('max_file_size_mb', 10) * 1024 * 1024
        
        self._log_if_enabled('initialization_log', 'info', f"使用配置文件中的API Key，跳过页面传入 key:...")
        self._log_if_enabled('initialization_log', 'info', "模块 text_to_video 初始化成功")
    
    def get_routes(self) -> Dict[str, callable]:
        """获取路由映射"""
        return {
            '/text_to_video': self.handle_text_to_video,
            '/image_to_video_advanced': self.handle_image_to_video_advanced,
            '/video_task_status/': self.handle_video_task_status,
            '/upload_video_image': self.handle_upload_video_image
        }
    
    def handle_request(self, path: str, method: str, headers: Dict[str, str], 
                      body: bytes = None) -> Dict[str, Any]:
        """处理HTTP请求"""
        try:
            routes = self.get_routes()
            
            # 查找匹配的路由
            handler = None
            for route_path, route_handler in routes.items():
                if path == route_path or (route_path.endswith('/') and path.startswith(route_path)):
                    handler = route_handler
                    break
            
            if handler:
                return handler(path, method, headers, body)
            else:
                return self.send_error_response(404, "路由未找到")
                
        except Exception as e:
            self._log_if_enabled('error_traceback', 'error', f"处理请求时发生错误: {str(e)}")
            if self._should_log('error_traceback'):
                self.logger.error(traceback.format_exc())
            return self.send_error_response(500, f"服务器内部错误: {str(e)}")
    
    def handle_text_to_video(self, path: str, method: str, headers: Dict[str, str], 
                            body: bytes = None) -> Dict[str, Any]:
        """处理文生视频请求"""
        if method != 'POST':
            return self.send_error_response(405, "只支持POST方法")
        
        try:
            # 解析请求数据
            data = json.loads(body.decode('utf-8'))
            prompt = data.get('prompt', '').strip()
            
            if not prompt:
                return self.send_error_response(400, "提示词不能为空")
            
            # 提取高级参数
            resolution = data.get('resolution')
            aspect_ratio = data.get('aspect_ratio')
            duration = data.get('duration')
            seed = data.get('seed')
            fixed_camera = data.get('fixed_camera', False)
            model_type = data.get('model_type')
            api_key = data.get('api_key', '').strip()
            
            # 创建视频生成任务
            task_result = self._create_video_task(
                prompt, 'text_to_video',
                resolution=resolution,
                aspect_ratio=aspect_ratio,
                duration=duration,
                seed=seed,
                fixed_camera=fixed_camera,
                model_type=model_type,
                api_key=api_key
            )
            
            if task_result['success']:
                return self.send_json_response(200, {
                    'success': True,
                    'task_id': task_result['task_id'],
                    'message': '文生视频任务创建成功'
                })
            else:
                return self.build_error_response(500, f"创建任务失败: {task_result['error']}", task_result.get('upstream_error'), task_result.get('error_response_content'))
                
        except json.JSONDecodeError:
            return self.send_error_response(400, "请求数据格式错误")
        except Exception as e:
            self._log_if_enabled('error_traceback', 'error', f"处理文生视频请求时发生错误: {str(e)}")
            return self.send_error_response(500, f"处理请求失败: {str(e)}")
    
    def handle_image_to_video_advanced(self, path: str, method: str, headers: Dict[str, str], 
                                     body: bytes = None) -> Dict[str, Any]:
        """处理高级图生视频请求（支持首帧和首尾帧）"""
        if method != 'POST':
            return self.send_error_response(405, "只支持POST方法")
        
        try:
            # 解析multipart/form-data
            content_type = headers.get('Content-Type', '') or headers.get('content-type', '')
            if 'multipart/form-data' not in content_type:
                return self.send_error_response(400, "需要multipart/form-data格式")
            
            form_data = self.parse_multipart_form_data(content_type, body)
            
            # 获取参数
            prompt = ''
            video_type = 'image_to_video_first_frame'  # 默认首帧模式
            first_frame_url = None
            last_frame_url = None
            
            if 'prompt' in form_data:
                prompt = form_data['prompt'][0]['content'].decode('utf-8').strip()
            
            if 'video_type' in form_data:
                video_type = form_data['video_type'][0]['content'].decode('utf-8').strip()
            
            # 处理图片上传
            if 'first_frame' in form_data:
                first_frame_info = form_data['first_frame'][0]
                file_content = first_frame_info['content']
                if len(file_content) > self.max_file_size:
                    return self.send_error_response(400, f"文件大小不能超过{self.max_file_size // (1024*1024)}MB")
                
                upload_result = self.tos_uploader.upload_file(file_content, first_frame_info.get('filename', 'first_frame.jpg'))
                if not upload_result['success']:
                    return self.send_error_response(500, f"上传首帧图片失败: {upload_result['error']}")
                first_frame_url = upload_result['url']
            
            if video_type == 'image_to_video_first_last_frame' and 'last_frame' in form_data:
                last_frame_info = form_data['last_frame'][0]
                file_content = last_frame_info['content']
                if len(file_content) > self.max_file_size:
                    return self.send_error_response(400, f"文件大小不能超过{self.max_file_size // (1024*1024)}MB")
                
                upload_result = self.tos_uploader.upload_file(file_content, last_frame_info.get('filename', 'last_frame.jpg'))
                if not upload_result['success']:
                    return self.send_error_response(500, f"上传尾帧图片失败: {upload_result['error']}")
                last_frame_url = upload_result['url']
            
            # 验证必要参数
            if video_type in ['image_to_video_first_frame', 'image_to_video_first_last_frame'] and not first_frame_url:
                return self.send_error_response(400, "首帧图片是必需的")
            
            if video_type == 'image_to_video_first_last_frame' and not last_frame_url:
                return self.send_error_response(400, "尾帧图片是必需的")
            
            # 提取高级参数
            resolution = None
            aspect_ratio = None
            duration = None
            seed = None
            fixed_camera = False
            model_type = None
            
            if 'resolution' in form_data:
                resolution = form_data['resolution'][0]['content'].decode('utf-8').strip()
            if 'aspect_ratio' in form_data:
                aspect_ratio = form_data['aspect_ratio'][0]['content'].decode('utf-8').strip()
            if 'duration' in form_data:
                try:
                    duration = int(form_data['duration'][0]['content'].decode('utf-8').strip())
                except ValueError:
                    pass
            if 'seed' in form_data:
                try:
                    seed = int(form_data['seed'][0]['content'].decode('utf-8').strip())
                except ValueError:
                    pass
            if 'fixed_camera' in form_data:
                fixed_camera_str = form_data['fixed_camera'][0]['content'].decode('utf-8').strip().lower()
                fixed_camera = fixed_camera_str in ['true', '1', 'yes', 'on']
            if 'model_type' in form_data:
                model_type = form_data['model_type'][0]['content'].decode('utf-8').strip()
            
            # 提取API key
            api_key = None
            if 'api_key' in form_data:
                api_key = form_data['api_key'][0]['content'].decode('utf-8').strip()
            
            # 创建视频生成任务
            task_result = self._create_video_task(
                prompt, video_type, first_frame_url, last_frame_url,
                resolution=resolution,
                aspect_ratio=aspect_ratio,
                duration=duration,
                seed=seed,
                fixed_camera=fixed_camera,
                model_type=model_type,
                api_key=api_key
            )
            
            if task_result['success']:
                return self.send_json_response(200, {
                    'success': True,
                    'task_id': task_result['task_id'],
                    'message': '图生视频任务创建成功'
                })
            else:
                return self.build_error_response(500, f"创建任务失败: {task_result['error']}", task_result.get('upstream_error'), task_result.get('error_response_content'))
                
        except Exception as e:
            self._log_if_enabled('error_traceback', 'error', f"处理图生视频请求时发生错误: {str(e)}")
            return self.send_error_response(500, f"处理请求失败: {str(e)}")
    
    def handle_video_task_status(self, path: str, method: str, headers: Dict[str, str], 
                               body: bytes = None) -> Dict[str, Any]:
        """处理任务状态查询"""
        if method != 'GET':
            return self.send_error_response(405, "只支持GET方法")
        
        try:
            # 从路径中提取task_id
            task_id = path.split('/')[-1] if path.endswith('/') else path.split('/')[-1]
            
            if not task_id:
                return self.send_error_response(400, "缺少任务ID")
            
            # 查询任务状态
            status_result = self._query_task_status(task_id)
            
            if status_result['success']:
                return self.send_json_response(200, status_result['data'])
            else:
                return self.build_error_response(500, f"查询任务状态失败: {status_result['error']}", status_result.get('upstream_error'), status_result.get('error_response_content'), { 'status': 'failed' })
                
        except Exception as e:
            self._log_if_enabled('error_traceback', 'error', f"查询任务状态时发生错误: {str(e)}")
            return self.send_error_response(500, f"查询失败: {str(e)}")
    
    def handle_upload_video_image(self, path: str, method: str, headers: Dict[str, str], 
                                body: bytes = None) -> Dict[str, Any]:
        """处理图片上传"""
        if method != 'POST':
            return self.send_error_response(405, "只支持POST方法")
        
        try:
            content_type = headers.get('Content-Type', '') or headers.get('content-type', '')
            if 'multipart/form-data' not in content_type:
                return self.send_error_response(400, "需要multipart/form-data格式")
            
            form_data = self.parse_multipart_form_data(content_type, body)
            
            if 'image' not in form_data:
                return self.send_error_response(400, "缺少图片文件")
            
            file_info = form_data['image'][0]
            file_content = file_info['content']
            
            if len(file_content) > self.max_file_size:
                return self.send_error_response(400, f"文件大小不能超过{self.max_file_size // (1024*1024)}MB")
            
            # 上传到TOS
            upload_result = self.tos_uploader.upload_file(file_content, file_info.get('filename', 'image.jpg'))
            
            if upload_result['success']:
                return self.send_json_response(200, {
                    'success': True,
                    'url': upload_result['url'],
                    'message': '图片上传成功'
                })
            else:
                return self.send_error_response(500, f"上传失败: {upload_result['error']}")
                
        except Exception as e:
            self._log_if_enabled('error_traceback', 'error', f"上传图片时发生错误: {str(e)}")
            return self.send_error_response(500, f"上传失败: {str(e)}")
    
    def _create_video_task(self, prompt: str, video_type: str, 
                          first_frame_url: str = None, last_frame_url: str = None,
                          resolution: str = None, aspect_ratio: str = None, 
                          duration: int = None, seed: int = None, 
                          fixed_camera: bool = False, model_type: str = None, 
                          api_key: str = None) -> Dict[str, Any]:
        """创建视频生成任务"""
        try:
            # 根据模型类型和视频类型选择正确的模型
            model_version = model_type if model_type else "seedance-1.0-lite"  # 默认使用lite版本
            
            if video_type == 'text_to_video':
                if "pro" in model_version:
                    model_name = "doubao-seedance-1-0-pro-250528"  # 文生视频Pro模型
                else:
                    model_name = "doubao-seedance-1-0-lite-t2v-250428"  # 文生视频Lite模型
            else:
                if "pro" in model_version:
                    model_name = "doubao-seedance-1-0-pro-250528"  # 图生视频Pro模型
                else:
                    model_name = "doubao-seedance-1-0-lite-i2v-250428"  # 图生视频Lite模型
            
            # 构建带参数的prompt
            enhanced_prompt = prompt
            
            # 添加分辨率参数 --rs
            if resolution:
                enhanced_prompt += f" --rs {resolution}"
            
            # 添加比例参数 --rt
            if aspect_ratio:
                enhanced_prompt += f" --rt {aspect_ratio}"
                
            # 添加时长参数 --dur
            if duration:
                enhanced_prompt += f" --dur {duration}"
                
            # 添加种子参数 --seed
            if seed is not None:
                enhanced_prompt += f" --seed {seed}"
            
            # 添加固定摄像头参数 --cf
            if fixed_camera:
                enhanced_prompt += " --cf True"
            
            # 构建请求数据
            request_data = {
                "model": model_name,
                "content": [
                    {
                        "type": "text",
                        "text": enhanced_prompt
                    }
                ]
            }
            
            # 根据视频类型添加相应参数
            if video_type == 'text_to_video':
                # 纯文本生视频 - 已经在上面设置了content
                pass
            elif video_type == 'image_to_video_first_frame':
                # 首帧图生视频
                request_data["content"].append({
                    "type": "image_url",
                    "image_url": {"url": first_frame_url},
                    "role": "first_frame"
                })
            elif video_type == 'image_to_video_first_last_frame':
                # 首尾帧图生视频
                request_data["content"].append({
                    "type": "image_url",
                    "image_url": {"url": first_frame_url},
                    "role": "first_frame"
                })
                if last_frame_url:
                    request_data["content"].append({
                        "type": "image_url",
                        "image_url": {"url": last_frame_url},
                        "role": "last_frame"
                    })
            
            # 发送API请求
            # 使用传入的api_key，如果没有则使用配置中的默认值
            use_api_key = api_key if api_key else self.api_key
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {use_api_key}'
            }
            
            # 记录请求详情
            if self._should_log('api_request_log'):
                self.logger.info(f"=== 发送API请求 ===")
                self.logger.info(f"请求URL: {self.api_endpoint}")
                self.logger.info(f"请求方法: POST")
                self.logger.info(f"请求头: {headers}")
                self.logger.info(f"请求数据: {json.dumps(request_data, ensure_ascii=False, indent=2)}")
            
            req = urllib.request.Request(
                self.api_endpoint,
                data=json.dumps(request_data).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                response_text = response.read().decode('utf-8')
                
                # 记录响应详情
                if self._should_log('api_response_log'):
                    self.logger.info(f"=== 收到API响应 ===")
                    self.logger.info(f"响应状态码: {response.status}")
                    self.logger.info(f"响应头: {dict(response.headers)}")
                    self.logger.info(f"响应内容: {response_text}")
                
                response_data = json.loads(response_text)
                
                if response.status == 200:
                    # API返回的字段名是'id'，不是'task_id'
                    task_id = response_data.get('id')
                    if task_id:
                        self.logger.info(f"视频生成任务创建成功: {task_id}")
                        return {'success': True, 'task_id': task_id}
                    else:
                        self.logger.error(f"响应中缺少id字段: {response_data}")
                        return {'success': False, 'error': '响应中缺少id字段'}
                else:
                    error_msg = response_data.get('error', {}).get('message', '未知错误')
                    self.logger.error(f"API返回错误状态码 {response.status}: {error_msg}")
                    return {
                        'success': False,
                        'error': error_msg,
                        'upstream_error': response_data.get('error'),
                        'error_response_content': response_text
                    }
                    
        except urllib.error.HTTPError as e:
            # 读取错误响应内容
            error_response = ""
            try:
                if e.fp:
                    error_response = e.fp.read().decode('utf-8')
            except:
                pass
            
            error_msg = f"HTTP错误 {e.code}: {e.reason}"
            self.logger.error(f"=== HTTP错误详情 ===")
            self.logger.error(f"错误码: {e.code}")
            self.logger.error(f"错误原因: {e.reason}")
            self.logger.error(f"请求URL: {e.url}")
            self.logger.error(f"错误响应内容: {error_response}")
            self.logger.error(error_msg)
            upstream = None
            try:
                upstream = json.loads(error_response).get('error')
            except:
                pass
            return {'success': False, 'error': error_msg, 'error_response_content': error_response, 'upstream_error': upstream}
        except Exception as e:
            error_msg = f"创建任务时发生错误: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def _query_task_status(self, task_id: str) -> Dict[str, Any]:
        """查询任务状态"""
        try:
            # 构建查询URL
            query_url = f"{self.api_endpoint}/{task_id}"
            
            headers = {
                'Authorization': f'Bearer {self.api_key}'
            }
            
            req = urllib.request.Request(query_url, headers=headers, method='GET')
            
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                response_text = response.read().decode('utf-8')
                response_data = json.loads(response_text)
                
                if response.status == 200:
                    return {'success': True, 'data': response_data}
                else:
                    error_msg = response_data.get('error', {}).get('message', '未知错误')
                    return {
                        'success': False,
                        'error': error_msg,
                        'upstream_error': response_data.get('error'),
                        'error_response_content': response_text
                    }
                    
        except urllib.error.HTTPError as e:
            error_response = ""
            try:
                if e.fp:
                    error_response = e.fp.read().decode('utf-8')
            except:
                pass
            error_msg = f"HTTP错误 {e.code}: {e.reason}"
            self.logger.error(error_msg)
            upstream = None
            try:
                upstream = json.loads(error_response).get('error')
            except:
                pass
            return {
                'success': False,
                'error': error_msg,
                'upstream_error': upstream,
                'error_response_content': error_response
            }
        except Exception as e:
            error_msg = f"查询任务状态时发生错误: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def parse_multipart_form_data(self, content_type: str, body: bytes) -> Dict[str, list]:
        """解析multipart/form-data"""
        try:
            # 提取boundary
            boundary_match = re.search(r'boundary=([^;\s]+)', content_type)
            if not boundary_match:
                return {}
            
            boundary = boundary_match.group(1).strip('"')
            boundary_bytes = f'--{boundary}'.encode('utf-8')
            end_boundary_bytes = f'--{boundary}--'.encode('utf-8')
            
            # 分割数据
            parts = body.split(boundary_bytes)
            form_data = {}
            
            for part in parts:
                if not part or part == b'\r\n' or part.startswith(b'--'):
                    continue
                
                # 分离头部和内容
                if b'\r\n\r\n' in part:
                    headers_section, content = part.split(b'\r\n\r\n', 1)
                    content = content.rstrip(b'\r\n')
                    
                    # 解析Content-Disposition
                    headers_text = headers_section.decode('utf-8', errors='ignore')
                    name_match = re.search(r'name="([^"]+)"', headers_text)
                    filename_match = re.search(r'filename="([^"]+)"', headers_text)
                    
                    if name_match:
                        field_name = name_match.group(1)
                        file_info = {
                            'content': content,
                            'filename': filename_match.group(1) if filename_match else None
                        }
                        
                        if field_name not in form_data:
                            form_data[field_name] = []
                        form_data[field_name].append(file_info)
            
            return form_data
            
        except Exception as e:
            self.logger.error(f"解析multipart数据时发生错误: {str(e)}")
            return {}