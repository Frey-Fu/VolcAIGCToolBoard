# 火山AIGC服务工作台 - 可扩展性框架

## 概述

本项目实现了一个可扩展的火山AIGC服务工作台框架，将原有的参考图生视频功能作为第一个模块集成，并为未来功能扩展提供了完整的架构支持。

## 架构设计

### 前端架构

- **主页面**: `main.html` - 提供统一的用户界面入口
- **Tab导航**: 支持多个功能模块的切换
- **响应式设计**: 支持桌面和移动端访问

### 后端架构

- **主服务器**: `main_server.py` - 统一的服务入口
- **模块管理器**: `ModuleManager` - 负责模块注册和路由分发
- **基础模块类**: `BaseModule` - 定义模块接口规范
- **功能模块**: 各个具体功能的实现

## 文件结构

```
image_to_video_service/
├── main.html                    # 前端主页面
├── main_server.py              # 后端主服务器
├── index.html                  # 原有的参考图生视频页面
├── config.json                 # 配置文件
├── modules/                    # 模块目录
│   ├── __init__.py
│   ├── base_module.py          # 基础模块类
│   └── image_to_video_module.py # 参考图生视频模块
└── README_new_framework.md     # 本文档
```

## 使用方法

### 启动新框架服务

```bash
cd VolcAIGCToolBoard_release
python main_server.py
```

服务将在 `http://localhost:8000` 启动

### 访问方式

- **主页面**: http://localhost:8000/main.html
- **API信息**: http://localhost:8000/api/modules
- **原有功能**: 通过主页面的"参考图生视频"标签页访问

## 模块开发指南

### 创建新模块

1. 继承 `BaseModule` 类
2. 实现必要的抽象方法
3. 在主服务器中注册模块

### 示例：创建文本生图模块

```python
from modules.base_module import BaseModule

class TextToImageModule(BaseModule):
    def __init__(self, config):
        super().__init__("text_to_image", config)
    
    def get_routes(self):
        return {
            '/text_to_image': self.handle_text_to_image
        }
    
    def handle_request(self, path, method, headers, body=None):
        # 实现请求处理逻辑
        pass
```

### 注册新模块

在 `main_server.py` 的 `run_server()` 函数中添加：

```python
# 注册新模块
text_to_image_module = TextToImageModule(config)
module_manager.register_module(text_to_image_module)
```

## 配置说明

配置文件 `config.json` 包含以下部分：

- `server`: 服务器配置（主服务器使用端口8001）
- `tos`: 对象存储配置
- `api`: API端点配置
- `limits`: 限制配置

## 扩展性特性

### 1. 模块化设计
- 每个功能作为独立模块
- 统一的接口规范
- 热插拔支持

### 2. 路由自动注册
- 模块自定义路由
- 自动路由映射
- 冲突检测

### 3. 配置管理
- 统一配置文件
- 模块级配置支持
- 环境变量支持

### 4. 错误处理
- 统一错误响应格式
- 模块级错误隔离
- 详细日志记录

## 测试验证

### 功能测试
1. 启动新框架服务
2. 访问主页面，验证Tab切换
3. 测试参考图生视频功能
4. 验证API响应格式

### 性能测试
- 响应时间对比
- 内存使用对比
- 并发处理能力

### 扩展性测试
- 添加新模块
- 路由冲突处理
- 配置热更新

## 未来规划

### 即将添加的功能模块
1. **文本生图模块** - 支持多种AI模型的文本到图像生成
2. **图像编辑模块** - 智能图像编辑和处理功能
3. **视频编辑模块** - AI驱动的视频编辑和特效

### 技术改进
- 数据库集成
- 用户认证系统
- 任务队列管理
- 缓存优化
- 监控和日志系统

## 故障排除

### 常见问题

1. **模块注册失败**
   - 检查模块类是否正确继承 `BaseModule`
   - 验证必要方法是否实现

2. **路由冲突**
   - 检查路由定义是否重复
   - 查看日志中的路由注册信息

3. **配置加载失败**
   - 验证 `config.json` 格式
   - 检查文件权限

4. **静态文件404**
   - 确认文件路径正确
   - 检查文件权限

## 贡献指南

1. 遵循现有代码风格
2. 添加适当的错误处理
3. 编写单元测试
4. 更新文档
