# 深度登记 数据共享授权到期与分区访问复核

规模：中型。使用者：企业数据共享审计专员。核心规则：拒绝规则优先于允许，授权必须同时命中资源、分区和生效窗；显式拒绝不得被宽授权覆盖。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 访问采信 | 查看并运行访问采信 | `/api/accesses` | `app/modules/m1_accesses/rules.py` | `tests/test_m1.py` |
| M2 资源映射 | 查看并运行资源映射 | `/api/resources` | `app/modules/m2_resources/rules.py` | `tests/test_m2.py` |
| M3 授权定版 | 查看并运行授权定版 | `/api/grants` | `app/modules/m3_grants/rules.py` | `tests/test_m3.py` |
| M4 冲突裁决 | 查看并运行冲突裁决 | `/api/conflicts` | `app/modules/m4_conflicts/rules.py` | `tests/test_m4.py` |
| M5 分区判定 | 查看并运行分区判定 | `/api/partitions` | `app/modules/m5_partitions/rules.py` | `tests/test_m5.py` |
| M6 访问对账 | 查看并运行访问对账 | `/api/audit` | `app/modules/m6_audit/rules.py` | `tests/test_m6.py` |
| M7 覆盖结论 | 查看并运行覆盖结论 | `/api/coverage` | `app/modules/m7_coverage/rules.py` | `tests/test_m7.py` |
| M8 审计归档 | 查看并运行审计归档 | `/api/seals` | `app/modules/m8_seals/rules.py` | `tests/test_m8.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | 旧编码 | 默认解码失败 | 回退GB18030 | `app/modules/m1_accesses/rules.py` | `tests/test_m1.py::test_legacy_encoding_real_sample` |
| TRAP-02 | BOM | 首列名多字符 | utf-8-sig | `app/modules/m1_accesses/rules.py` | `tests/test_m1.py::test_bom_real_sample` |
| TRAP-03 | 带引号换行 | 拆成两条 | csv逻辑行 | `app/modules/m1_accesses/rules.py` | `tests/test_m1.py::test_quoted_newline_is_one_record` |
| TRAP-05 | 列数不匹配 | 静默错列 | 隔离原行 | `app/modules/m1_accesses/rules.py` | `tests/test_m1.py::test_bad_columns_real_sample` |
| TRAP-08 | 前导零ID | 编码变形 | 全程字符串 | `app/modules/m1_accesses/rules.py` | `tests/test_m1.py::test_identifier_preserved_real_sample` |
| TRAP-14 | 重复键冲突 | 后写覆盖 | 保留首条并隔离冲突行 | `app/modules/m1_accesses/rules.py` | `tests/test_m1.py::test_duplicate_conflict_real_sample` |
| TRAP-18 | 空态三态 | 一律成功 | 分别错误码 | `app/modules/m1_accesses/rules.py` | `tests/test_m1.py::test_three_empty_states` |
| TRAP-26 | 旧版本提交 | 覆盖新结果 | 版本条件更新 | `app/store.py` | `tests/test_e2e.py::test_stale_review_409` |
| TRAP-07 | 上游结果空值 | 误报拒绝 | 隔离缺失 | `app/values.py` | `tests/test_m3.py::test_real_missing_decision_not_zero` |
| TRAP-19 | 允许与拒绝重叠 | 后写覆盖 | 拒绝优先且排序证据 | `app/modules/m4_conflicts/rules.py` | `tests/test_m4.py::test_deny_priority_counterexample` |
| TRAP-23 | 授权到期点 | 多放行一次 | 半开生效窗 | `app/modules/m3_grants/rules.py` | `tests/test_m3.py::test_expiry_endpoint_excluded` |
| TRAP-31 | 别名登记授权 | 拒绝静默失配，访问显示持续受权 | 授权入算前归并别名，未知资源拒绝登记 | `app/modules/m3_grants/rules.py` | `tests/test_m3.py::test_alias_deny_not_silently_inert` |
| TRAP-32 | 跨月拒绝两视图分歧 | 按月扩成整月或重复计 | 连续区间权威，按月只裁剪投影 | `app/modules/m7_coverage/rules.py` | `tests/test_m7.py::test_cross_month_deny_projection` |
| TRAP-33 | 空档内无访问 | 整段空档不可见 | 按复查范围扫段，空档三态入结论 | `app/modules/m7_coverage/rules.py` | `tests/test_m7.py::test_gap_visible_without_access_inside` |
| TRAP-34 | 重跑同一输入 | 覆盖版本膨胀 | 结论内容寻址，INSERT OR IGNORE | `app/store.py` | `tests/test_m7.py::test_same_input_adds_no_coverage_version` |
| TRAP-35 | 切换覆盖版本失败 | 旧版证据被覆盖 | 版本条件更新，冲突保留旧版 | `app/store.py` | `tests/test_m7.py::test_switch_stale_keeps_old_evidence` |
| TRAP-36 | 封存依据断开 | 按陈旧行状态归档 | 封存只接受覆盖结论并逐行复核 | `app/modules/m8_seals/rules.py` | `tests/test_m8.py::test_seal_rejects_detached_row` |

## 覆盖结论

覆盖结论按（主体，规范资源，分区）给出复查范围内的三态覆盖：allow 覆盖内、deny 显式拒绝、gap 覆盖空档（无任何授权的默认拒绝）。连续有效区间为权威结论；按月展开是同一区间在自然月边界上的裁剪投影，跨月拒绝不扩整月、不重复计，两种视图由构造保证一致。资源别名在访问采信（M2）与授权定版（M3）两侧都先归并再计算，结论中不出现别名。落入空档或显式拒绝的越权放行逐条链接到所在区间与规则证据。结论内容寻址得到coverage_id，同源重跑不新增版本；切换生效版本需携带当前版本号，冲突返回409且旧版证据保留。封存（M8）只接受这份结论：缺少结论或任何一行与结论矛盾都拒绝归档。

## 对账规则

输入原始逻辑行=最终采纳来源行+隔离来源行+重复行+空白行+分段表头。派生记录用_sources保存完整来源，因此分组不丢行。业务预期合计与上游申报合计之差等于逐行差异之和。结果按输入摘要、规则版本及参数产生唯一批次，事务写入；同源重跑只复用已有批次。

## 已知不覆盖

4MB以上文件需预先按业务键分批；不模拟生产支付与外部回调。人工复核只变更批次状态，不改写原始记录。
