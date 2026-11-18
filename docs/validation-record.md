# 本地实机验收记录

开发目录为 D:/ansys-workbench-mcp，基线提交为 2950add0f46023c685d897135970c9e691b2f255。开始开发时已与 GitHub main 对照一致。验证环境为 Windows 和 ANSYS 2025 R1，数值运行日期为 2026-11-17，最终文件与测试复核日期为 2026-11-18。

## 服务端与 Skill

- 12 个 Skill 均通过 skill-creator 的 frontmatter、命名与占位符检查。
- MCP stdio 客户端真实连接并列出 56 个工具，通过协议调用 verify_simulation 校验 ICEM 输出。
- 23 项自动测试通过，覆盖既有接口、脚本写入、后台任务去重与跨进程查询、取消后代进程、数值缺失/重复/非有限值/单位不一致和日志行号。
- 后台真实静力案例在 runs/background-static 得到位移 0.02 m，求解状态 finished，保留 bench.rst、bench.db 和原生 PNG。
- 挂起创建求解器并显式加入 Windows Job Object 后，真实 MAPDL 取消测试在 runs/cancel-live3/cancel.json 记录三个进程，三个句柄均确认退出。取消适用于本地作业成员，外部服务调度的远程进程需使用对应调度接口。
- 后台任务状态在 runs/jobs 持久保存，重复调用使用相同 UUID request_id。

## 数值基准

| 范围 | 验收证据 |
|---|---|
| 静力、接触、塑性、模态、预应力模态、谐响应、瞬态、响应谱、随机振动 | [9 项解析基准与 Workbench 重开记录](../examples/mechanics/VALIDATION.md) |
| 稳态热、瞬态热、热结构、Parameter Set 与 Mechanical 原生结果 | [热分析实机证据](../examples/thermal/VALIDATION.md) |
| Fluent、CFX、共轭传热、空化、Fluent–MAPDL 双向 FSI | [五项流体与耦合验收记录](../examples/fluids/VALIDATION.md) |
| 独立 Ansys Meshing | 2025 R1 通过 MCP 导入 STEP，按全局 4 mm、端面 2 mm 划分 2700 个单元和 12815 个节点，最小 Element Quality 为 0.7071。保存网格、导出并重开工程后读回统计。 [调用与产物](../examples/meshing/README.md#独立-ansys-meshing) |
| ICEM 规则阻塞网格 | runs/mesh-cube-4，64 个 HEXA_8 单元，最小 Determinant 为 1，保存 .blk/.uns/.fbc 并重载 |

## 使用范围

结构 Workbench 验收使用 Mechanical APDL 系统，热组同时包含原生 Mechanical 对象树。独立双向 FSI 使用 Fluent、MAPDL 和 System Coupling，其证据对应这条实际路线。CFX–Mechanical 的 Workbench 双向耦合目前仍需完整物理算例验收。

Skill 中列出的辐射、各向异性导热、复杂接触、优化等工作流程，需要在具体任务中补充对应的模型和判据。此处的基准覆盖列出的模型、软件版本和载荷，不能直接推定所有模型组合都已经验证。

工程打开时保留同名 _files 目录。复跑程序在 runs 下建立独立目录，输入模板位于 examples。Git 忽略 runs 下的大型计算产物，仓库保留可编辑输入与复跑代码。
