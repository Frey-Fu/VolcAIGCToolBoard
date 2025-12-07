# -*- coding: utf-8 -*-
import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from hashlib import sha256
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from modules.base_module import BaseModule
from modules.ref_i2v_module import RefI2VModule
from modules.i2v_and_t2v_module import I2VAndT2VModule
from modules.v2t_module import V2TModule

class ModuleManager:
    def __init__(self, app: FastAPI, config: Dict[str, Any]):
        self.app = app
        self.config = config
        self.modules: Dict[str, BaseModule] = {}
        self.logger = logging.getLogger("module_manager")

    def register_module(self, module: BaseModule) -> bool:
        try:
            if not module.initialize():
                self.logger.error(f"模块 {module.name} 初始化失败")
                return False
            self.modules[module.name] = module
            router = module.get_router()
            if router is not None:
                self.app.include_router(router)
            if module.enabled:
                module.start()
            self.logger.info(f"模块 {module.name} 注册成功")
            return True
        except Exception as e:
            self.logger.error(f"注册模块 {module.name} 失败: {e}")
            return False

    def unregister_module(self, name: str) -> bool:
        module = self.modules.get(name)
        if not module:
            return False
        try:
            module.unload()
            module.enabled = False
            return True
        except Exception:
            return False

    def start_module(self, name: str) -> bool:
        module = self.modules.get(name)
        if not module:
            return False
        return module.start()

    def stop_module(self, name: str) -> bool:
        module = self.modules.get(name)
        if not module:
            return False
        return module.stop()

    def get_module_state(self, name: str) -> Optional[str]:
        module = self.modules.get(name)
        return module.state if module else None

    def get_all_modules_info(self) -> Dict[str, Any]:
        return {name: m.get_module_info() for name, m in self.modules.items()}

def load_config() -> Dict[str, Any]:
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {
            "server": {"port": 8000, "host": "0.0.0.0"}
        }

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(filename)s:%(lineno)d %(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = normalize_config(config)
    image_to_video_module = RefI2VModule(cfg)
    module_manager.register_module(image_to_video_module)
    text_to_video_module = I2VAndT2VModule(cfg)
    module_manager.register_module(text_to_video_module)
    video_comprehension_module = V2TModule(cfg)
    module_manager.register_module(video_comprehension_module)
    try:
        yield
    finally:
        for m in module_manager.modules.values():
            try:
                m.stop()
            except Exception:
                pass

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = load_config()
module_manager = ModuleManager(app, config)

def normalize_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    modules = cfg.get("modules") or {}
    defaults = {
        "ref_i2v_module": {"enabled": True, "display_name": "参考图生视频"},
        "i2v_and_t2v_module": {"enabled": True, "display_name": "文/图生视频"},
        "v2t_module": {"enabled": True, "display_name": "视频理解"},
        "seedream": {"enabled": True, "display_name": "SeedDream"},
    }
    for name, meta in defaults.items():
        if name not in modules:
            enabled = name in cfg or True
            modules[name] = {"enabled": enabled, "display_name": meta["display_name"]}
    cfg["modules"] = modules
    return cfg

# 运行期不支持热插拔：移除配置差异应用与相关端点


@app.get("/api/modules")
def list_modules(request: Request):
    modules_info = module_manager.get_all_modules_info()
    payload = {"success": True, "modules": modules_info}
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    etag = sha256(body.encode("utf-8")).hexdigest()
    inm = request.headers.get("If-None-Match")
    logging.info(f"[{datetime.now().isoformat()}] /api/modules etag={etag}")
    if inm == etag:
        return Response(status_code=304)
    return JSONResponse(payload, headers={"ETag": etag, "Cache-Control": "max-age=5"})

@app.get("/api/modules/{name}")
def get_module(name: str):
    module = module_manager.modules.get(name)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    return module.get_module_info()

# 运行期不支持启停/卸载与热加载，相关管理端点已移除

@app.get("/index.html")
def get_index():
    index_path = os.path.join(os.path.dirname(__file__), 'index.html')
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="页面不存在")
    return FileResponse(index_path, headers={"Cache-Control": "no-store, must-revalidate"})

@app.get("/", include_in_schema=False)
def get_root():
    return get_index()

frontend_dir = os.path.join(os.path.dirname(__file__), 'frontend')
if os.path.isdir(frontend_dir):
    app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

static_dir = os.path.join(os.path.dirname(__file__), 'static')
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
