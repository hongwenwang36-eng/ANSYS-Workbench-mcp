---
name: ansys-diagnostics
description: 定位 ANSYS 启动、许可、脚本、网格、求解及导出错误，恢复批处理任务。
---

确定出错的阶段和本轮目录。后台任务用 `get_ansys_job` 获取状态和控制台路径，读 MAPDL .out/.err、Fluent transcript、CFX .out、Workbench journal 日志或 System Coupling 日志。用 `diagnose_ansys_log` 提取已知错误及行号；无匹配时从首个异常向前读取上下文。

路径/语法错误修复实际报错行，许可失败先检查模块和许可服务。奇异矩阵检查选择集、材料、接触和约束；负体积检查网格及大变形区域；数值发散检查边界、初值、时间步和监测量。记录每次改动及相应证据。修改用户规定的物理工况前先解决输入依据。

客户端断开后用相同 job_id 查询。只有明确需要停止本次后台任务才用 `stop_ansys_job`，记录中止时刻和最近完整结果。恢复计算时使用求解器支持的匹配重启文件，在新目录保留原日志。对重复原因仅在有新的修复依据且处于重试预算内时重跑。


后台任务、数值检查的参数与用法见 [运行说明](../../../docs/skills-and-validation.md)。
