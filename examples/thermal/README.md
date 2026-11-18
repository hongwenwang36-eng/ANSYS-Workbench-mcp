# 热分析、设计点与热膨胀验收

最近实机数值、工程与节点误差记录见 [VALIDATION.md](VALIDATION.md)。

在仓库根目录运行。每次执行都会在 `runs` 下生成带时间戳的新目录，保留输入、求解器原始结果和日志。

```powershell
.\.venv\Scripts\python.exe examples/thermal/run.py
.\.venv\Scripts\python.exe examples/thermal/run_workbench.py
.\.venv\Scripts\python.exe examples/thermal/run_mechanical.py
```

**MAPDL 数值验收**使用仓库的 `run_mapdl_input`。试件尺寸 0.1 × 0.02 × 0.02 m。稳态模型的导热率为 45 W/(m·K)，四周绝热，冷端 20 °C。当热端分别为 100、60 °C 时，中点温度应为 60、40 °C，两端反力热流的绝对值应为 14.4、7.2 W，且符号相反。`steady.dat` 是可编辑源文件。每一工况输出温度与热流密度 PNG、CSV、`.rth` 及求解器日志。

瞬态模型从 20 °C 均匀初温开始，在全绝热条件下施加 2 MW/m³ 体积热源，体积热容为 1 MJ/(m³·K)，温升率应为 2 K/s。`transient_expansion.dat` 随后把相同网格转换为结构单元，使用 `LDREAD,TEMP` 从 10 s 热结果读取节点温度，参考温度 20 °C，热膨胀系数 12 × 10⁻⁶/K。以三个正交平面上的法向约束容许自由膨胀，预期端部位移为 24 µm。原始结果包括 `.rth`、`.rst`、温度与轴向位移 PNG。九个标量的测量值、单位、参考值和判定写入 `verification.csv`，以相对容差 10⁻⁵ 核对本算例的离散精确解。

**Workbench 参数算例**使用 `run_workbench_journal` 调用 `parameter_study.wbjn`，将两段分析注册为 Mechanical APDL 组件，发布热端温度 P1 和中点温度 P2，更新 DP0 与保留数据的 DP1。脚本保存并重开 `thermal.wbpj`，从两个设计点的参数对象读回输入与输出，写入 `design_points.csv`。移动工程时请一并复制同名 `thermal_files` 目录。

**Mechanical 对象树算例**使用 `run_spaceclaim_script` 创建长方体，将几何导入 Workbench Steady-State Thermal，再通过 `mechanical.py` 创建两端温度边界、网格、温度及总热流密度结果。查看工程请打开 `thermal_mechanical.wbpj`，保持同名配套目录在旁。求解器原生云图为 `temperature.png` 和 `heat_flux.png`。同时以 `PlotData` 导出节点表 `temperature.csv` 和 `heat_flux.csv`，记录节点号、沿杆的归一化位置、数值和单位，并逐节点核对线性温度解析解，允许绝对偏差 10⁻⁴ °C。Mechanical 默认 Structural Steel 的热物性保存在工程 Engineering Data 中。

该组基准使用 SI 制和线性常物性，涵盖瞬态加热、固体导热及同网格温度传递。各向异性导热、接触热阻与辐射需要各自对应的模型和验证证据。

有关 APDL 变量发布、设计点更新和输出的 Workbench 脚本接口，请参见 [Ansys 2025 R1 Workbench Scripting Guide](https://ansyshelp.ansys.com/public/Views/Secured/corp/v251/en/wb2_js/wb2js_example4.html)。
