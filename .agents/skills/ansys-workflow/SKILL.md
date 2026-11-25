---
name: ansys-workflow
description: 组织跨模块 Workbench 工程、选择分析系统、跟踪求解并交付可重开工程。
---

从目标量反推需要的物理场、载荷历程和求解顺序。例如温度引起的应力需要温度场、参考温度和约束，用户只要求模态时直接走动力学。读取已有工程的单位制、材料和命名选择，并列出仍影响问题定义的缺项。

1. 用 `check_ansys_installation` 查看可执行文件。实时模式用 `check_workbench_connection` 和 `get_project_info` 确认当前项目，再用 `probe_workbench_analysis_templates_live` 查看安装中可用模板。采用批处理时，以 `run_workbench_journal` 运行主控 WBJN，使工程和输出写入本工况目录。
2. 按任务调用同目录下的几何、网格、静力、动力、热、CFD、耦合或参数研究 Skill。Mechanical 脚本应在 Model/Setup 容器内通过 SendCommand 执行，保存、更新和设计点操作由 WBJN 执行。避免两个会话同时写同一个工程。
3. 长计算用 `start_ansys_job` 提交工具及其参数，保存 job_id 和输入。用 `get_ansys_job` 查询进度。超时后先查询同一个任务，发现异常再读日志并定位阶段。
4. 在求解器内提取用户要求的量，写出带单位的 CSV。按验收条件执行 `verify_simulation`。保存后重开 .wbpj，检查同名 _files、分析系统、设计点及结果加载。记录打开入口、图表、输入脚本、软件版本与实际验证到的步骤。


后台任务、数值检查的参数与用法见 [运行说明](../../../docs/skills-and-validation.md)。

`start_workflow` 以依赖顺序接收 steps，通过 `inputs` 中的 `@步骤名/输出文件` 传递已验收文件，每次尝试使用独立目录。用 `get_workflow` 读取作业号和数值验收记录。编排器中断后用 `resume_workflow` 对账；停止时用 `stop_workflow`。
