"""数据模型层。

- schema.sql：SQLite 结构定义（唯一事实来源，Database.initialize 执行）。
- migrations.py：结构演进与数据迁移（加列、表重建、数据合并）。

当前保留裸 SQL 并异步包装（见 app/core/database.py）；若迁移到
SQLAlchemy 异步 ORM，本目录改为存放 ORM models，上层（services/routers）不变。
"""
