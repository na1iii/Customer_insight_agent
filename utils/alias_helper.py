# -*- coding: utf-8 -*-
"""
alias_helper.py - 企业简称与同义词映射加载工具
通过内存映射，支持简称到全称（以及全称到简称）的快速查找，避免对数据库进行写操作。
"""

import os
import pandas as pd

class AliasHelper:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(AliasHelper, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.alias_to_official = {}
        self.official_to_alias = {}
        self.load_aliases()
        self._initialized = True

    def load_aliases(self):
        try:
            # 获取当前文件所在位置的绝对路径
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            file_path = os.path.join(base_dir, "data", "enterprise_aliases.xlsx")
            
            if not os.path.exists(file_path):
                print(f"【AliasHelper Warning】别名映射文件不存在: {file_path}")
                return
                
            # 读取 Excel 文件
            df = pd.read_excel(file_path)
            
            # 使用列的索引或列名获取数据，增强健壮性
            col_official = "原始词" if "原始词" in df.columns else df.columns[0]
            col_alias = "同义词" if "同义词" in df.columns else df.columns[1]
            
            for _, row in df.iterrows():
                official = str(row[col_official]).strip()
                alias = str(row[col_alias]).strip()
                
                # 过滤无效空值与 NaN 字符串
                if (official and alias and 
                    official.lower() != "nan" and 
                    alias.lower() != "nan" and 
                    official != "" and 
                    alias != ""):
                    self.alias_to_official[alias] = official
                    self.official_to_alias[official] = alias
            
            print(f"【AliasHelper】成功从本地内存加载 {len(self.official_to_alias)} 条企业简称对照数据。")
        except Exception as e:
            print(f"【AliasHelper Error】加载别名文件异常: {e}")

# 全局单例对象
alias_helper = AliasHelper()
