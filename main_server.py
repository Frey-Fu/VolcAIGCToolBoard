# -*- coding: utf-8 -*-
"""
AIGC工作台主服务器
集成所有功能模块，提供统一的服务入口
"""

import http.server
import socketserver
import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, List
import traceback
import mimetypes
from urllib.parse import urlparse, parse_qs

from modules.base_module import BaseModule
from modules.image_to_video_module import ImageToVideoModule
from modules.text_to_video_module import TextToVideoModule
from modules.video_comprehension_module import VideoComprehensionModule

class ModuleManager:
    """模块管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.modules: Dict[str, BaseModule] = {}
        self.route_map: Dict[str, BaseModule] = {}
        self.logger = logging.getLogger("module_manager")
        
    def register_module(self, module: BaseModule) -> bool:
        """注册模块"""
        try:
            if not module.initialize():
                self.logger.error(f"模块 {module.name} 初始化失败")
                return False
            
            self.modules[module.name] = module
            
            # 注册路由
            routes = module.get_routes()
            for route in routes:
                self.route_map[route] = module
                self.logger.info(f"注册路由: {route} -> {module.name}")
            
            self.logger.info(f"模块 {module.name} 注册成功")
            return True
            
        except Exception as e:
            self.logger.error(f"注册模块 {module.name} 失败: {e}")
            return False
    
    def find_module_for_path(self, path: str) -> BaseModule:
        """根据路径找到对应的模块"""
        # 精确匹配
        if path in self.route_map:
            return self.route_map[path]
        
        # 前缀匹配（用于带参数的路径，如 /task_status/xxx）
        for route, module in self.route_map.items():
            if route.endswith('/') and path.startswith(route):
                return module
        
        return None
    
    def get_all_modules_info(self) -> Dict[str, Any]:
        """获取所有模块信息"""
        return {
            name: module.get_module_info() 
            for name, module in self.modules.items()
        }

class MainRequestHandler(http.server.BaseHTTPRequestHandler):
    """主请求处理器"""
    
    def __init__(self, *args, module_manager: ModuleManager = None, 
                 blocked_ips: set = None, **kwargs):
        self.module_manager = module_manager
        self.blocked_ips = blocked_ips or set()
        super().__init__(*args, **kwargs)
    
    def check_blocked_ip(self) -> bool:
        """检查是否为被阻止的IP"""
        client_ip = self.client_address[0]
        if client_ip in self.blocked_ips:
            print(f"[{datetime.now().isoformat()}] Blocked request from {client_ip}")
            return True
        return False
    
    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"[{datetime.now().isoformat()}] {format % args}")
    
    def do_OPTIONS(self):
        """处理OPTIONS请求（CORS预检）"""
        if self.check_blocked_ip():
            return
        
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
    
    def do_GET(self):
        """处理GET请求"""
        if self.check_blocked_ip():
            return
        
        try:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            
            # 处理静态文件
            if path == '/' or path == '/index.html':
                self.serve_static_file('index.html')
                return
            elif path == '/reference_image_gen_video.html':
                self.serve_static_file('frontend/reference_image_gen_video.html')
                return
            
            elif path == '/gen_video.html':
                self.serve_static_file('frontend/gen_video.html')
                return
            
            elif path == '/video_comprehension.html':
                self.serve_static_file('frontend/video_comprehension.html')
                return
            elif path.startswith('/frontend/'):
                # 处理frontend目录下的文件
                self.serve_static_file(path.lstrip('/'))
                return
            elif path.startswith('/static/') or path.endswith(('.css', '.js', '.png', '.jpg', '.ico')):
                self.serve_static_file(path.lstrip('/'))
                return
            elif path == '/api/modules':
                # 返回所有模块信息
                self.send_json_response(200, {
                    "success": True,
                    "modules": self.module_manager.get_all_modules_info()
                })
                return
            
            # 查找对应的模块
            module = self.module_manager.find_module_for_path(path)
            if module:
                headers = dict(self.headers)
                response = module.handle_request(path, 'GET', headers)
                self.send_module_response(response)
            else:
                self.send_json_response(404, {
                    "success": False,
                    "error": "路径未找到",
                    "path": path
                })
                
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] GET请求处理错误: {e}")
            print(traceback.format_exc())
            self.send_json_response(500, {
                "success": False,
                "error": f"服务器内部错误: {str(e)}"
            })
    
    def do_POST(self):
        """处理POST请求"""
        if self.check_blocked_ip():
            return
        
        try:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            
            # 读取请求体
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            headers = dict(self.headers)
            
            # 查找对应的模块
            module = self.module_manager.find_module_for_path(path)
            if module:
                response = module.handle_request(path, 'POST', headers, body)
                self.send_module_response(response)
            else:
                self.send_json_response(404, {
                    "success": False,
                    "error": "路径未找到",
                    "path": path
                })
                
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] POST请求处理错误: {e}")
            print(traceback.format_exc())
            self.send_json_response(500, {
                "success": False,
                "error": f"服务器内部错误: {str(e)}"
            })
    
    def serve_static_file(self, file_path: str):
        """提供静态文件服务"""
        try:
            # 安全检查，防止路径遍历攻击
            if '..' in file_path or file_path.startswith('/'):
                self.send_response(403)
                self.end_headers()
                return
            
            full_path = os.path.join(os.path.dirname(__file__), file_path)
            
            if not os.path.exists(full_path) or not os.path.isfile(full_path):
                self.send_response(404)
                self.end_headers()
                return
            
            # 获取MIME类型
            mime_type, _ = mimetypes.guess_type(full_path)
            if mime_type is None:
                mime_type = 'application/octet-stream'
            
            # 发送文件
            with open(full_path, 'rb') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-Type', mime_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(content)
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] 静态文件服务错误: {e}")
            self.send_response(500)
            self.end_headers()
    
    def send_module_response(self, response: Dict[str, Any]):
        """发送模块响应"""
        try:
            status_code = response.get('status_code', 200)
            headers = response.get('headers', {})
            body = response.get('body', '')
            
            self.send_response(status_code)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            
            if isinstance(body, str):
                self.wfile.write(body.encode('utf-8'))
            elif isinstance(body, bytes):
                self.wfile.write(body)
                
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] 发送响应错误: {e}")
    
    def send_json_response(self, status_code: int, data: Dict[str, Any]):
        """发送JSON响应"""
        try:
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
            self.end_headers()
            
            json_data = json.dumps(data, ensure_ascii=False, indent=2)
            self.wfile.write(json_data.encode('utf-8'))
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] 发送JSON响应错误: {e}")

def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    print(f"尝试加载配置文件: {config_path}")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"警告: 无法加载配置文件 {config_path}, 使用默认配置: {e}")
        return {
            "server": {"port": 8001, "host": "localhost"},
            "tos": {"bucket": "fuwei-test", "region": "cn-beijing"},
            "api": {"endpoint": "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks", "timeout": 30},
            "limits": {"max_file_size_mb": 10, "max_images": 4}
        }

def load_blocked_ips() -> set:
    """加载被阻止的IP列表"""
    blocked_ips = set()
    block_list_file = os.path.join(os.path.dirname(__file__), 'block_list.txt')
    if os.path.exists(block_list_file):
        try:
            with open(block_list_file, 'r') as f:
                for line in f:
                    ip = line.strip()
                    if ip:
                        blocked_ips.add(ip)
        except Exception as e:
            print(f"警告: 无法加载IP黑名单: {e}")
    return blocked_ips

def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def create_request_handler(module_manager: ModuleManager, blocked_ips: set):
    """创建请求处理器工厂"""
    def handler(*args, **kwargs):
        return MainRequestHandler(*args, module_manager=module_manager, 
                                blocked_ips=blocked_ips, **kwargs)
    return handler

def run_server():
    """运行主服务器"""
    # 设置日志
    setup_logging()
    
    # 加载配置
    config = load_config()
    blocked_ips = load_blocked_ips()
    
    # 创建模块管理器
    module_manager = ModuleManager(config)
    
    # 注册模块
    image_to_video_module = ImageToVideoModule(config)
    if not module_manager.register_module(image_to_video_module):
        print("错误: 参考图生视频模块注册失败")
        return
    
    text_to_video_module = TextToVideoModule(config)
    if not module_manager.register_module(text_to_video_module):
        print("错误: 文/首尾帧生视频模块注册失败")
        return
    
    video_comprehension_module = VideoComprehensionModule(config)
    if not module_manager.register_module(video_comprehension_module):
        print("错误: 视频理解模块注册失败")
        return
    
    # 服务器配置
    host = config['server']['host']
    port = config['server']['port']
    
    # 创建请求处理器
    handler = create_request_handler(module_manager, blocked_ips)
    
    # 启动服务器
    try:
        with socketserver.TCPServer((host, port), handler) as httpd:
            print(f"🚀 AIGC工作台主服务器启动成功!")
            print(f"📍 服务地址: http://{host}:{port}")
            print(f"🌐 主页面: http://{host}:{port}/index.html")
            print(f"📊 模块信息: http://{host}:{port}/api/modules")
            print(f"🔧 已注册模块: {list(module_manager.modules.keys())}")
            print(f"🛡️  已加载 {len(blocked_ips)} 个被阻止的IP")
            print("按 Ctrl+C 停止服务器")
            
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        print("\n🛑 服务器已停止")
    except Exception as e:
        print(f"❌ 服务器启动失败: {e}")
        print(traceback.format_exc())

if __name__ == '__main__':
    run_server()