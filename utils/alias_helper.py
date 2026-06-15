# -*- coding: utf-8 -*-
"""
alias_helper.py - 企业简称与同义词映射加载工具
通过内存映射，支持简称到全称（以及全称到简称）的快速查找，直接从关系数据库的 brief2full_name 表加载数据。
"""

import os
from sqlalchemy import create_engine, text

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
            db_url = os.getenv("DATABASE_URL", "")
            if not db_url:
                print("【AliasHelper Warning】DATABASE_URL 环境变量未配置，无法加载别名。")
                return
                
            # 确保使用 utf8mb4 连接
            if "?" in db_url:
                base_url = db_url.split("?")[0]
                db_url = f"{base_url}?charset=utf8mb4"
            else:
                db_url = f"{db_url}?charset=utf8mb4"
                
            # 使用临时连接引擎以避免长连接占用
            engine = create_engine(
                db_url,
                pool_pre_ping=True,
                connect_args={"connect_timeout": 5}
            )
            with engine.connect() as conn:
                res = conn.execute(text("SELECT brief_name, full_name FROM brief2full_name"))
                count = 0
                for row in res:
                    brief_raw = row[0]
                    full = row[1]
                    if not brief_raw or not full:
                        continue
                    brief_raw = str(brief_raw).strip()
                    full = str(full).strip()
                    if not brief_raw or not full:
                        continue
                        
                    # 拆分可能由中英文逗号隔开的多个简称
                    briefs = [b.strip() for b in brief_raw.replace("，", ",").split(",") if b.strip()]
                    for brief in briefs:
                        self.alias_to_official[brief] = full
                        if full not in self.official_to_alias:
                            self.official_to_alias[full] = brief
                        count += 1
                print(f"【AliasHelper】成功从关系数据库加载 {count} 条企业简称对照数据。")
        except Exception as e:
            print(f"【AliasHelper Error】加载关系数据库别名表异常: {e}")

# 全局单例对象
alias_helper = AliasHelper()

