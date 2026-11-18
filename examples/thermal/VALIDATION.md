# 热分析实机验证

2026-11-17，Windows、Ansys 2025 R1。运行使用仓库的 SpaceClaim、Workbench 和 MAPDL MCP 实现。

## MAPDL 数值基准

最终强化检查的运行目录为 `runs/thermal_20261117_220313_382044`。`verification.csv` 的九项全部通过，同时检查求解日志中的错误标志、非空 `.rth/.rst` 和 PNG 文件。输入、物理推导和复跑命令见 [README](README.md)。

| 指标 | 实测值 | 解析值 |
|---|---|---|
| 热端 100°C 时中点温度 | 59.9999999979°C | 60°C |
| 热端 100°C 时热端/冷端反力热流 | 14.4000000017 / -14.3999999988 W | 14.4 / -14.4 W |
| 热端 60°C 时中点温度 | 39.9999999986°C | 40°C |
| 热端 60°C 时热端/冷端反力热流 | 7.20000000109 / -7.19999999918 W | 7.2 / -7.2 W |
| 全绝热体积加热 5 s 温度 | 29.9999999998°C | 30°C |
| 全绝热体积加热 10 s 温度 | 39.9999999996°C | 40°C |
| 从热结果读取温度后的自由热膨胀 | 0.0000239999999995 m | 0.000024 m |

## Workbench 设计点

`runs/thermal_wb_20261117_220347_629474/thermal.wbpj` 包含稳态热参数分析和瞬态热—结构 APDL 组件。`design_points.csv` 确认 P1/P2 从工程中读取的 DP0 为 100/60°C，DP1 为 60/40°C。`workbench.log` 中的 `REOPEN_AND_DP_CHECK_PASSED` 是保存、重置、重新打开并重新读取设计点后的标记。配套 `thermal_files` 必须一起保留。

## Mechanical 原生模型与节点表

`runs/thermal_mech_20261117_215652_729590/thermal_mechanical.wbpj` 使用本轮 SpaceClaim 长方体、Mechanical 温度边界、网格和结果对象。`workbench.log` 中 `REOPEN_MECHANICAL_PASSED` 确认保存后重新打开工程。

通过 `PlotData` 导出 3396 个温度节点和热流节点记录，表中保留节点编号、轴向归一化坐标、数值及单位。逐节点比较 20 + 80x 的解析温度分布，最大绝对误差为 3.0518×10⁻⁶°C，验收上限为 10⁻⁴°C，结果记录在 `verification.json`。温度极值为 20°C、100°C。

原生温度和热流云图尺寸为 1600×1000，使用白底、固定导出尺寸，并由 Pillow 完整解码。早期 `ExportToTextFile` 在该批处理环境中产生空文件，最终脚本改为直接读取结果 `PlotData`。其他物性、辐射和热接触模型应使用各自的基准数据验收。

2026-11-18 最终导图复核已完成。重开工程后的温度类别确认为 TemperatureResult，按该类别重新定位并导出，refresh_verified_execution.json 同时确认脚本完成标记和 temperature.png 的修改时间更新。极值标签在激活结果后关闭，避免覆盖左侧时间文字。
