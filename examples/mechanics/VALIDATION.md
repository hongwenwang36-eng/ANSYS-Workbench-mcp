# 实机验证记录

验证日期为 2026-11-17，环境为 Windows、Ansys MAPDL / Workbench 2025 R1（Build 25.1，UP20241202）。由仓库中的 `run_mapdl_input` 和 `run_workbench_journal` 执行。

直接批处理证据保存在 `runs/mechanics/bench-ftfdw0sn/`。WorkBench 工程的最终复跑保存在 `runs/mechanics/workbench-sl_50xfp/`，包括 `mechanics.wbpj`、`mechanics_files/` 和 `reopen.log`。重开日志包含九个系统名以及 `PROJECT_REOPENED`。

| 案例 | 实测 | 独立参照 | 相对误差 |
|---|---|---|---|
| 线性静力 | 0.02 m | 0.02 m | 0 |
| 无摩擦接触 | -99.9997500006 N | -100 N | 0.000250% |
| 双线性塑性 | 55 N | 55 N | 0 |
| 模态 | 9.83631643083 Hz | 9.83631643083 Hz | 0 |
| 预应力模态 | 1.74345504940 Hz | 1.74345504940 Hz | 浮点舍入量级 |
| 谐响应 5 Hz | 0.0266418630611 m | 0.0266418630611 m | 浮点舍入量级 |
| 瞬态 0.02 s | 0.0148003266099 m | 0.0148275879248 m | 0.183855% |
| 响应谱 SRSS | 0.000306593798618 m | 0.000306594194335 m | 0.000129% |
| 随机振动 RMS | 0.00373343150200 m | 0.00373343150222 m | 0.00000000596% |

九项直接运行均通过误差、日志、数据库、结果与云图文件检查。谐响应导出 5 个频率点，瞬态导出 400 个时间点。Workbench 前一次 `workbench-uc_3obu_` 运行已完成全部九项数值检查和工程重开。最终复跑进一步增加数据库、错误日志和历程行数检查，结果见同目录 `checks.csv`。

直接批处理九张图及最终 Workbench 九张图均经 Pillow 完整解码，尺寸为 1077 × 810。人工视觉检查了接触位移云图，色标、单位对应 SI 模型，图中几何与压缩方向一致。

接触默认穿透容差初次得到 -80 N。调整此基准的 FKN 和 FTOLN 后达到表中的误差。塑性基准释放横向收缩约束后与单轴解析解一致。Workbench 输入去除 `/exit,nosave` 后，内置完成标记脚本得以执行，全部系统更新成功。

这些基准验证了列出的物理设置及 MAPDL/Workbench Mechanical APDL 路线。单个细分算例的通过范围是其具体模型、材料和载荷，原生 Mechanical 树对象及复杂接触的能力应结合各自实机工程记录。

APDL 响应谱与随机振动命令参考 Ansys 官方 Structural Analysis Guide 的 Spectrum Analysis 和 Random Vibration 章节。

- [响应谱工作流](https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/ans_str/Hlp_G_STR6_6.html)
- [随机振动工作流与结果集](https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/ans_str/Hlp_G_STR6_8.html)
