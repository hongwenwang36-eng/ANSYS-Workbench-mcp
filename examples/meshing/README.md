# Workbench 网格划分

## 独立 Ansys Meshing

向 `generate_ansys_mesh` 传入几何文件。`element_size_mm` 为可选的全局单元尺寸，省略时使用 Meshing 的自动尺寸。`project_dir` 为输出根目录，工具为每次调用创建独立的 `ansys-meshing-*` 子目录。

```json
{
  "geometry_file": "D:/cases/bar.step",
  "project_dir": "D:/cases/mesh",
  "element_size_mm": 4.0
}
```

如需局部尺寸等自定义控制，将适配当前几何的 Meshing Python 文件传给 `controls_script`。工具在独立 Mesh 单元中运行该脚本后统一生成网格。以 100 × 20 × 20 mm 的长方体为例，[face_sizing.py](face_sizing.py) 把 X 正端面细化到 2 mm。耗时任务可通过 `start_ansys_job` 提交同名工具和参数。

输出包括 `meshing.wbpj`、同名 `meshing_files`、`meshing.meshdat`、网格统计 JSON、可编辑 WBJN 和日志。打开工程时请一并保留工程文件夹。工具重开工程并读回节点数、单元数和 Element Quality 的最小、平均及最大值。网格质量是否满足具体用途由算例判据确定。

2025 R1 实测工程位于 `runs/meshing-step-final/ansys-meshing-yaqmkij4`。MCP 直接调用使用 STEP 长方体、全局 4 mm 和端面 2 mm，生成 2700 个单元和 12815 个节点，最小 Element Quality 为 0.7071。`mesh-stats.json` 和 `reopened-stats.json` 分别保留保存前与重开后的实测值，完整 MCP 返回见 `runs/meshing-step-final/execution.json`。

STEP 后台运行于 `runs/meshing-step-background/ansys-meshing-wo818m1g`，全局 4 mm 生成 625 个单元和 3396 个节点，工程重开通过。本机的 `.scdocx` 批处理导入出现过无法附加几何的错误。碰到该错误时先查看 `meshing.log`，可以用 STEP 重试；如果后续依赖命名选择，请在导入后核对名称与范围。

## ICEM 六面体网格基准

从仓库根目录使用虚拟环境运行以下 Python 调用，工作目录应是新目录。

```python
import json
from pathlib import Path
from tempfile import mkdtemp
import mcp_server

folder = Path(mkdtemp(prefix="icem-", dir="runs")).resolve()
reply = json.loads(mcp_server.run_icem_replay(
    str(Path("examples/meshing/cube.tcl").resolve()), str(folder)))
assert reply["ok"], reply
print(folder / "mesh.csv")
```

cube.tcl 创建 8 × 4 × 2 长方体阻塞，沿三个方向使用 9、5、3 个节点。导出 cube.blk、cube.uns 和 cube.fbc，重载 .uns 检查 64 个 HEXA_8 单元及最小 Determinant，再写 mesh.csv。2025 R1 实测最小 Determinant 为 1。

几何只有用于确定包围盒的对角线，本基准验证规则阻塞划分、导出与重载。物理边界的面命名与曲面投影应在实际模型中另行定义。
