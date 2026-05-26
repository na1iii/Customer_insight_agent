# -*- coding: utf-8 -*-
"""
后台商机预计算脚本。

用法：
    python scripts/build_opportunities.py --limit 500
    python scripts/build_opportunities.py --district 普陀区 --limit 300

该脚本会把原始文章的企业匹配、区县识别、评分、聚合结果写入 opportunity_articles，
/api/articles 在线接口只读取该结果表，避免页面请求时执行重计算。
"""

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def load_env_file():
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())


def main():
    parser = argparse.ArgumentParser(description="构建商机预计算结果表 opportunity_articles")
    parser.add_argument("--district", default=None, help="只刷新指定行政区，如：普陀区")
    parser.add_argument("--limit", type=int, default=500, help="每类源表最多读取多少篇文章")
    parser.add_argument("--keep-existing", action="store_true", help="不清空已有结果，追加写入。默认会先清理刷新范围内旧结果")
    args = parser.parse_args()

    load_env_file()

    from utils import db_helper as db

    result = db.rebuild_opportunity_articles(
        district=args.district,
        limit=args.limit,
        clear_existing=not args.keep_existing,
    )
    print(f"【Opportunity Build】刷新完成: {result}")


if __name__ == "__main__":
    main()
