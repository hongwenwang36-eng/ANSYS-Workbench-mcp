# 结构与动力学实机基准

在仓库根目录运行下列命令，使用当前 MCP 后端的 MAPDL 和 Workbench 配置。

```powershell
.\.venv\Scripts\python.exe examples\mechanics\verify.py
.\.venv\Scripts\python.exe examples\mechanics\workbench.py
```

可以在命令后指定一个或多个案例，例如 `contact plastic prestress`。每次运行生成独立的 `runs/mechanics/bench-*` 或 `workbench-*` 目录。程序成功返回 0，任何检查失败返回 1。

| 文件 | 用途 |
|---|---|
| `verify.py` | 用 `run_mapdl_input` 求解九类基准并核对独立解析解 |
| `workbench.py` | 通过 `run_workbench_journal` 建立九个 Mechanical APDL 系统，更新、保存、关闭工程后重开，检查系统和数值 |
| `decks/*.inp` | 可编辑 APDL 模型及分析设置片段，由入口组装完整输入 |
| `checks.csv` | 本次实测值、参考值和通过情况 |
| `mechanics.wbpj` 及 `mechanics_files/` | 可重开的 Workbench 工程，必须一起保留 |
| `benchmark.inp`、`bench.db`、`bench.rst` | 独立运行的完整输入、模型数据库和结果 |
| `bench000.png` 或 `file000.png` | 求解器生成的位移或应力云图 |
| `response.csv` | 谐响应频率—实位移或瞬态时间—位移，两列分别为 Hz/m 或 s/m |
| `reopen.log`、`tool_result.json` | Workbench 重开证据和 MCP 执行回包 |

## 模型与独立参照

所有案例采用 m、kg、s、N、Pa。核心模型由两段等长轴向 SOLID185 实体组成，每段长度和截面积均为 1，弹性模量为 10000，泊松比为零。两个自由截面各带 1 kg 集中质量。轴向自由度矩阵为

```text
K = 10000 * [[2, -1], [-1, 1]]
M = [[1, 0], [0, 1]]
```

`verify.py` 在求解器外计算特征值、振型和传递函数，与 MAPDL 输出比较。

| 案例 | 物理设置与检查量 |
|---|---|
| static | 末端 100 N，检查末端位移 0.02 m |
| contact | 两块实体之间面对面无摩擦接触，施加总压缩 0.02 m，检查反力 -100 N |
| plastic | 双线性各向同性硬化，屈服 50 Pa、切线模量 1000 Pa，总拉伸 0.02 m，检查反力 55 N。横向允许塑性收缩 |
| modal | 检查上述两自由度系统第一频率 9.83631643083466 Hz |
| prestress | 两根 LINK180 各承受 10 N 张力，中央质量 1 kg，横向支撑刚度 100 N/m，预应力模态频率 sqrt(120)/(2π) |
| harmonic | 1 至 5 Hz、恒幅 100 N、无阻尼，检查 5 Hz 位移并导出五行频响。频率低于第一共振 |
| transient | 零初值、100 N 阶跃，400 子步计算至 0.02 s，检查末端位移并导出全部时程 |
| spectrum | 基底加速度响应谱恒值 1 m/s²，两模态按 SRSS 组合，检查组合位移 |
| random | 1 至 100 Hz 单边力 PSD 为 1 N²/Hz，模态阻尼比 0.02。求解器外对复传递函数的模平方积分，检查位移 RMS |

除 random 为 3% 外，数值相对误差容差为 0.5%。这些阈值属于本组基准。程序还检查求解退出状态、日志错误、结果和数据库文件、云图文件以及历程行数。后处理已用 Pillow 独立解码核查，详见 [实机记录](VALIDATION.md)。

## 操作中已验证的细节

- Workbench 会在用户 APDL 输入后追加完成标记脚本。入口为 Workbench 组装输入时会移除独立批处理使用的 `/exit,nosave`，使追加脚本能够执行。
- 响应谱组合在 POST1 读取当前 job 的 `.mcom`。PSD 位移 1σ 从 `SET,3,1` 提取。
- 谐响应显式使用 `KBC,1` 保持各频率载荷幅值。导出时按频率子步选择实部，避免把复结果记录数当作频率点数。
- 接触采用本算例验证过的 FKN 与 FTOLN。默认设置曾给出收敛但偏低 20% 的反力，因此验证同时核对解析反力。
- 独立模态云图显示归一化振型。随机振动显示 1σ 位移，响应谱显示 SRSS 组合量。
- 当前 Workbench 基准使用 Mechanical APDL 系统。原生 Mechanical 的树对象、接触 GUI 和结果对象需要对应的 Mechanical 验证工程。
