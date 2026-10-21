"""数据访问层(repositories)

所有 SQL 都收在这里,service 层不再直接拼 SQL。
好处是:索引改了什么、查询被改写成什么形状,只需要看这一个目录。

约定:
- 只做数据存取,不做业务判断,不抛 HTTPException
- 返回纯 dict / list / 标量
- 未迁移到 async 的老模块仍然可以继续用 sync 池,但新 repo 一律 async
"""
