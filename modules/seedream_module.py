import json
import logging
import io
import re
import os
import time
from typing import Dict, Any, List, Tuple
from .base_module import BaseModule
from volcengine.visual.VisualService import VisualService
from werkzeug.datastructures import FileStorage
from .tos_utils import TOSUploader

class SeedreamModule(BaseModule):
    """SeedDream 4.0 图像生成模块"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__('seedream', config)
        self.visual_service = None
        self.tos_uploader = None
        
    def initialize(self) -> bool:
        """初始化模块"""
        try:
            # 初始化 Visual Service
            self.visual_service = VisualService()
            
            # 从配置中获取 AK/SK
            ak = self.config.get('volcengine_keys', {}).get('access_key')
            sk = self.config.get('volcengine_keys', {}).get('secret_key')
            
            if not ak or not sk:
                self.logger.error("缺少 volcengine access_key 或 secret_key")
                return False
                
            self.visual_service.set_ak(ak)
            self.visual_service.set_sk(sk)
            
            # 设置超时时间（如果SDK支持）
            try:
                if hasattr(self.visual_service, 'set_connection_timeout'):
                    self.visual_service.set_connection_timeout(90)
                if hasattr(self.visual_service, 'set_socket_timeout'):
                    self.visual_service.set_socket_timeout(90)
                self.logger.info("已设置API超时时间为90秒")
            except Exception as timeout_error:
                self.logger.warning(f"设置超时时间失败: {timeout_error}")
            
            # 从配置中获取重试次数和超时时间
            seedream_config = self.config.get('seedream', {})
            self.max_retries = seedream_config.get('max_retries', 2)
            self.api_timeout = seedream_config.get('api_timeout', 90)
            self.retry_delay = seedream_config.get('retry_delay', 5)
            
            self.logger.info(f"SeedDream配置: 最大重试次数={self.max_retries}, API超时={self.api_timeout}秒, 重试延迟={self.retry_delay}秒")
            
            # 初始化 TOS 上传器
            tos_config = self.config.get('tos', {})
            if tos_config:
                self.tos_uploader = TOSUploader(
                    bucket=tos_config.get('bucket_name'),
                    region=tos_config.get('region'),
                    enable_cache=True
                )
            else:
                self.logger.warning("TOS 配置未找到，跳过 TOS 初始化")
                self.tos_uploader = None
                
            self.logger.info("SeedDream 模块初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"SeedDream 模块初始化失败: {str(e)}")
            return False
    
    def get_routes(self) -> Dict[str, callable]:
        """获取路由配置"""
        return {
            '/seedream_generate': self.handle_seedream_generate
        }
    
    def handle_request(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        """处理请求"""
        try:
            routes = self.get_routes()
            
            # 查找匹配的路由
            handler = None
            for route_path, route_handler in routes.items():
                if path == route_path:
                    handler = route_handler
                    break
            
            if handler:
                return handler(path, method, headers, body)
            else:
                return self.send_error_response(404, "路由未找到")
                
        except Exception as e:
            self.logger.error(f"处理请求时发生错误: {str(e)}")
            return self.send_error_response(500, f"服务器内部错误: {str(e)}")
    
    def handle_seedream_generate(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        """处理 SeedDream 4.0 图像生成请求"""
        # 记录详细的请求信息
        self.logger.debug(f"=== SeedDream 请求开始 ===")
        self.logger.debug(f"请求路径: {path}")
        self.logger.debug(f"请求方法: {method}")
        self.logger.debug(f"请求头: {json.dumps(dict(headers), ensure_ascii=False, indent=2)}")
        self.logger.debug(f"请求体长度: {len(body) if body else 0} bytes")
        if body:
            try:
                body_str = body.decode('utf-8')[:1000]  # 只显示前1000字符
                self.logger.debug(f"请求体内容(前1000字符): {body_str}")
            except:
                self.logger.debug(f"请求体内容(二进制): {body[:100]}...")  # 显示前100字节
        
        if method != 'POST':
            return self.send_error_response(405, "只支持POST方法")
        
        try:
            # 检查Content-Type并相应地解析请求数据
            content_type = headers.get('Content-Type', '') or headers.get('content-type', '')
            self.logger.debug(f"请求Content-Type: {content_type}")
            
            prompt = ''
            seed = 42
            scale = 7.5
            return_url = True
            image_urls = []
            
            if 'multipart/form-data' in content_type:
                self.logger.debug("处理multipart/form-data请求")
                # 解析 multipart 数据
                form_data = self.parse_multipart_form_data(content_type, body)
                self.logger.debug(f"解析到的form字段: {list(form_data.keys())}")
                
                # 从 form 数据中获取参数
                if 'prompt' in form_data:
                    prompt = form_data['prompt'][0]['content'].decode('utf-8').strip()
                if 'seed' in form_data:
                    try:
                        seed = int(form_data['seed'][0]['content'].decode('utf-8').strip())
                    except (ValueError, KeyError):
                        pass
                if 'scale' in form_data:
                    try:
                        scale = float(form_data['scale'][0]['content'].decode('utf-8').strip())
                    except (ValueError, KeyError):
                        pass
                if 'return_url' in form_data:
                    try:
                        return_url_str = form_data['return_url'][0]['content'].decode('utf-8').strip().lower()
                        return_url = return_url_str in ['true', '1', 'yes']
                    except (ValueError, KeyError):
                        pass
                
                # 处理上传的图片文件
                for key in form_data:
                    if key.startswith('files') or key.startswith('image') or key == 'file':
                        for file_info in form_data[key]:
                            file_content = file_info['content']
                            filename = file_info.get('filename', 'image.jpg')
                            
                            self.logger.debug(f"处理上传文件: {filename}, 大小: {len(file_content)} bytes")
                            
                            # 上传图片到 TOS
                            upload_result = self._upload_image_to_tos_bytes(file_content, filename)
                            if upload_result and upload_result.get('success'):
                                image_url = upload_result['url']
                                image_urls.append(image_url)
                                self.logger.debug(f"图片上传成功: {image_url}")
                            else:
                                error_msg = upload_result.get('error', '未知错误') if upload_result else '上传失败'
                                self.logger.error(f"图片上传失败: {filename}, 错误: {error_msg}")
                                return self.send_error_response(500, f"图片上传失败: {error_msg}")
            
            elif 'application/json' in content_type:
                self.logger.debug("处理application/json请求")
                # 解析JSON数据
                if not body:
                    return self.send_error_response(400, "请求体为空")
                
                data = json.loads(body.decode('utf-8'))
                prompt = data.get('prompt', '')
                seed = data.get('seed', 42)
                scale = data.get('scale', 7.5)
                return_url = data.get('return_url', True)
            
            else:
                self.logger.error(f"不支持的Content-Type: {content_type}")
                return self.send_error_response(400, f"不支持的Content-Type: {content_type}")
            
            self.logger.debug(f"解析的请求参数: prompt='{prompt}', seed={seed}, scale={scale}, return_url={return_url}")
            self.logger.debug(f"上传的图片数量: {len(image_urls)}")
            
            if not prompt:
                return self.send_error_response(400, "缺少必要参数: prompt")
            
            # 构建请求参数
            form = {
                'req_key': 'jimeng_t2i_v40',
                'prompt': prompt,
                'seed': seed,
                'scale': scale,
                'return_url': return_url
            }
            
            if image_urls:
                form['image_urls'] = image_urls
            
            self.logger.debug(f"=== 准备调用远程 SeedDream API ===")
            self.logger.debug(f"API 请求参数: {json.dumps(form, ensure_ascii=False, indent=2)}")
            self.logger.info(f"SeedDream 请求参数: {json.dumps(form, ensure_ascii=False)}")
            
            # 调用 Visual Service API（带重试机制）
            response = self._call_api_with_retry(form)
            if response is None:
                return self.build_error_response(500, "API调用失败，请稍后重试")
            
            # 处理响应
            self.logger.debug(f"=== 处理 API 响应 ===")
            if response and isinstance(response, dict) and 'data' in response:
                self.logger.debug(f"响应包含 data 字段，开始提取图片 URL")
                data = response['data']
                self.logger.debug(f"data 内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
                
                # 提取生成的图片 URL
                result_images = []
                
                if 'image_urls' in data:
                    result_images = data['image_urls']
                    self.logger.debug(f"从 image_urls 字段提取到 {len(result_images)} 张图片")
                elif 'images' in data:
                    result_images = data['images']
                    self.logger.debug(f"从 images 字段提取到 {len(result_images)} 张图片")
                elif 'image_url' in data:
                    result_images = [data['image_url']]
                    self.logger.debug(f"从 image_url 字段提取到 1 张图片")
                else:
                    self.logger.warning(f"未找到图片 URL 字段，data 的键: {list(data.keys())}")
                
                final_response = {
                    'success': True,
                    'message': '图像生成成功',
                    'data': {
                        'images': result_images,
                        'prompt': prompt,
                        'seed': seed,
                        'scale': scale,
                        'input_images': image_urls
                    }
                }
                self.logger.debug(f"=== 最终返回给前端的响应 ===")
                self.logger.debug(f"响应内容: {json.dumps(final_response, ensure_ascii=False, indent=2)}")
                return self.send_json_response(200, final_response)
            else:
                self.logger.error(f"=== API 响应格式错误 ===")
                self.logger.error(f"响应是否为字典: {isinstance(response, dict)}")
                self.logger.error(f"响应是否包含 data: {'data' in response if isinstance(response, dict) else 'N/A'}")
                error_msg = "API 调用失败或返回数据格式错误"
                if response:
                    error_msg += f"，响应内容: {json.dumps(response, ensure_ascii=False)[:200]}"
                    self.logger.error(f"完整响应内容: {json.dumps(response, ensure_ascii=False)}")
                return self.build_error_response(500, error_msg)
                
        except Exception as e:
            self.logger.error(f"=== SeedDream 生成异常 ===")
            self.logger.error(f"异常类型: {type(e)}")
            self.logger.error(f"异常信息: {str(e)}")
            import traceback
            self.logger.error(f"异常堆栈: {traceback.format_exc()}")
            error_response = self.build_error_response(500, f"生成失败: {str(e)}")
            self.logger.debug(f"=== 错误响应 ===")
            self.logger.debug(f"错误响应内容: {json.dumps(error_response, ensure_ascii=False, indent=2)}")
            return error_response
    
    def _call_api_with_retry(self, form: Dict[str, Any]) -> Dict[str, Any]:
        """带重试机制的API调用"""
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    self.logger.info(f"第 {attempt + 1} 次尝试调用API（共 {self.max_retries + 1} 次）")
                    time.sleep(self.retry_delay)
                else:
                    self.logger.info("开始调用SeedDream API，请稍候...")
                
                # 详细记录即将发送的请求信息
                self.logger.debug(f"=== 即将发送到远程 SeedDream API 的请求 ===")
                self.logger.debug(f"请求目标: visual.volcengineapi.com")
                self.logger.debug(f"API方法: cv_process")
                self.logger.debug(f"请求参数类型: {type(form)}")
                self.logger.debug(f"请求参数内容: {json.dumps(form, ensure_ascii=False, indent=2)}")
                
                # 记录请求的关键信息
                req_key = form.get('req_key', 'unknown')
                prompt = form.get('prompt', '')[:100] + '...' if len(form.get('prompt', '')) > 100 else form.get('prompt', '')
                self.logger.info(f"发送请求 - req_key: {req_key}, prompt: {prompt}")
                
                # 记录开始时间
                start_time = time.time()
                self.logger.debug(f"请求开始时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")
                
                self.logger.debug(f"正在调用 visual_service.cv_process...")
                response = self.visual_service.cv_process(form)
                
                # 记录结束时间和耗时
                end_time = time.time()
                duration = end_time - start_time
                self.logger.debug(f"请求结束时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")
                self.logger.debug(f"请求耗时: {duration:.2f} 秒")
                
                self.logger.debug(f"=== 远程 SeedDream API 响应 ===")
                self.logger.debug(f"响应类型: {type(response)}")
                self.logger.debug(f"响应大小: {len(str(response)) if response else 0} 字符")
                
                # 详细记录响应内容
                if response:
                    response_str = json.dumps(response, ensure_ascii=False, indent=2)
                    self.logger.debug(f"完整响应内容: {response_str}")
                    
                    # 如果响应很长，也记录一个截断版本
                    if len(response_str) > 1000:
                        self.logger.info(f"响应内容(前500字符): {response_str[:500]}...")
                    else:
                        self.logger.info(f"响应内容: {response_str}")
                        
                    # 检查响应结构
                    if isinstance(response, dict):
                        self.logger.debug(f"响应字段: {list(response.keys())}")
                        if 'data' in response:
                            data = response['data']
                            self.logger.debug(f"data字段类型: {type(data)}")
                            if isinstance(data, dict):
                                self.logger.debug(f"data字段内容: {list(data.keys())}")
                else:
                    self.logger.debug(f"响应为空或None")
                
                self.logger.info(f"SeedDream API 调用成功，耗时 {duration:.2f} 秒")
                
                return response
                
            except Exception as api_error:
                last_error = api_error
                error_msg = str(api_error)
                
                # 记录异常发生时间
                error_time = time.time()
                self.logger.error(f"=== API 调用异常（第 {attempt + 1} 次尝试）===")
                self.logger.error(f"异常发生时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(error_time))}")
                self.logger.error(f"异常类型: {type(api_error)}")
                self.logger.error(f"异常信息: {error_msg}")
                
                # 记录异常时的请求信息
                self.logger.error(f"异常时的请求参数: {json.dumps(form, ensure_ascii=False)}")
                
                # 详细分析异常类型
                import traceback
                self.logger.error(f"异常堆栈: {traceback.format_exc()}")
                
                # 检查是否是网络相关错误
                is_network_error = any(keyword in error_msg.lower() for keyword in [
                    'timeout', 'timed out', 'read timeout', 'connection', 'network', 
                    'httperror', 'connectionerror', 'connecttimeout'
                ])
                
                # 检查是否是超时错误
                is_timeout = ('timeout' in error_msg.lower() or 
                            'timed out' in error_msg.lower() or
                            'read timeout' in error_msg.lower())
                
                self.logger.error(f"错误分类 - 网络错误: {is_network_error}, 超时错误: {is_timeout}")
                
                if is_timeout or is_network_error:
                    if attempt < self.max_retries:
                        self.logger.warning(f"API调用网络异常，将在 {self.retry_delay} 秒后重试...")
                        continue
                    else:
                        self.logger.error(f"API调用网络异常，已达到最大重试次数 {self.max_retries}")
                else:
                    # 非网络错误，不重试
                    self.logger.error(f"API调用发生非网络错误，不进行重试")
                    break
        
        # 所有重试都失败了
        if last_error:
            import traceback
            final_error_time = time.time()
            self.logger.error(f"=== 最终API调用失败 ===")
            self.logger.error(f"失败时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(final_error_time))}")
            self.logger.error(f"总重试次数: {self.max_retries}")
            self.logger.error(f"最后一次异常堆栈: {traceback.format_exc()}")
            
            error_msg = str(last_error)
            if 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower():
                self.logger.error(f"SeedDream API调用超时，已重试 {self.max_retries} 次，请检查网络连接或稍后重试")
                self.logger.error(f"建议: 1) 检查网络连接 2) 稍后重试 3) 联系技术支持")
            else:
                self.logger.error(f"SeedDream API调用失败: {error_msg}")
                self.logger.error(f"建议: 1) 检查请求参数 2) 查看API文档 3) 联系技术支持")
        
        return None
    
    def parse_multipart_form_data(self, content_type: str, body: bytes) -> Dict[str, List[Dict[str, Any]]]:
        """
        解析 multipart/form-data 格式的请求体
        """
        try:
            # 提取 boundary
            boundary_match = re.search(r'boundary=([^;\s]+)', content_type)
            if not boundary_match:
                return {}
            
            boundary = boundary_match.group(1).strip('"')
            boundary_bytes = f'--{boundary}'.encode('utf-8')
            
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
                    
                    # 解析头部
                    headers_text = headers_section.decode('utf-8', errors='ignore')
                    name_match = re.search(r'name="([^"]+)"', headers_text)
                    filename_match = re.search(r'filename="([^"]+)"', headers_text)
                    
                    if name_match:
                        field_name = name_match.group(1)
                        
                        field_info = {
                            'content': content,
                            'headers': headers_text
                        }
                        
                        if filename_match:
                            field_info['filename'] = filename_match.group(1)
                        
                        if field_name not in form_data:
                            form_data[field_name] = []
                        form_data[field_name].append(field_info)
            
            return form_data
            
        except Exception as e:
            self.logger.error(f"解析 multipart 数据失败: {str(e)}")
            return {}
    
    def _upload_image_to_tos(self, file: FileStorage) -> Dict[str, Any]:
        """上传图片到 TOS"""
        try:
            if not self.tos_uploader:
                self.logger.warning("TOS 未配置，跳过图片上传")
                return {'success': False, 'error': 'TOS未配置'}
            
            # 读取文件内容
            file.seek(0)
            file_content = file.read()
            
            # 生成带前缀的文件名
            filename = f"seedream/{file.filename}"
            
            # 使用TOSUploader上传
            upload_result = self.tos_uploader.upload_file(file_content, filename, set_public_read=True)
            
            if upload_result['success']:
                self.logger.info(f"图片上传成功: {upload_result['url']}")
            else:
                self.logger.error(f"图片上传失败: {upload_result['error']}")
            
            return upload_result
            
        except Exception as e:
            self.logger.error(f"图片上传失败: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _upload_image_to_tos_bytes(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        上传字节数据到 TOS
        """
        try:
            if not self.tos_uploader:
                self.logger.warning("TOS 未配置，跳过图片上传")
                return {'success': False, 'error': 'TOS未配置'}
            
            # 生成带前缀的文件名
            upload_filename = f"seedream/{filename}"
            
            # 使用TOSUploader上传
            upload_result = self.tos_uploader.upload_file(file_content, upload_filename, set_public_read=True)
            
            if upload_result['success']:
                self.logger.info(f"图片上传成功: {upload_result['url']}")
            else:
                self.logger.error(f"图片上传失败: {upload_result['error']}")
            
            return upload_result
            
        except Exception as e:
            self.logger.error(f"图片上传失败: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_module_info(self) -> Dict[str, Any]:
        """获取模块信息"""
        return {
            'name': 'SeedDream 4.0',
            'version': '1.0.0',
            'description': 'SeedDream 4.0 图像生成功能模块',
            'routes': self.get_routes(),
            'status': 'active' if self.visual_service else 'inactive'
        }
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """验证配置"""
        volcengine_config = config.get('volcengine', {})
        if not volcengine_config.get('access_key') or not volcengine_config.get('secret_key'):
            return False
        
        # 检查TOS配置（可选）
        tos_config = config.get('tos', {})
        if tos_config and not tos_config.get('bucket_name'):
            self.logger.warning("TOS配置中缺少bucket_name")
        
        return True