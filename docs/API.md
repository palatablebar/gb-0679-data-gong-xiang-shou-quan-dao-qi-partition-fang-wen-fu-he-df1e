# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。/api/upload接收multipart文件file。/api/runs/<id>/archive只导出一份带清单与证据的CSV。

覆盖结论额外提供：`GET /api/coverage/current`返回生效结论与版本号；`GET /api/coverage/versions`列出全部覆盖版本；`GET /api/coverage/<id>`取指定版本证据；`POST /api/coverage/switch`传coverage_id与当前version切换生效版本，版本冲突返回409且旧版证据保留。同一输入重跑不新增覆盖版本。
