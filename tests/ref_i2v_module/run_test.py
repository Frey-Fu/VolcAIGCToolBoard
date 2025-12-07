#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
参考图生视频模块自动化测试用例
模拟用户在前端页面上传图片并提交任务的过程
"""

import os
import sys
import time
import json
import requests
from typing import Dict, Any, List

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

class RefGenVideoTestCase:
    """参考图生视频测试用例类"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.test_images_dir = os.path.join(os.path.dirname(__file__))
        self.test_images = ["人物 1.jpeg", "人物 2.jpeg", "人物 3.jpeg", "场景 1.jpeg"]
        
        # 测试参数配置（模拟前端页面配置）
        self.test_config = {
            "resolution": "480p",
            "aspect_ratio": "16:9", 
            "duration": 3,
            "seed": -1,
            "video_count": 2,
            "prompt": "镜头越过[图1]人物肩膀缓缓拉近，对准[图2]人物，[图3]人物站在[图2]人物旁边，表情警惕。 全图背景是[图4]。"
        }
    
    def log_info(self, message: str):
        """记录信息日志"""
        print(f"[INFO] {time.strftime('%Y-%m-%d %H:%M:%S')} - {message}")
    
    def log_error(self, message: str):
        """记录错误日志"""
        print(f"[ERROR] {time.strftime('%Y-%m-%d %H:%M:%S')} - {message}")
    
    def check_test_images(self) -> bool:
        """检查测试图片文件是否存在"""
        self.log_info("检查测试图片文件...")
        
        missing_files = []
        for image_name in self.test_images:
            image_path = os.path.join(self.test_images_dir, image_name)
            if not os.path.exists(image_path):
                missing_files.append(image_name)
            else:
                file_size = os.path.getsize(image_path)
                self.log_info(f"找到测试图片: {image_name} (大小: {file_size} bytes)")
        
        if missing_files:
            self.log_error(f"缺少测试图片文件: {missing_files}")
            return False
        
        self.log_info("所有测试图片文件检查完成")
        return True
    
    def upload_and_create_task(self) -> Dict[str, Any]:
        """上传图片并创建任务"""
        self.log_info("开始上传图片并创建任务...")
        
        try:
            # 准备multipart/form-data请求
            files = []
            data = {
                'prompt': self.test_config['prompt'],
                'resolution': self.test_config['resolution'],
                'aspect_ratio': self.test_config['aspect_ratio'],
                'duration': str(self.test_config['duration']),
                'seed': str(self.test_config['seed']),
                'video_count': str(self.test_config['video_count'])
            }
            
            # 依次添加测试图片
            for i, image_name in enumerate(self.test_images):
                image_path = os.path.join(self.test_images_dir, image_name)
                file_size = os.path.getsize(image_path)
                with open(image_path, 'rb') as f:
                    files.append((
                        f'image_file_{i+1}',
                        (image_name, f.read(), 'image/jpeg')
                    ))
                self.log_info(f"添加图片文件: {image_name} (大小: {file_size} bytes, 字段名: image_file_{i+1})")
            
            # 发送请求
            url = f"{self.base_url}/upload_and_create_task"
            self.log_info(f"发送请求到: {url}")
            self.log_info(f"请求参数: {json.dumps(data, indent=2, ensure_ascii=False)}")
            self.log_info(f"上传文件数量: {len(files)}")
            
            response = requests.post(url, data=data, files=files, timeout=30)
            
            self.log_info(f"响应状态码: {response.status_code}")
            self.log_info(f"响应内容: {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                # 检查是否有task_id或id字段
                task_id = result.get('task_id') or result.get('id')
                if task_id:
                    self.log_info(f"任务创建成功，任务ID: {task_id}")
                    # 打印详细的响应信息
                    self.log_info(f"完整响应数据: {json.dumps(result, indent=2, ensure_ascii=False)}")
                    return {'success': True, 'task_id': task_id, 'response': result}
                elif result.get('success'):
                    task_id = result.get('task_id')
                    self.log_info(f"任务创建成功，任务ID: {task_id}")
                    # 打印详细的响应信息
                    self.log_info(f"完整响应数据: {json.dumps(result, indent=2, ensure_ascii=False)}")
                    return {'success': True, 'task_id': task_id, 'response': result}
                else:
                    error_msg = result.get('message', result.get('error', '未知错误'))
                    self.log_error(f"任务创建失败: {error_msg}")
                    return {'success': False, 'error': error_msg, 'response': result}
            else:
                error_msg = f"HTTP错误 {response.status_code}: {response.text}"
                self.log_error(error_msg)
                return {'success': False, 'error': error_msg}
                
        except requests.exceptions.RequestException as e:
            error_msg = f"请求异常: {str(e)}"
            self.log_error(error_msg)
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"上传任务时发生错误: {str(e)}"
            self.log_error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def query_task_status(self, task_id: str, max_attempts: int = 60, interval: int = 10) -> Dict[str, Any]:
        """查询任务状态，直到任务完成或失败"""
        self.log_info(f"开始查询任务状态，任务ID: {task_id}")
        
        for attempt in range(max_attempts):
            try:
                url = f"{self.base_url}/task_status/{task_id}"
                self.log_info(f"第{attempt + 1}次查询任务状态: {url}")
                
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    result = response.json()
                    status = result.get('status', 'unknown')
                    self.log_info(f"任务状态: {status}")
                    
                    # 打印详细的状态查询响应
                    self.log_info(f"状态查询完整响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
                    
                    # 检查任务是否完成
                    if status in ['succeeded', 'completed', 'success']:
                        self.log_info("任务执行成功")
                        
                        # 提取并打印视频URL信息
                        # 检查content字段（豆包API格式）
                        if 'content' in result and isinstance(result['content'], dict):
                            content = result['content']
                            self.log_info(f"任务结果数据: {json.dumps(content, indent=2, ensure_ascii=False)}")
                            
                            if 'video_url' in content and isinstance(content['video_url'], str):
                                self.log_info("=== 生成的视频URL ===")
                                self.log_info(f"视频URL: {content['video_url']}")
                                self.log_info("=" * 50)
                            else:
                                self.log_info("未找到视频URL信息")
                        
                        # 检查data字段（其他API格式）
                        elif 'data' in result:
                            data = result['data']
                            self.log_info(f"任务结果数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
                            
                            # 尝试提取视频URL
                            video_urls = []
                            if isinstance(data, dict):
                                # 检查不同可能的字段名
                                for key in ['videos', 'video_urls', 'results', 'outputs']:
                                    if key in data and isinstance(data[key], list):
                                        for item in data[key]:
                                            if isinstance(item, dict) and 'url' in item:
                                                video_urls.append(item['url'])
                                            elif isinstance(item, str) and item.startswith('http'):
                                                video_urls.append(item)
                                
                                # 直接检查是否有url字段
                                if 'url' in data and isinstance(data['url'], str):
                                    video_urls.append(data['url'])
                                
                                # 检查video_url字段
                                if 'video_url' in data and isinstance(data['video_url'], str):
                                    video_urls.append(data['video_url'])
                            
                            if video_urls:
                                self.log_info("=== 生成的视频URL列表 ===")
                                for i, url in enumerate(video_urls, 1):
                                    self.log_info(f"视频{i}: {url}")
                                self.log_info("=" * 50)
                            else:
                                self.log_info("未找到视频URL信息")
                        else:
                            self.log_info("响应中未找到视频数据字段")
                        
                        return {'success': True, 'status': status, 'result': result}
                    elif status in ['failed', 'error']:
                        error_msg = result.get('error', {}).get('message', '任务执行失败')
                        self.log_error(f"任务执行失败: {error_msg}")
                        return {'success': False, 'status': status, 'error': error_msg, 'result': result}
                    elif status in ['running', 'processing', 'pending']:
                        self.log_info(f"任务正在执行中，等待{interval}秒后重试...")
                        time.sleep(interval)
                        continue
                    else:
                        self.log_info(f"未知任务状态: {status}，继续等待...")
                        time.sleep(interval)
                        continue
                else:
                    error_msg = f"查询状态失败，HTTP {response.status_code}: {response.text}"
                    self.log_error(error_msg)
                    if attempt < max_attempts - 1:
                        self.log_info(f"等待{interval}秒后重试...")
                        time.sleep(interval)
                        continue
                    else:
                        return {'success': False, 'error': error_msg}
                        
            except requests.exceptions.RequestException as e:
                error_msg = f"查询请求异常: {str(e)}"
                self.log_error(error_msg)
                if attempt < max_attempts - 1:
                    self.log_info(f"等待{interval}秒后重试...")
                    time.sleep(interval)
                    continue
                else:
                    return {'success': False, 'error': error_msg}
            except Exception as e:
                error_msg = f"查询任务状态时发生错误: {str(e)}"
                self.log_error(error_msg)
                if attempt < max_attempts - 1:
                    self.log_info(f"等待{interval}秒后重试...")
                    time.sleep(interval)
                    continue
                else:
                    return {'success': False, 'error': error_msg}
        
        # 超时
        timeout_msg = f"任务状态查询超时，已尝试{max_attempts}次"
        self.log_error(timeout_msg)
        return {'success': False, 'error': timeout_msg}
    
    def run_test(self) -> bool:
        """运行完整的测试流程"""
        self.log_info("="*60)
        self.log_info("开始参考图生视频模块自动化测试")
        self.log_info(f"测试配置: {json.dumps(self.test_config, indent=2, ensure_ascii=False)}")
        self.log_info("="*60)
        
        try:
            # 步骤1: 检查测试图片文件
            if not self.check_test_images():
                self.log_error("测试失败: 测试图片文件检查失败")
                return False
            
            # 步骤2: 上传图片并创建任务
            upload_result = self.upload_and_create_task()
            if not upload_result['success']:
                self.log_error(f"测试失败: 上传任务失败 - {upload_result['error']}")
                return False
            
            task_id = upload_result['task_id']
            
            # 步骤3: 查询任务状态直到完成
            status_result = self.query_task_status(task_id)
            if not status_result['success']:
                self.log_error(f"测试失败: 任务状态查询失败 - {status_result['error']}")
                return False
            
            self.log_info("="*60)
            self.log_info("参考图生视频模块自动化测试完成 - 成功")
            self.log_info("="*60)
            return True
            
        except Exception as e:
            error_msg = f"测试过程中发生未预期的错误: {str(e)}"
            self.log_error(error_msg)
            self.log_error("="*60)
            self.log_error("参考图生视频模块自动化测试完成 - 失败")
            self.log_error("="*60)
            return False


def main():
    """主函数"""
    # 可以通过命令行参数指定服务器地址
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    # 创建测试实例
    test_case = RefGenVideoTestCase(base_url)
    
    # 运行测试
    success = test_case.run_test()
    
    # 退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()