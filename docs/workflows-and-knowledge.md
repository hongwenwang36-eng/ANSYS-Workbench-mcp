# 0.6.0 工具与验收

本版沿用 Workbench journal、Mechanical 内置脚本、Fluent journal、MAPDL、CFX 和 ICEM 批处理。原有工具名及参数继续有效。新增接口返回结构化对象，原有接口仍可返回 JSON 文本。安装依赖后重新连接 stdio 服务即可加载新工具。

## 从知识库找到可检查的依据

首次检索自动建库。默认资料包括仓库内的技能、实例、验证文档、诊断规则和桥接脚本。索引保存在 MCP 主目录的 `runs/knowledge/index.sqlite`。已有本地帮助或内部算例可调用 `update_knowledge_base` 添加文件或目录，例如：

```json
{"sources":[{"path":"D:/CAE/help/fluent","software":"Fluent","module":"fluids","version":"2025 R1","kind":"reference"}]}
```

将示例路径替换为实际目录。支持可提取文字的 PDF、HTML、Markdown、文本、日志和常用求解器脚本。PDF 返回页码与页内行号，HTML 返回提取后文本行号，脚本返回原文件行号。扫描件需先 OCR。重建会重新读取登记的来源，失败时读者继续使用上一次成功索引。`replace_sources=true` 用于替换外部来源清单，默认库始终保留。

`search_commands` 接受例如 `{"query":"AddDataTransfer","module":"multiphysics","version":"2025 R1"}`。`search_examples` 查算例，`search_errors` 查错误与处置资料，`search_knowledge` 跨类别检索。可按 software、command_type、module、version 精确过滤，版本未知的记录只在未限定版本时返回。通过 `get_document` 的 document_id、offset、limit 可分页回读索引原文。回答中应给出命中文件和位置，调用命令前核对上下文。

默认检索在本机完成，使用 SQLite FTS5/BM25、语料训练的 TF-IDF/LSA 向量、倒数排名融合，并根据查询词覆盖和短语匹配重排。可选安装 `sentence-transformers` 并将 `ANSYS_RAG_EMBEDDING_MODEL`、`ANSYS_RAG_RERANK_MODEL` 指向本地双编码器与交叉编码器模型目录。更换向量模型后重建索引。设计参考了 [Foam-Agent](https://github.com/csml-rpi/Foam-Agent) 和 [Sentence Transformers](https://github.com/huggingface/sentence-transformers)。

## 读取、修改和恢复模型

1. 将 `.wbpj` 或 Fluent case 传给 `inspect_model`。Workbench 先读取系统名称，再指定 Mechanical 的内部 system 名称以获取体、面、材料、网格和载荷。Fluent 二维模型需指定 `dimension="2d"`。
2. 将返回的 report 路径传给 `inspect_geometry`、`inspect_mesh`、`get_boundary_conditions` 或 `audit_model`。独立 Meshing 的 mesh-stats.json 也可用于查看网格质量。报告只覆盖已列出的检查，工程载荷、自由度约束和湍流模型适用性仍由具体工况决定。
3. `edit_model` 的 change 包含 field、target、value 和可选 faces。Workbench 参数使用 P1 等内部名；Mechanical 材料、载荷使用对象 ID，局部网格使用面号和带单位尺寸；Fluent 使用实际区域名。支持字段由 MCP 输入 schema 列出。示例为 `{"field":"magnitude","target":"31","value":"90 [C]"}`，对象 ID 取本次报告。工具返回改后的副本路径，重开后以 `compare_model` 对比报告。若修改输入影响结果，另行更新或求解。
4. `snapshot_model` 保存工程及其配套目录或单个 Fluent case 的 SHA-256 清单。`restore_model` 校验并还原到新目录。外部引用的 CAD、求解器脚本、单独存放的 Fluent data 等文件应随工程另外归档。

## 工作流、故障诊断与回滚

`start_workflow` 接受按依赖排序的 steps。以下参数为同一工作流内的普通网格步骤示例。geometry_file 需替换为实际输入。

```json
{"steps":[{"name":"mesh","tool":"generate_ansys_mesh","arguments":{"geometry_file":"D:/CAE/bar.step","element_size_mm":4.0},"mesh_min_quality":0.5,"result_outputs":{"grid":"mesh_file","quality":"statistics_file"},"repairs":[{"category":"mesh","arguments":{"element_size_mm":3.0}}]}]}
```

`mesh_min_quality` 是算例给定的最低 Element Quality。原生 Meshing 输出到独立子目录，result_outputs 将工具结果中的文件路径命名为下游可引用的产物。对固定文件名使用 outputs。下一阶段设置 `depends_on:["mesh"]` 和 `inputs:{"mesh-stats.json":"@mesh/quality"}`，工具会复制上游通过验收的文件。输入格式应与下游求解器一致。工程目录和多文件重启动数据需要完整传递。

每次重试有独立工作目录。诊断命中预先指定的 category 才使用下一条 repairs，最多三次，保留每次的参数、日志、失败证据和有效输出。相对路径输出在本次目录内；用户 journal 内显式写入的外部路径由该脚本自行管理。物理参数变化须由调用方明确给出。停止后原始输入仍可作为基准，模型编辑可使用已验证的快照回滚。通过 `get_workflow` 查询状态，`resume_workflow` 对账中断编排器的持久化作业，`stop_workflow` 终止当前作业并停止后续阶段。

## 验证数值结果

| 工具 | 输入及判据 |
| --- | --- |
| verify_simulation | metric,unit,value 长表，逐项检查给定上限与下限。适用于残差、应力、网格质量等。 |
| verify_physics | 同格式长表，为各量指定带符号系数、同一单位、参考值和容差。例如对界面热流定义 terms 为两侧各 +1，reference 为 0，atol 为工程选定的 W 数。 |
| verify_refinement | spacing,metric,unit,value 表，按尺度排序，至少三档。最后两档变化要在容差内，且不超过前一对的变化。适用于网格和时间步敏感性。 |
| verify_coupling | 原生双向力/位移接口 CSV，检查时间步是否完整、每步最后迭代的两项 RMS 以及源端与目标端总力矢量差。提供终止时间、RMS 阈值、绝对与相对力容差。 |

`verify_physics` 的通过条件是绝对误差不超过 atol + rtol × scale。未指定 scale 时，使用参考值及各带权分项的最大绝对值。工作流可给出 metrics_csv 与 criteria，将 CSV 验收纳入步骤完成条件。

## Windows / Ansys 2025 R1 实测

- 参数化热工程的 P1 由 100 调到 85，保存并在新 Workbench 进程重开后读回 85。本项验证的是参数持久化。
- Mechanical 热工程读回 625 个单元、3396 个节点及中文材料名。指定 Hot 边界温度为 90 °C，重开副本后读回 90 °C。
- 二维 Fluent 共轭传热 case 的 inlet 速度由 0.10 改为 0.15 m/s。新 Fluent 进程重开改后 case，读回 0.15 m/s。
- MAPDL 热传导首次运行故意省去结果导出，编排器检测到缺失产物，按预设修复重新运行相同物理模型。Workbench 下一阶段读取第二次的输出，中点温度为 59.9999999979 °C，端面热流不平衡为 2.90×10⁻⁹ W。
- 重新检查既有 Fluent–MAPDL 双向耦合原始界面 CSV。10 个时间步均通过，终止时间 1 s，使用 RMS 上限 0.01、总力绝对容差 10⁻⁹ N、相对容差 0.001。
- 普通 Meshing 读取 STEP 几何并按 4 mm 尺寸划分，产生 625 个单元和 3396 个节点；重开前后的最小 Element Quality 均为 0.99999999996，工作流接受了网格文件与统计文件。
