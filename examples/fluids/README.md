# Fluent、CFX 与双向耦合基准

在仓库根目录执行，每次默认创建独立的 runs/fluid-类型-时间戳 目录。

```powershell
.\.venv\Scripts\python.exe examples/fluids/run.py duct
.\.venv\Scripts\python.exe examples/fluids/run.py cfx
.\.venv\Scripts\python.exe examples/fluids/run.py cht
.\.venv\Scripts\python.exe examples/fluids/run.py cavitation
.\.venv\Scripts\python.exe examples/fluids/run.py fsi
```

通过 `--output` 指定尚不存在的输出目录。对已经求解且有 solver.json 的目录，使用 `--post-only --output <目录>` 重新生成云图及验证记录。

| 案例 | 输入与验收 | 主要产物 |
|---|---|---|
| duct | 原创 256 单元二维矩形网格、无黏性剪切的对称上下边界、1 m/s 入口。检查出口平均速度偏差小于 10⁻⁵ m/s | duct.cas.h5/dat.h5、velocity.png、metrics.json/csv |
| cfx | 本机 CFX/examples/StaticMixer.def，检查求解目标达成、出口混合温度 300±0.01 K | mixer*.res/out、outlet.png/csv |
| cht | 原创 480 单元共形流体—固体二维网格，入口 300 K、外侧壁面 350 K，检查界面双侧热流绝对差小于 10⁻⁶ W 和出口温度范围 | cht.cas.h5/dat.h5、temperature.png、metrics.json/csv |
| cavitation | ANSYS 公开轴对称空化网格，液水与水蒸气混合模型、SST、绝对压力边界，检查六个终步残差均小于 10⁻⁵ | cav.cas.h5/dat.h5、vapor.png、残差验收 CSV |
| fsi | ANSYS 公开振动板 Fluent–MAPDL 双向耦合，计算至 1 s，检查两向传递 RMS 小于 0.01 和界面合力差小于 10⁻⁸ N | 两侧求解器结果、SyC/Interface-1.csv、MAPDL/fsi_post000.png |

CFX 基准读取安装附带的 .def，安装位置通过 MCP 的 ANSYS_CFX_SOLVE 配置获得。空化和 FSI 输入从 ansys/example-data 的固定提交下载，首次复跑需要网络。下载后的输入及全部原始结果保存在本次目录，项目源代码不包含厂商二进制模型。空化脚本保留上游 MIT 声明。固定版本为 c283ea5a153158b62fa429ae06e7cc802f7263c2。[上游数据](https://github.com/ansys/example-data/tree/c283ea5a153158b62fa429ae06e7cc802f7263c2)

本组使用仓库的 run_fluent_journal、run_cfx_solver、run_cfx_post_session、run_system_coupling_script 和 run_mapdl_input。Fluent 求解用 -g，图片后处理调用 gui=True 并添加 -gu，使批处理保留图形渲染能力。Python journal 用 solver.exit() 正常退出。求解器返回码和 journal 异常同时检查，旧日志中的失败不会混入本次后处理判定。

verification.json 与 metrics.csv 记录具体接受值，CSV 包含 metric、unit、value 三列。CFX 有带单位的 outlet.csv，FSI 的原始接口 CSV 保留全部迭代。自动验收覆盖所列算例，空化尚需网格敏感性、相质量平衡及实验对比才能用于定量预测。独立 FSI 基准验证 Fluent–MAPDL 参与方与 System Coupling CLI，CFX–Mechanical Workbench 的结果关联需要其对应工程验收。

已实测数值和路径见 [验证记录](VALIDATION.md)。
