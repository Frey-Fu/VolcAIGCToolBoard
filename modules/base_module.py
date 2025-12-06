# -*- coding: utf-8 -*-
"""
基础模块类
定义所有功能模块的通用接口和基础功能
"""

from abc import ABC, abstractmethod
import json
from typing import Dict, Any, Optional
import logging
try:
    from fastapi import APIRouter, Request, Response
except Exception:
    APIRouter = None
    Request = None
    Response = None

class BaseModule(ABC):
    """
    基础模块抽象类
    所有功能模块都应该继承此类并实现相应的抽象方法
    """
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        """
        初始化基础模块
        
        Args:
            name: 模块名称
            config: 模块配置
        """
        self.name = name
        self.config = config or {}
        self.logger = logging.getLogger(f"module.{name}")
        self.state = "unloaded"
        modules_cfg = (self.config.get("modules", {}) if isinstance(self.config, dict) else {})
        module_cfg = modules_cfg.get(self.name, {})
        self.display_name = module_cfg.get("display_name", self.name)
        self.enabled = bool(module_cfg.get("enabled", True))
        
        # 设置日志配置
        self._setup_logging()
        
    @abstractmethod
    def get_routes(self) -> Dict[str, callable]:
        """
        获取模块的路由映射
        
        Returns:
            Dict[str, callable]: 路由路径到处理函数的映射
        """
        pass
    
    @abstractmethod
    def handle_request(self, path: str, method: str, headers: Dict[str, str], 
                      body: bytes = None) -> Dict[str, Any]:
        """
        处理HTTP请求
        
        Args:
            path: 请求路径
            method: HTTP方法
            headers: 请求头
            body: 请求体
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        pass
    
    def validate_config(self) -> bool:
        """
        验证模块配置
        
        Returns:
            bool: 配置是否有效
        """
        return True
    
    def initialize(self) -> bool:
        """
        初始化模块
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            if not self.validate_config():
                if self._should_log('error_log'):
                    self.logger.error(f"模块 {self.name} 配置验证失败")
                return False
            
            if self._should_log('initialization_log'):
                self.logger.info(f"模块 {self.name} 初始化成功")
            self.state = "initialized"
            return True
        except Exception as e:
            if self._should_log('error_log'):
                self.logger.error(f"模块 {self.name} 初始化失败: {e}")
            return False

    def start(self) -> bool:
        try:
            if not self.enabled:
                return False
            self.state = "started"
            return True
        except Exception:
            self.state = "stopped"
            return False

    def stop(self) -> bool:
        try:
            self.state = "stopped"
            return True
        except Exception:
            return False

    def unload(self) -> bool:
        try:
            self.state = "unloaded"
            return True
        except Exception:
            return False
    
    def get_module_info(self) -> Dict[str, Any]:
        """
        获取模块信息
        
        Returns:
            Dict[str, Any]: 模块信息
        """
        return {
            "name": self.name,
            "display_name": self.display_name,
            "enabled": self.enabled,
            "state": self.state,
            "config": self.config,
            "routes": list(self.get_routes().keys())
        }
    
    def send_json_response(self, status_code: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        构造JSON响应
        
        Args:
            status_code: HTTP状态码
            data: 响应数据
            
        Returns:
            Dict[str, Any]: 格式化的响应
        """
        return {
            "status_code": status_code,
            "headers": {
                "Content-Type": "application/json; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization"
            },
            "body": json.dumps(data, ensure_ascii=False, indent=2)
        }
    
    def send_error_response(self, status_code: int, error_message: str) -> Dict[str, Any]:
        """
        构造错误响应
        
        Args:
            status_code: HTTP状态码
            error_message: 错误信息
            
        Returns:
            Dict[str, Any]: 错误响应
        """
        return self.send_json_response(status_code, {
            "success": False,
            "error": error_message,
            "module": self.name
        })

    def build_error_response(self, status_code: int, base_error: str, upstream_error: Any = None, raw_error_text: Optional[str] = None, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "success": False,
            "error": base_error,
            "module": self.name
        }
        if upstream_error is not None:
            payload["upstream_error"] = upstream_error
        if raw_error_text:
            payload["error_response_content"] = raw_error_text
        if extra:
            payload.update(extra)
        return self.send_json_response(status_code, payload)

    def parse_upstream_error(self, raw_text: Optional[str]) -> Optional[Dict[str, Any]]:
        if not raw_text:
            return None
        try:
            data = json.loads(raw_text)
            err = data.get("error")
            if isinstance(err, dict):
                return err
        except Exception:
            return None
        return None
    
    def _setup_logging(self):
        """设置日志配置"""
        logging_config = self.config.get('logging', {})
        module_logging_config = logging_config.get(self.name, {})
        
        # 设置日志级别
        log_level = module_logging_config.get('level', 'INFO')
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        
        # 存储日志开关配置
        self.log_switches = module_logging_config
    
    def _should_log(self, log_type: str) -> bool:
        return self.log_switches.get(f'enable_{log_type}', self.log_switches.get(log_type, True))
    
    def _log_if_enabled(self, log_type: str, level: str, message: str):
        if self._should_log(log_type):
            getattr(self.logger, level.lower())(message)

    def get_router(self):
        if APIRouter is None:
            return None
        router = APIRouter()
        routes = list(self.get_routes().keys())
        async def handler(request: Request, subpath: Optional[str] = None):
            method = request.method
            headers = dict(request.headers)
            body = await request.body()
            path = request.url.path if subpath is None else request.url.path
            resp = self.handle_request(path, method, headers, body)
            status_code = resp.get("status_code", 200)
            headers_out = resp.get("headers", {})
            body_out = resp.get("body", "")
            if isinstance(body_out, str):
                return Response(content=body_out, status_code=status_code, headers=headers_out)
            elif isinstance(body_out, bytes):
                return Response(content=body_out, status_code=status_code, headers=headers_out)
            else:
                return Response(content=json.dumps(body_out, ensure_ascii=False), status_code=status_code, headers=headers_out)
        for route in routes:
            router.add_api_route(route, handler, methods=["GET", "POST"])
            if route.endswith('/'):
                router.add_api_route(route + "{subpath:path}", handler, methods=["GET", "POST"])
        return router