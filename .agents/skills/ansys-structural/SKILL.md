---
name: ansys-structural
description: 通过 Mechanical 或 MAPDL 完成线性静力、接触、材料或几何非线性分析并提取应力和反力。
---

确定材料、截面、接触/摩擦、载荷和支承，记录小变形或大变形、压力面法向、远程载荷参考点。预紧需要记录施加、锁定和后续加载的载荷步。

工程路径用 `create_static_structural_system_live` 创建 Static Structural，向 Mechanical 模型发送材料、网格、Named Selection、载荷与求解脚本。独立 APDL 经 `write_ansys_script` 写 .inp，`run_mapdl_input` 运行。核查最后收敛子步，读取 .rst、约束反力和力矩；接触问题同时检查开闭、穿透、滑移和接触压力。保留变形比例和结果坐标系。

用反力与外载平衡、简单算例的解析位移验证。固定端尖角应力奇异时记录提取距离与网格敏感性。导出位移/应力云图、反力及关键位置 CSV。


配套可复跑基准与适用范围见 [examples/mechanics](../../../examples/mechanics/README.md)。工作目录以仓库根目录为准，运行产物保存到 runs。

Workbench Mechanical APDL 组件会在输入文件后追加更新与参数处理命令，组件输入脚本应让执行返回 Workbench。独立批处理使用的 /exit 命令应在装配到该组件时移除，避免提前结束后续参数发布和更新。

单轴塑性验证允许材料的横向收缩，检查横向约束是否改变应力状态；用施加位移、截面积和材料切线模量推导轴向反力进行比较。
