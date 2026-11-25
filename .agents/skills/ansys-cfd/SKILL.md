---
name: ansys-cfd
description: 使用 Fluent 或 CFX 求解稳态、瞬态、流体传热、旋转流、多相及空化。
---

先核对流体域、材料物性、网格尺度、壁面运动与参考系、边界类型和压力基准。按 Reynolds 数、壁面分辨率及问题定义选择黏性模型。热问题指定能量方程与热边界；旋转机械区分相对与绝对速度。

- Fluent 用 `run_fluent_journal` 执行与本机版本匹配的 .jou，读取网格、检查区域和网格、设置材料/边界、初始化或从匹配的 case/data 续算，保存本轮 .cas.h5/.dat.h5 及 transcript。
- CFX 用 `run_cfx_pre_session` 执行 .pre 并验证新 .def，`run_cfx_solver` 求解，读 .out 和 .res，`run_cfx_post_session` 指向该 .res 导出图和数据。工程交付还需重开 Workbench 验证 Results 可加载本轮结果。
- 多相流先确定界面捕捉、混合或分散相模型，输入相物性、体积分数及相间作用。验证各相体积分数范围、总和与分相质量。空化校对绝对压力、操作/参考压力和饱和蒸气压，核查低压区及汽相体积分数，检查对网格和时间步的敏感性。

按稳态监测量是否稳定或瞬态终止时刻、每步残差和质量守恒验收。有能量方程时核对焓通量和壁面热流。写出带区域和方向的流量、压降、力或力矩，并用统一色标、视角和单位生成所需云图。


配套可复跑基准与适用范围见 [examples/fluids](../../../examples/fluids/README.md)。工作目录以仓库根目录为准，运行产物保存到 runs。

用 `inspect_model` 读取 Fluent case 时给出实际的 `dimension`，从 `get_boundary_conditions` 返回的区域名选择入口或出口。用 `edit_model` 修改副本并重开核对。连续性检查用 `verify_physics` 汇总带符号的进出口质量流量，单位统一为 kg/s。
