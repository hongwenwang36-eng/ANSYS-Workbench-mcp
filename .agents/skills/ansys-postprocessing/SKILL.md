---
name: ansys-postprocessing
description: 从 Mechanical/MAPDL、Fluent 或 CFD-Post 导出结果云图、历程、积分量和数据。
---

确认加载的是对应设计点、本轮时间步或频率以及正确的结果文件。记录变量、单位、选择集、坐标系和分量。积分力和力矩要给出作用面、正方向、力矩轴和参考点；结构应力说明节点平均或单元结果。

MAPDL 在 /POST1 选择结果集，输出 PLNSOL/PLESOL 并使用 PNG 图形设备，时程用 /POST26 或逐结果集导出。Mechanical 在指定 Result 对象 Evaluate 后导出图片和数值。Fluent journal 选定 surface 与 contour，通过 hardcopy 导出 PNG，同时写 report definition 结果。CFD-Post 用 `run_cfx_post_session` 指定 result_file 和 .cse，选择域/截面、变量及模式，用 expected_output 验证输出。

比较工况时固定视角、坐标范围、色标和单位，报告极值与位置。检查 PNG 可解码、CSV 数值有限且行数符合对象或时间步数。交付原始结果、云图、数据、可重放脚本及打开入口。


配套可复跑基准与适用范围见 [examples/mechanics](../../../examples/mechanics/README.md)。工作目录以仓库根目录为准，运行产物保存到 runs。

Fluent 的 -g 会关闭图片图形设备。需要批处理导图时使用 run_fluent_journal 的 gui=True 和 extra_args="-gu"，使图形渲染保留且主界面隐藏。Mechanical 批处理中 ExportToTextFile 若产生空文件，可按配套热基准从 PlotData 导出节点值，并检查节点数、单位及解析误差。

Mechanical 2025 R1 重开工程后，温度结果类别是 DataModelObjectCategory.TemperatureResult，热流结果是 TotalHeatFlux。用 Solution.GetChildren 按实际类别取对象并断言数量，在 result.Activate() 后设置图形偏好。导出检查文件修改时间和大小，Workbench SendCommand 可能将编辑器内部错误保留在其日志中，主控应校验脚本生成的完成标记及产物。
