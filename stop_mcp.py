# -*- coding: utf-8 -*-
"""Signal the Ansys Workbench MCP bridge loop to stop."""

import os


mcp_home = os.environ.get("ANSYS_WORKBENCH_MCP_HOME", "").strip()
if not mcp_home:
    mcp_home = os.path.dirname(os.path.abspath(__file__))

stop_file = os.path.join(mcp_home, "stop.flag")
with open(stop_file, "w", encoding="utf-8") as f:
    f.write("stop")

print("Stop signal sent to Ansys Workbench MCP (" + mcp_home + ")")
