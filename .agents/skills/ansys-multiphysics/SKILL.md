---
name: ansys-multiphysics
description: 设置热结构、流固、共轭传热和多参与方数据传递，检查界面与耦合收敛。
---

先确定参与方、传递方向、物理量、量纲和反馈是否影响上游。热结构顺序耦合先解温度，向结构映射指定时刻温度，确认热膨胀系数和零应变参考温度；对自由膨胀及受限膨胀分别检查变形与应力。

单求解器共轭传热要同时建立流体域、固体域及热耦合壁面；记录两侧面积积分热流的符号、界面温度和接触热阻。单向流固将压力/剪切映射到结构表面并对比积分合力和力矩。

双向 FSI 用 `create_cfx_mechanical_fsi_project_live` 建立工程，在 CFX 和 Mechanical 中分别建模、划网格、发布 System Coupling 区域。用 `get_system_coupling_status_live` 读取实际参与方、区域、变量，再用 `configure_cfx_mechanical_two_way_fsi_live` 创建载荷及位移传递，`configure_system_coupling_settings_live` 设置分析时间和耦合迭代，`run_system_coupling_solution_live` 运行。

核对两侧使用一致的坐标和时间、映射覆盖、力平衡、位移连续性以及最后一个耦合步的传递收敛。输出两侧结果、传递量与迭代历史。流热结构按实际反馈顺序串接上述步骤并保留各传递的源结果。


配套可复跑基准与适用范围见 [examples/fluids](../../../examples/fluids/README.md)。工作目录以仓库根目录为准，运行产物保存到 runs。

独立 Fluent–MAPDL 耦合使用参与方导出的 .scp 和 System Coupling Python 脚本，通过 run_system_coupling_script 运行，路径依赖在专用目录准备。用接口 CSV 对比两侧传递和终步时间。该路线产生独立求解器结果，工程内 Results 关联需另行验证。
