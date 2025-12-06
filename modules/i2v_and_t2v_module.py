# -*- coding: utf-8 -*-
import json
import urllib.request
import urllib.error
import re
from typing import Dict, Any
import traceback

from .base_module import BaseModule
from .tos_utils import TOSUploader

class TextToVideoModule(BaseModule):
    def __init__(self, config: Dict[str, Any] = None):
        BaseModule.__init__(self, "i2v_and_t2v_module", config)
        cfg = self.config.get('i2v_and_t2v_module', {})
        self.api_endpoint = cfg.get('endpoint', '')
        self.api_key = cfg.get('ark_api_key', '')
        self.timeout = cfg.get('timeout', 30)
        tos_config = self.config.get('tos', {})
        self.tos_uploader = TOSUploader(bucket=tos_config.get('bucket_name'), region=tos_config.get('region'), enable_cache=True)
        limits = self.config.get('limits', {})
        self.max_file_size = limits.get('max_file_size_mb', 10) * 1024 * 1024

    def get_routes(self) -> Dict[str, callable]:
        return {
            '/text_to_video': self.handle_text_to_video,
            '/image_to_video_advanced': self.handle_image_to_video_advanced,
            '/video_task_status/': self.handle_video_task_status,
            '/upload_video_image': self.handle_upload_video_image
        }

    def handle_request(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        try:
            self._log_if_enabled('request_log', 'info', f"path={path} method={method} content_type={headers.get('Content-Type') or headers.get('content-type')}")
            routes = self.get_routes()
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
            if self._should_log('error_traceback'):
                self.logger.error(traceback.format_exc())
            return self.send_error_response(500, f"服务器内部错误: {str(e)}")

    def handle_text_to_video(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        if method != 'POST':
            return self.send_error_response(405, "只支持POST方法")
        try:
            ct = headers.get('Content-Type', '') or headers.get('content-type', '')
            self._log_if_enabled('request_log', 'info', f"text_to_video content_type={ct} body_len={len(body) if body else 0}")
            data = json.loads(body.decode('utf-8'))
            prompt = data.get('prompt', '').strip()
            self._log_if_enabled('request_log', 'info', f"prompt_len={len(prompt)} seed={data.get('seed')} duration={data.get('duration')} resolution={data.get('resolution')} rt={data.get('aspect_ratio')} fixed_camera={data.get('fixed_camera')} model_type={data.get('model_type')}")
            if not prompt:
                return self.send_error_response(400, "提示词不能为空")
            resolution = data.get('resolution')
            aspect_ratio = data.get('aspect_ratio')
            duration = data.get('duration')
            seed = data.get('seed')
            fixed_camera = data.get('fixed_camera', False)
            model_type = data.get('model_type')
            api_key = data.get('api_key', '').strip()
            task_result = self._create_video_task(prompt, 'text_to_video', None, None, resolution, aspect_ratio, duration, seed, fixed_camera, model_type, api_key)
            if task_result['success']:
                self._log_if_enabled('task_creation_log', 'info', f"text_to_video task_id={task_result['task_id']}")
                return self.send_json_response(200, {'success': True, 'task_id': task_result['task_id'], 'message': '文生视频任务创建成功'})
            else:
                self._log_if_enabled('error_traceback', 'error', f"create_failed error={task_result.get('error')} upstream={task_result.get('upstream_error')} raw={task_result.get('error_response_content')}")
                return self.build_error_response(500, f"创建任务失败: {task_result['error']}", task_result.get('upstream_error'), task_result.get('error_response_content'))
        except json.JSONDecodeError:
            return self.send_error_response(400, "请求数据格式错误")
        except Exception as e:
            if self._should_log('error_traceback'):
                self.logger.error(traceback.format_exc())
            return self.send_error_response(500, f"处理请求失败: {str(e)}")

    def handle_image_to_video_advanced(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        if method != 'POST':
            return self.send_error_response(405, "只支持POST方法")
        try:
            content_type = headers.get('Content-Type', '') or headers.get('content-type', '')
            if 'multipart/form-data' not in content_type:
                return self.send_error_response(400, "需要multipart/form-data格式")
            form_data = self.parse_multipart_form_data(content_type, body)
            self._log_if_enabled('request_log', 'info', f"i2v_advanced fields={list(form_data.keys())}")
            prompt = ''
            video_type = 'image_to_video_first_frame'
            first_frame_url = None
            last_frame_url = None
            if 'prompt' in form_data:
                prompt = form_data['prompt'][0]['content'].decode('utf-8').strip()
            if 'video_type' in form_data:
                video_type = form_data['video_type'][0]['content'].decode('utf-8').strip()
            if 'first_frame' in form_data:
                first_frame_info = form_data['first_frame'][0]
                file_content = first_frame_info['content']
                self._log_if_enabled('request_log', 'info', f"first_frame size={len(file_content)} name={first_frame_info.get('filename')}")
                if len(file_content) > self.max_file_size:
                    return self.send_error_response(400, f"文件大小不能超过{self.max_file_size // (1024*1024)}MB")
                upload_result = self.tos_uploader.upload_file(file_content, first_frame_info.get('filename', 'first_frame.jpg'))
                if not upload_result['success']:
                    self._log_if_enabled('error_traceback', 'error', f"first_frame_upload_failed error={upload_result['error']}")
                    return self.send_error_response(500, f"上传首帧图片失败: {upload_result['error']}")
                first_frame_url = upload_result['url']
            if video_type == 'image_to_video_first_last_frame' and 'last_frame' in form_data:
                last_frame_info = form_data['last_frame'][0]
                file_content = last_frame_info['content']
                self._log_if_enabled('request_log', 'info', f"last_frame size={len(file_content)} name={last_frame_info.get('filename')}")
                if len(file_content) > self.max_file_size:
                    return self.send_error_response(400, f"文件大小不能超过{self.max_file_size // (1024*1024)}MB")
                upload_result = self.tos_uploader.upload_file(file_content, last_frame_info.get('filename', 'last_frame.jpg'))
                if not upload_result['success']:
                    self._log_if_enabled('error_traceback', 'error', f"last_frame_upload_failed error={upload_result['error']}")
                    return self.send_error_response(500, f"上传尾帧图片失败: {upload_result['error']}")
                last_frame_url = upload_result['url']
            if video_type in ['image_to_video_first_frame', 'image_to_video_first_last_frame'] and not first_frame_url:
                return self.send_error_response(400, "首帧图片是必需的")
            if video_type == 'image_to_video_first_last_frame' and not last_frame_url:
                return self.send_error_response(400, "尾帧图片是必需的")
            resolution = None; aspect_ratio = None; duration = None; seed = None; fixed_camera = False; model_type = None
            if 'resolution' in form_data:
                resolution = form_data['resolution'][0]['content'].decode('utf-8').strip()
            if 'aspect_ratio' in form_data:
                aspect_ratio = form_data['aspect_ratio'][0]['content'].decode('utf-8').strip()
            if 'duration' in form_data:
                try: duration = int(form_data['duration'][0]['content'].decode('utf-8').strip())
                except ValueError: pass
            if 'seed' in form_data:
                try: seed = int(form_data['seed'][0]['content'].decode('utf-8').strip())
                except ValueError: pass
            if 'fixed_camera' in form_data:
                fixed_camera_str = form_data['fixed_camera'][0]['content'].decode('utf-8').strip().lower()
                fixed_camera = fixed_camera_str in ['true', '1', 'yes', 'on']
            if 'model_type' in form_data:
                model_type = form_data['model_type'][0]['content'].decode('utf-8').strip()
            api_key = None
            if 'api_key' in form_data:
                api_key = form_data['api_key'][0]['content'].decode('utf-8').strip()
            self._log_if_enabled('request_log', 'info', f"video_type={video_type} resolution={resolution} rt={aspect_ratio} duration={duration} seed={seed} fixed_camera={fixed_camera} model_type={model_type}")
            task_result = self._create_video_task(prompt, video_type, first_frame_url, last_frame_url, resolution, aspect_ratio, duration, seed, fixed_camera, model_type, api_key)
            if task_result['success']:
                self._log_if_enabled('task_creation_log', 'info', f"i2v task_id={task_result['task_id']}")
                return self.send_json_response(200, {'success': True, 'task_id': task_result['task_id'], 'message': '图生视频任务创建成功'})
            else:
                self._log_if_enabled('error_traceback', 'error', f"create_failed error={task_result.get('error')} upstream={task_result.get('upstream_error')} raw={task_result.get('error_response_content')}")
                return self.build_error_response(500, f"创建任务失败: {task_result['error']}", task_result.get('upstream_error'), task_result.get('error_response_content'))
        except Exception as e:
            if self._should_log('error_traceback'):
                self.logger.error(traceback.format_exc())
            return self.send_error_response(500, f"处理请求失败: {str(e)}")

    def handle_video_task_status(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
        if method != 'GET':
            return self.send_error_response(405, "只支持GET方法")
        try:
            task_id = path.split('/')[-1] if path.endswith('/') else path.split('/')[-1]
            if not task_id:
                return self.send_error_response(400, "缺少任务ID")
            status_result = self._query_task_status(task_id)
            if status_result['success']:
                return self.send_json_response(200, status_result['data'])
            else:
                return self.build_error_response(500, f"查询任务状态失败: {status_result['error']}", status_result.get('upstream_error'), status_result.get('error_response_content'), { 'status': 'failed' })
        except Exception as e:
            return self.send_error_response(500, f"查询失败: {str(e)}")

    def handle_upload_video_image(self, path: str, method: str, headers: Dict[str, str], body: bytes = None) -> Dict[str, Any]:
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
            upload_result = self.tos_uploader.upload_file(file_content, file_info.get('filename', 'image.jpg'))
            if upload_result['success']:
                return self.send_json_response(200, {'success': True, 'url': upload_result['url'], 'message': '图片上传成功'})
            else:
                return self.send_error_response(500, f"上传失败: {upload_result['error']}")
        except Exception as e:
            return self.send_error_response(500, f"上传失败: {str(e)}")

    def _create_video_task(self, prompt: str, video_type: str, first_frame_url: str = None, last_frame_url: str = None, resolution: str = None, aspect_ratio: str = None, duration: int = None, seed: int = None, fixed_camera: bool = False, model_type: str = None, api_key: str = None) -> Dict[str, Any]:
        try:
            model_version = model_type if model_type else "seedance-1.0-lite"
            if video_type == 'text_to_video':
                model_name = "doubao-seedance-1-0-pro-250528" if "pro" in model_version else "doubao-seedance-1-0-lite-t2v-250428"
            else:
                model_name = "doubao-seedance-1-0-pro-250528" if "pro" in model_version else "doubao-seedance-1-0-lite-i2v-250428"
            enhanced_prompt = prompt
            if resolution: enhanced_prompt += f" --rs {resolution}"
            if aspect_ratio: enhanced_prompt += f" --rt {aspect_ratio}"
            if duration: enhanced_prompt += f" --dur {duration}"
            if seed is not None: enhanced_prompt += f" --seed {seed}"
            if fixed_camera: enhanced_prompt += " --cf True"
            request_data = {"model": model_name, "content": [{"type": "text", "text": enhanced_prompt}]}
            if video_type == 'image_to_video_first_frame':
                request_data["content"].append({"type": "image_url", "image_url": {"url": first_frame_url}, "role": "first_frame"})
            elif video_type == 'image_to_video_first_last_frame':
                request_data["content"].append({"type": "image_url", "image_url": {"url": first_frame_url}, "role": "first_frame"})
                if last_frame_url:
                    request_data["content"].append({"type": "image_url", "image_url": {"url": last_frame_url}, "role": "last_frame"})
            use_api_key = api_key if api_key else self.api_key
            headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {use_api_key}'}
            req = urllib.request.Request(self.api_endpoint, data=json.dumps(request_data).encode('utf-8'), headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                response_text = response.read().decode('utf-8')
                response_data = json.loads(response_text)
                if response.status == 200:
                    task_id = response_data.get('id')
                    if task_id:
                        self._log_if_enabled('task_creation_log', 'info', f"api_task_ok id={task_id}")
                        return {'success': True, 'task_id': task_id}
                    else:
                        self._log_if_enabled('error_traceback', 'error', f"missing_id raw={response_text}")
                        return {'success': False, 'error': '响应中缺少id字段'}
                else:
                    error_msg = response_data.get('error', {}).get('message', '未知错误')
                    self._log_if_enabled('error_traceback', 'error', f"api_non_200 status={response.status} error={error_msg} raw={response_text}")
                    return {'success': False, 'error': error_msg, 'upstream_error': response_data.get('error'), 'error_response_content': response_text}
        except urllib.error.HTTPError as e:
            error_response = ""
            try:
                if e.fp: error_response = e.fp.read().decode('utf-8')
            except: pass
            error_msg = f"HTTP错误 {e.code}: {e.reason}"
            self._log_if_enabled('error_traceback', 'error', f"http_error code={e.code} reason={e.reason} raw={error_response}")
            upstream = None
            try:
                upstream = json.loads(error_response).get('error')
            except: pass
            return {'success': False, 'error': error_msg, 'error_response_content': error_response, 'upstream_error': upstream}
        except Exception as e:
            error_msg = f"创建任务时发生错误: {str(e)}"
            if self._should_log('error_traceback'):
                self.logger.error(traceback.format_exc())
            return {'success': False, 'error': error_msg}

    def _query_task_status(self, task_id: str) -> Dict[str, Any]:
        try:
            query_url = f"{self.api_endpoint}/{task_id}"
            headers = {'Authorization': f'Bearer {self.api_key}'}
            req = urllib.request.Request(query_url, headers=headers, method='GET')
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                response_text = response.read().decode('utf-8')
                response_data = json.loads(response_text)
                if response.status == 200:
                    self._log_if_enabled('request_log', 'info', f"status_ok id={task_id}")
                    return {'success': True, 'data': response_data}
                else:
                    error_msg = response_data.get('error', {}).get('message', '未知错误')
                    self._log_if_enabled('error_traceback', 'error', f"status_non_200 id={task_id} status={response.status} error={error_msg} raw={response_text}")
                    return {'success': False, 'error': error_msg, 'upstream_error': response_data.get('error'), 'error_response_content': response_text}
        except urllib.error.HTTPError as e:
            error_response = ""
            try:
                if e.fp: error_response = e.fp.read().decode('utf-8')
            except: pass
            error_msg = f"HTTP错误 {e.code}: {e.reason}"
            self._log_if_enabled('error_traceback', 'error', f"status_http_error id={task_id} code={e.code} reason={e.reason} raw={error_response}")
            upstream = None
            try:
                upstream = json.loads(error_response).get('error')
            except: pass
            return {'success': False, 'error': error_msg, 'upstream_error': upstream, 'error_response_content': error_response}
        except Exception as e:
            error_msg = f"查询任务状态时发生错误: {str(e)}"
            if self._should_log('error_traceback'):
                self.logger.error(traceback.format_exc())
            return {'success': False, 'error': error_msg}

    def parse_multipart_form_data(self, content_type: str, body: bytes) -> Dict[str, list]:
        try:
            boundary_match = re.search(r'boundary=([^;\s]+)', content_type)
            if not boundary_match:
                return {}
            boundary = boundary_match.group(1).strip('"')
            boundary_bytes = f'--{boundary}'.encode('utf-8')
            parts = body.split(boundary_bytes)
            form_data = {}
            for part in parts:
                if not part or part == b'\r\n' or part.startswith(b'--'):
                    continue
                if b'\r\n\r\n' in part:
                    headers_section, content = part.split(b'\r\n\r\n', 1)
                    content = content.rstrip(b'\r\n')
                    headers_text = headers_section.decode('utf-8', errors='ignore')
                    name_match = re.search(r'name="([^"]+)"', headers_text)
                    filename_match = re.search(r'filename="([^"]+)"', headers_text)
                    if name_match:
                        field_name = name_match.group(1)
                        file_info = {'content': content, 'filename': filename_match.group(1) if filename_match else None}
                        if field_name not in form_data:
                            form_data[field_name] = []
                        form_data[field_name].append(file_info)
            return form_data
        except Exception:
            return {}

I2VAndT2VModule = TextToVideoModule
