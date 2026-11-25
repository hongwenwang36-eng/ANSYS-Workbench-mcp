---
name: ansys-parametric
description: 发布 Workbench 参数，运行设计点、敏感性分析及带停止条件的优化。
---

在 `execute_workbench_script` 或 `run_workbench_journal` 主控中查询 Parameters.GetAllParameters()，获取工程内的参数对象、单位及输入输出类型。记录当前设计点和初值，检查几何或求解参数实际发布到 Parameter Set。

逐点设输入并读回单位和值，执行更新，检查所有必需组件的状态。从该点读取输出或其结果目录，记录设计点编号、输入、输出、单位、求解终止原因和结果路径。需要重开对应工况时启用设计点数据保留。改变几何后重查命名面及网格。

敏感性计算说明差分步长、参数范围及约束；优化记录目标、设计变量、边界、初值、可行性、迭代上限及停止条件。失败设计点保留错误原因和空输出；极值候选在相同工况复算，并报告与基准点之差。


配套可复跑基准与适用范围见 [examples/thermal](../../../examples/thermal/README.md)。工作目录以仓库根目录为准，运行产物保存到 runs。

用 `snapshot_model` 保存基准，再用 `edit_model(field=parameter)` 修改输入参数，重开副本用 `compare_model` 对比参数。参数表达式改变后，求解输出须经设计点更新才能用于比较。
