# 仿真 Skill 与运行方法

在本仓库目录中使用 Codex，项目 Skill 放在 .agents/skills。修改 MCP 后需要重新连接服务，以加载新的工具定义。现有解释器使用 .venv/Scripts/python.exe，依赖在 requirements.txt。

| Skill | 范围 |
|---|---|
| ansys-workflow | 任务定义、分析系统、执行状态、工程交付 |
| ansys-geometry | SpaceClaim 几何、命名选择、参数化 |
| ansys-meshing | Ansys Meshing、ICEM、质量及网格收敛 |
| ansys-structural | 静力、接触、塑性、大变形 |
| ansys-dynamics | 模态、预应力模态、谐响应、瞬态、响应谱、随机振动 |
| ansys-thermal | 稳态与瞬态热、热边界及能量检查 |
| ansys-cfd | Fluent、CFX、流体传热、多相、空化 |
| ansys-multiphysics | 热结构、共轭传热、单向与双向流固耦合 |
| ansys-parametric | Workbench 设计点、敏感性及优化流程 |
| ansys-diagnostics | 日志定位、恢复和重试依据 |
| ansys-verification | 带单位的数值验收 |
| ansys-postprocessing | 云图、曲线、数据和可重放后处理 |

## 后台计算

start_ansys_job 接收 tool、arguments 和可选的 UUID request_id。它复用现有批处理工具，在独立工作进程内运行。相同 request_id 与相同参数返回已有任务，参数不一致则报错。工作目录使用绝对路径，每个正在运行的算例使用自己的目录。

```python
import json
import uuid
from pathlib import Path
import mcp_server as mcp

request_id = str(uuid.uuid4())
job = json.loads(mcp.start_ansys_job(
    "run_mapdl_input",
    {"input_file": str(Path("case/model.inp").resolve()),
     "workdir": str(Path("case").resolve()), "timeout_seconds": 3600},
    request_id))
print(job["job_id"])
# 保存 job_id，重新连接后仍可查询。
print(mcp.get_ansys_job(job["job_id"]))
# 需要中止该任务时调用 mcp.stop_ansys_job(job["job_id"])。
```

状态包括 starting、running、stopping、stopped、finished、failed 和 interrupted。finished 表示工具执行成功，物理判据由验证工具和算例脚本检查。结果记录在 runs/jobs，console.log 持续写入标准输出；MAPDL .out 等求解器专用日志位于对应算例目录。启动器以挂起状态加入 Windows Job Object，随后恢复执行；取消终止该作业中全部进程。通过系统代理另行启动的进程（例如 Microsoft Store 应用别名）可能脱离作业，脚本调用解释器时使用真实可执行文件路径。外部调度器或远程 MPI 进程需按其自身管理接口检查。

独立耦合入口 run_system_coupling_script 运行 System Coupling Python 脚本，可用 ANSYS_SYSTEM_COUPLING 指定 systemcoupling.bat。创建脚本时使用与安装版本对应的 DatamodelRoot 等 API。

## 数值与日志工具

verify_simulation 的输入 CSV 使用 metric、unit、value 三列。criteria 是指标名、单位和闭区间上下界的列表。每个指标至少有一个界限，缺值、重复指标、单位不一致、NaN 或无穷值均不能通过。验证值的来源由求解器后处理脚本记录，检查上下界不能替代原始结果追溯。

```python
from simulation_checks import MetricLimit
print(mcp.verify_simulation("case/metrics.csv", [
    MetricLimit(metric="reaction", unit="N", minimum=99.5, maximum=100.5)
]))
print(mcp.diagnose_ansys_log("case/model.out"))
```

diagnose_ansys_log 返回匹配行号、错误类别和排查方向。匹配词覆盖许可、网格、约束、收敛、文件和脚本错误；没有匹配时仍需查看求解器退出原因及数值证据。

## 复跑与证据

- [结构和动力学](../examples/mechanics/README.md)
- [热、热结构和 Workbench 设计点](../examples/thermal/README.md)
- [流体及耦合](../examples/fluids/README.md)
- [ICEM 六面体网格](../examples/meshing/README.md)

测试命令为 .venv/Scripts/python.exe -m unittest discover -s tests -v。数值基准由各示例入口实际调用 ANSYS，依赖本机安装与有效许可。验证记录中的版本和算例范围构成已实测能力边界。
