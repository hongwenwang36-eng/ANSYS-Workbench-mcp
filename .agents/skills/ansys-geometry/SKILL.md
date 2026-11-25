---
name: ansys-geometry
description: 用 SpaceClaim 建立、导入、修复并参数化 Workbench 几何，维护命名面和接口。
---

读取输入长度单位、坐标原点、轴向、对称面和需要传给下游的体/面。导入后统计实体/片体、包围盒、体积和接触或间隙；壳与梁保留厚度、截面和方向。为 CFD 提取封闭流体域，耦合模型分别保留参与方。

独立脚本用 `write_ansys_script` 写 .py，经 `run_spaceclaim_script` 指定 script_api 和 expected_output 导出 .scdocx 或 STEP。Workbench 参数和关联更新要在几何容器中 Edit(IsSpaceClaimGeometry=True)，运行脚本，Exit 后刷新。用 `execute_workbench_script` 枚举 Parameters.GetAllParameters() 核对名称、单位、数值。

以几何位置、法向和邻接关系定位面，记录命名选择的面数和面积；变更尺寸后重查，防止拓扑变化把载荷移到其他面。交付重开后的模型及参数表；只要求几何时在该阶段验收。


配套可复跑基准与适用范围见 [examples/thermal](../../../examples/thermal/README.md)。工作目录以仓库根目录为准，运行产物保存到 runs。

用 `inspect_model` 指定 Mechanical 系统后，`inspect_geometry` 返回体 ID 与面 ID。替换 `geometry_file` 后重新读取 ID，重新核对载荷与命名面，旧拓扑上的面号可能已经改变。
