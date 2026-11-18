---
name: ansys-thermal
description: 完成稳态和瞬态热分析，处理热源、对流、辐射、接触热阻及能量平衡。
---

读取导热率张量与材料轴、热源、规定温度、对流换热系数及环境温度、辐射发射率与环境，瞬态还需要初温、密度和比热。辐射采用一致的绝对温标。热接触明确按总热阻还是单位面积热阻输入。

使用 `create_steady_state_thermal_system_live` 或 `create_transient_thermal_system_live`，在 Mechanical Model 中生成网格和热边界，或用 `run_mapdl_input` 运行等价热单元模型。保存 .rth 并核对结果时刻。检查热边界的选择集面积、热源体积以及通量符号。

稳态对整个控制体积分输入功率和输出功率；瞬态积分净热量并与内能变化对比。用解析热阻、热扩散解或有依据的实验值验证指定位置温度。导出温度及热流密度云图、热流率和时间历程 CSV。将温度传给结构时连同坐标、单位、参考温度和载荷步交给耦合流程。


配套可复跑基准与适用范围见 [examples/thermal](../../../examples/thermal/README.md)。工作目录以仓库根目录为准，运行产物保存到 runs。
