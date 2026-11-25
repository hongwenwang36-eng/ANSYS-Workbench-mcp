"""Local engineering sources with reproducible page and line locations."""

from bisect import bisect_left
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict

FORMATS = {
    ".md",
    ".txt",
    ".pdf",
    ".html",
    ".htm",
    ".inp",
    ".dat",
    ".ccl",
    ".cse",
    ".jou",
    ".py",
    ".wbjn",
    ".pre",
    ".tcl",
    ".rpl",
    ".log",
    ".out",
}
SKIP = {".git", ".venv", "__pycache__", "node_modules", ".ruff_cache"}
ALIASES = {
    "thermal": "热分析 热传导 温度 热流 温升 稳态传热 瞬态传热 conduction heat temperature",
    "structural": "结构 静力 应力 变形 位移 塑性 接触 mechanics static stress displacement",
    "dynamics": "动力学 模态 振动 固有频率 谐响应 响应谱 随机振动 modal frequency harmonic spectrum vibration",
    "fluids": "流体 流动 压降 空化 空蚀 气蚀 共轭传热 CFD Fluent CFX cavitation",
    "multiphysics": "流固耦合 双向耦合 力 位移 热应力 FSI System Coupling transfer interface",
    "meshing": "网格划分 网格质量 尺寸控制 meshing mesh ICEM sizing",
    "geometry": "几何 参数化 命名选择 SpaceClaim geometry CAD",
    "diagnostics": "排错 诊断 许可证 发散 不收敛 错误 license convergence failure",
}


# Expand engineering terms that occur in Chinese requests but have English command names.
QUERY_TERMS = {
    "谐响应": "harmonic",
    "响应谱": "spectrum",
    "随机振动": "random vibration",
    "模态": "modal modes",
    "预应力": "prestress",
    "瞬态": "transient",
    "静力": "static",
    "接触": "contact",
    "塑性": "plastic",
    "空化": "cavitation",
    "共轭传热": "cht",
    "流固耦合": "fsi coupling",
    "网格尺寸": "sizing",
    "热膨胀": "expansion",
    "稳态": "steady",
    "温度": "temperature",
    "零主元": "zero pivot",
    "许可": "license",
}


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    module: str = ""
    version: str = ""
    kind: str = ""
    software: str = ""
    command_type: str = ""


def default_sources(root):
    return [
        Source(path=str(root / path), version="2025 R1" if path == "examples" else "")
        for path in (
            "README.md",
            "docs",
            "examples",
            ".agents/skills",
            "ansys_workbench_bridge.wbjn",
            "ansys_meshing.wbjn",
            "icem_cfd_bridge.tcl",
            "simulation_checks.py",
            "ansys_mcp/journals",
        )
    ]


def files(source):
    root = Path(source.path).expanduser().resolve(strict=True)
    if root.is_file():
        if root.suffix.lower() not in FORMATS:
            raise ValueError(f"Unsupported document format: {root}")
        yield root
        return
    for path in sorted(root.rglob("*")):
        if (
            path.suffix.lower() in FORMATS
            and not SKIP.intersection(path.relative_to(root).parts)
            and path.is_file()
        ):
            yield path


def metadata(path, source):
    name = path.as_posix().lower()
    module = source.module
    if not module:
        module = next((key for key in ALIASES if key in name), "")
    if not module:
        module = next(
            (
                key
                for pattern, key in (
                    ("mechanics", "structural"),
                    ("cfd", "fluids"),
                    ("fsi", "multiphysics"),
                    ("simulation_checks", "diagnostics"),
                )
                if pattern in name
            ),
            "workbench",
        )
    stem = path.stem.lower()
    if (
        stem
        in {"harmonic", "random", "spectrum", "transient", "extract_modes", "prestress"}
        and "mechanics" in name
    ):
        module = source.module or "dynamics"
    if "fsi" in stem or stem == "plate":
        module = source.module or "multiphysics"
    kinds = {"reference"}
    if "/examples/" in name:
        kinds.add("example")
    if path.suffix.lower() not in {
        ".md",
        ".pdf",
        ".html",
        ".htm",
        ".txt",
        ".log",
        ".out",
    }:
        kinds.add("command")
    if path.suffix.lower() in {".log", ".out"} or module == "diagnostics":
        kinds.add("error")
    suffix = path.suffix.lower()
    languages = {
        ".wbjn": "WBJN",
        ".inp": "APDL",
        ".dat": "APDL",
        ".rpl": "Tcl",
        ".tcl": "Tcl",
        ".jou": "TUI",
        ".ccl": "CCL",
        ".cse": "CSE",
        ".pre": "CFX-Pre",
        ".py": "Python",
    }
    command_type = source.command_type or languages.get(suffix, "")
    software = source.software
    if not software:
        software = next(
            (
                product
                for marker, product in (
                    ("cfx", "CFX"),
                    ("icem", "ICEM CFD"),
                    ("fluent", "Fluent"),
                    ("mechanical", "Mechanical"),
                    ("meshing", "Ansys Meshing"),
                )
                if marker in name
            ),
            "",
        )
    if not software:
        software = {
            ".wbjn": "Workbench",
            ".inp": "MAPDL",
            ".dat": "MAPDL",
            ".jou": "Fluent",
            ".cse": "CFD-Post",
            ".ccl": "CFX",
            ".pre": "CFX-Pre",
        }.get(suffix, "")
    return (
        module,
        source.version,
        [source.kind] if source.kind else sorted(kinds),
        software,
        command_type,
    )


def pages(path):
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        for i, page in enumerate(reader.pages, 1):
            yield i, page.extract_text() or ""
        return
    raw = path.read_bytes()
    if b"\0" in raw and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ValueError("binary content")
    for enc in (
        "utf-8-sig",
        "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "gb18030",
        "cp1252",
    ):
        try:
            body = raw.decode(enc)
            break
        except UnicodeError:
            continue
    else:
        raise ValueError("unrecognized encoding")
    if suffix in {".html", ".htm"}:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(body, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        body = soup.get_text("\n", strip=True)
    yield 0, body


def chunks(body, size=1500, overlap=220):
    # Keep original line numbers, including for long single-line input.
    newlines = [i for i, c in enumerate(body) if c == "\n"]
    start = 0
    while start < len(body):
        end = min(start + size, len(body))
        if end < len(body):
            boundary = body.rfind("\n", start + size // 2, end)
            if boundary >= 0:
                end = boundary + 1
        part = body[start:end]
        if part.strip():
            yield (
                bisect_left(newlines, start) + 1,
                bisect_left(newlines, end - 1) + 1,
                part,
            )
        if end == len(body):
            break
        start = end - overlap


def tokens(text):
    parts = re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]+", text.casefold())
    words = []
    for part in parts:
        if part[0].isascii():
            words.append(part)
            if "_" in part:
                words.extend(x for x in part.split("_") if x)
        else:
            words.extend(part[i : i + 2] for i in range(max(1, len(part) - 1)))
    return words
