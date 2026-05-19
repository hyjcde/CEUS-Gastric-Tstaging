# 临床表格整理

这里保存从 `胃癌分期/` 原始目录回收并整理到正式 `dataset/` 口径下的临床表格资产。

当前目录包含三类内容：

- `raw/`：原始 Excel 表的副本，方便后续回溯
- `by_source/`：按来源工作簿和 sheet 拆开的 CSV
- `clinical_table_index.csv`：表格索引，记录每张表的来源、sheet、导出路径和行数
- `clinical_table_registry.csv`：统一汇总表，抽取了住院号、姓名、性别、年龄、肿瘤位置、CEA、CA199、病理、Lauren、T 分期等常见字段
- `center_name_registry.csv`：标准医院名称 ↔ 遗留目录/source 前缀 ↔ 入库状态对照表

注意事项：

- 这些表仍然是“原始临床表整理层”，还不是最终患者级注册表
- 不同年份和中心的表头并不完全一致，因此 `clinical_table_registry.csv` 保留了 `source_row_json` 方便追溯
- `2019.xlsx` 使用的是表内 `ID`，不是标准住院号，后续做患者级注册时需要单独处理
- 外部部分中心带有多个 sheet，当前做法是全部保留，只要该 sheet 里存在非空数据行

如果后续要继续补齐正式资产，建议顺序是：

1. 在当前表格层基础上生成患者级注册表
2. 补 `label_tstage` 和标签来源映射
3. 再做患者级 split 和分层统计
