---
name: ansys-meshing
description: 用 Ansys Meshing 或 ICEM CFD 划分和检查结构、流体、薄层或耦合网格。
---

读取几何尺度、薄层/间隙、接触、壁面分辨率和用户指定网格工具。结构应力集中处控制单元阶次和尺寸，薄体可用扫掠或有物理依据的壳。CFD 按壁面处理估算首层高度并在计算后核对 y+。耦合面核对面积、朝向及映射覆盖率。

独立 Ansys Meshing 用 `generate_ansys_mesh` 从几何建立 Workbench Mesh 系统。用 `element_size_mm` 设置全局尺寸，或由 Meshing 自动选取。用 `controls_script` 提供当前 ANSYS 版本的 Meshing Python 脚本，设置局部尺寸、扫掠或边界层等控制。读取实际节点数、单元数和 Element Quality，核对重开工程后统计一致。使用 `.wbpj` 与同名 `_files` 目录恢复项目，`.meshdat` 为 Meshing 数据导出。已有项目的 Mesh 单元用 Workbench journal 编辑。

ICEM 可用 `run_icem_replay` 或 `start_icem_bridge` 加 `execute_icem_script` 执行 Tcl。阻塞边的节点数等于该边单元数加一。记录实际 Part、单元总数、厚度方向层数，导出 .uns/.fbc 或目标求解器网格并重新读入。

按单元类型报告质量指标定义、极值和坏单元位置。对负体积先修复几何/阻塞。网格无关性研究保持物理条件和后处理位置一致，比较至少两个细化级别的目标量，需要观察收敛阶或估计离散误差时再增加级别。


配套可复跑基准与适用范围见 [examples/meshing](../../../examples/meshing/README.md)。工作目录以仓库根目录为准，运行产物默认保存到 runs。

普通 Meshing 输出的 `mesh-stats.json` 可直接传给 `inspect_mesh`。在 Mechanical 工程上，`edit_model` 的 `face_sizing` 使用最新几何报告中的面号和带单位尺寸。以同一监测量比较至少三档网格的 `spacing,metric,unit,value` 表。
