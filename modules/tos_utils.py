import os
import tempfile
import subprocess
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional


class TOSUploader:
    """TOS对象存储上传工具类"""
    
    def __init__(self, bucket: str, region: str, enable_cache: bool = True):
        """
        初始化TOS上传器
        
        Args:
            bucket: TOS存储桶名称
            region: TOS区域，默认为cn-beijing
            enable_cache: 是否启用缓存，默认为True
        """
        self.bucket = bucket
        self.region = region
        if not bucket or not region:
            raise ValueError("bucket and region must be provided")
        self.base_url = f"https://{bucket}.tos-{region}.volces.com"
        self.enable_cache = enable_cache
        self.upload_cache = {} if enable_cache else None
        
        # 获取tosutil路径
        self.tosutil_path = os.path.join(os.path.dirname(__file__), '..', 'tosutil')
    
    def upload_file(self, file_content: bytes, filename: str, 
                   set_public_read: bool = True) -> Dict[str, Any]:
        """
        上传文件到TOS
        
        Args:
            file_content: 文件内容（字节）
            filename: 原始文件名
            set_public_read: 是否设置为公开读取，默认为True
            
        Returns:
            Dict包含上传结果:
            {
                "success": bool,
                "url": str,  # 成功时返回文件URL
                "error": str,  # 失败时返回错误信息
                "cached": bool  # 是否来自缓存
            }
        """
        try:
            # 生成唯一文件名
            file_hash = hashlib.md5(file_content).hexdigest()[:8]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_filename = f"{timestamp}_{file_hash}_{filename}"
            
            # 检查缓存
            if self.enable_cache:
                cache_key = hashlib.md5(file_content).hexdigest()
                if cache_key in self.upload_cache:
                    return {
                        "success": True,
                        "url": self.upload_cache[cache_key],
                        "cached": True
                    }
            
            # 使用tosutil上传
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
            
            try:
                # 构造tosutil上传命令
                upload_cmd = [
                    self.tosutil_path, 'cp',
                    temp_file_path,
                    f'tos://{self.bucket}/{unique_filename}'
                ]
                
                upload_result = subprocess.run(upload_cmd, capture_output=True, text=True, timeout=30)
                
                if upload_result.returncode == 0:
                    # 设置文件为公开读取权限（如果需要）
                    if set_public_read:
                        acl_cmd = [
                            self.tosutil_path, 'set-acl',
                            f'tos://{self.bucket}/{unique_filename}',
                            'public-read'
                        ]
                        
                        acl_result = subprocess.run(acl_cmd, capture_output=True, text=True, timeout=30)
                        
                        if acl_result.returncode != 0:
                            print(f"警告: 设置ACL失败: {acl_result.stderr}")
                    
                    file_url = f"{self.base_url}/{unique_filename}"
                    
                    # 缓存URL
                    if self.enable_cache:
                        cache_key = hashlib.md5(file_content).hexdigest()
                        self.upload_cache[cache_key] = file_url
                    
                    return {
                        "success": True,
                        "url": file_url,
                        "cached": False
                    }
                else:
                    return {
                        "success": False,
                        "error": f"上传失败: {upload_result.stderr}"
                    }
            finally:
                # 清理临时文件
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            return {
                "success": False,
                "error": f"上传过程中发生错误: {str(e)}"
            }
    
    def clear_cache(self):
        """清空上传缓存"""
        if self.upload_cache:
            self.upload_cache.clear()
    
    def get_cache_size(self) -> int:
        """获取缓存大小"""
        return len(self.upload_cache) if self.upload_cache else 0
    
    def set_acl(self, object_key: str, acl: str = 'public-read') -> Dict[str, Any]:
        """
        设置对象ACL权限
        
        Args:
            object_key: 对象键名
            acl: ACL权限，默认为public-read
            
        Returns:
            Dict包含操作结果
        """
        try:
            acl_cmd = [
                self.tosutil_path, 'set-acl',
                f'tos://{self.bucket}/{object_key}',
                acl
            ]
            
            result = subprocess.run(acl_cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"ACL设置成功: {acl}"
                }
            else:
                return {
                    "success": False,
                    "error": f"ACL设置失败: {result.stderr}"
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"ACL设置过程中发生错误: {str(e)}"
            }