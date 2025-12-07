#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TOS工具类使用示例

这个文件展示了如何使用tos_utils.TOSUploader类进行文件上传
"""

import os
import sys

# 将项目根目录加入 Python 路径，便于从 modules 导入（tests/tosutil → tests → 项目根）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules.tos_utils import TOSUploader

file1_name = '人物 1.jpeg'
file2_name = '人物 2.jpeg'
TEST_DIR = os.path.dirname(os.path.abspath(__file__))

def example_basic_upload():
    """基本上传示例"""
    # 初始化TOS上传器
    uploader = TOSUploader(
        bucket='fuwei-test',
        region='cn-beijing',
        enable_cache=True
    )
    
    # 准备要上传的文件内容
    with open(os.path.join(TEST_DIR, file1_name), 'rb') as f:
        file_content = f.read()
    
    # 上传文件
    result = uploader.upload_file(
        file_content=file_content,
        filename=file1_name,
        set_public_read=True
    )
    
    if result['success']:
        print(f"上传成功！文件URL: {result['url']}")
        if result.get('cached'):
            print("文件来自缓存")
    else:
        print(f"上传失败: {result['error']}")


def example_multiple_uploads():
    """批量上传示例"""
    uploader = TOSUploader('fuwei-test', 'cn-beijing')
    
    files = [file1_name, file2_name]
    
    for filename in files:
        try:
            with open(os.path.join(TEST_DIR, filename), 'rb') as f:
                file_content = f.read()
            
            result = uploader.upload_file(file_content, filename)
            
            if result['success']:
                print(f"{filename} 上传成功: {result['url']}")
            else:
                print(f"{filename} 上传失败: {result['error']}")
                
        except FileNotFoundError:
            print(f"文件 {filename} 不存在")
    
    print(f"缓存中有 {uploader.get_cache_size()} 个文件")


def example_acl_management():
    """ACL权限管理示例"""
    uploader = TOSUploader('fuwei-test', 'cn-beijing')
    
    # 上传文件但不设置公开读取
    with open(os.path.join(TEST_DIR, 'private_file.txt'), 'rb') as f:
        file_content = f.read()
    
    result = uploader.upload_file(
        file_content=file_content,
        filename='private_file.txt',
        set_public_read=False
    )
    
    if result['success']:
        # 从URL中提取对象键名
        object_key = result['url'].split('/')[-1]
        
        # 后续设置为公开读取
        acl_result = uploader.set_acl(object_key, 'public-read')
        
        if acl_result['success']:
            print(f"ACL设置成功: {acl_result['message']}")
        else:
            print(f"ACL设置失败: {acl_result['error']}")


if __name__ == '__main__':
    print("TOS工具类使用示例")
    print("=" * 50)
    
    # 运行示例（注意：需要实际的文件才能运行）
    example_basic_upload()
    example_multiple_uploads()
    example_acl_management()
    
    print("示例代码已准备就绪，请根据实际情况修改文件路径后运行")
