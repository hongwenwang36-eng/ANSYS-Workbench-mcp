"""MCP contracts for source retrieval, native model operations and persistent workflows."""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import models, verification, workflows
from .rag import store
from .rag.documents import Source


def runtime():
    import mcp_server

    return mcp_server


def index():
    server = runtime()
    return server.RUNS_DIR / "knowledge" / "index.sqlite", server.SERVER_ROOT


def update_knowledge_base(
    sources: list[Source] | None = None, replace_sources: bool = False
) -> dict[str, Any]:
    """Rebuild the local knowledge index atomically. Add files/directories with optional metadata. Set replace_sources to replace the external source list."""
    return store.update(*index(), sources, replace_sources)


def search_knowledge(
    query: str,
    module: str = "",
    version: str = "",
    limit: int = 5,
    software: str = "",
    command_type: str = "",
) -> dict[str, Any]:
    """Find local ANSYS knowledge by keyword and vector similarity. Returns cited text with page or lines."""
    return store.search(
        *index(), query, "", module, version, limit, software, command_type
    )


def search_commands(
    query: str,
    module: str = "",
    version: str = "",
    limit: int = 5,
    software: str = "",
    command_type: str = "",
) -> dict[str, Any]:
    """Retrieve command and journal excerpts. Check the source and solver release before use."""
    return store.search(
        *index(), query, "command", module, version, limit, software, command_type
    )


def search_examples(
    query: str,
    module: str = "",
    version: str = "",
    limit: int = 5,
    software: str = "",
    command_type: str = "",
) -> dict[str, Any]:
    """Find indexed engineering examples with their original source and validation context."""
    return store.search(
        *index(), query, "example", module, version, limit, software, command_type
    )


def search_errors(
    query: str,
    module: str = "",
    version: str = "",
    limit: int = 5,
    software: str = "",
    command_type: str = "",
) -> dict[str, Any]:
    """Retrieve diagnostic documentation and indexed solver errors."""
    return store.search(
        *index(), query, "error", module, version, limit, software, command_type
    )


def get_document(document_id: str, offset: int = 0, limit: int = 8) -> dict[str, Any]:
    """Read stored source excerpts by document ID; paginate using the chunk offset."""
    return store.get_document(*index(), document_id, offset, limit)


class ModelEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Literal[
        "parameter",
        "geometry_file",
        "mesh_size",
        "face_sizing",
        "material",
        "magnitude",
        "boundary_scope",
        "add_temperature",
        "add_fixed_support",
        "end_time",
        "inlet_velocity",
        "outlet_pressure",
        "fluid_material",
        "viscous_model",
        "time_step",
    ]
    target: str = ""
    value: str | float = ""
    faces: list[int] = Field(default_factory=list)


def inspect_model(
    model_file: str, system: str = "", dimension: Literal["2d", "3d"] = "3d"
) -> dict[str, Any]:
    """Open a copy of a WBPJ or Fluent case; specify the Mechanical system name for geometry, mesh and loads."""
    return models.run(
        Path(model_file).resolve(),
        system,
        None,
        runtime().RUNS_DIR,
        runtime(),
        dimension,
    )


def edit_model(
    model_file: str,
    change: ModelEdit,
    system: str = "",
    dimension: Literal["2d", "3d"] = "3d",
) -> dict[str, Any]:
    """Apply one native edit in an isolated copy. Select Mechanical ObjectId/face IDs or a Fluent zone from inspect_model."""
    if (
        change.field
        in {"boundary_scope", "face_sizing", "add_fixed_support", "add_temperature"}
        and not change.faces
    ):
        raise ValueError("Specify geometry face IDs from inspect_model")
    return models.run(
        Path(model_file).resolve(),
        system,
        change.model_dump(),
        runtime().RUNS_DIR,
        runtime(),
        dimension,
    )


def report(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if data.get("kind") not in {"workbench", "fluent"}:
        raise ValueError(
            "Supply the model.json report returned by inspect_model or edit_model"
        )
    return data


def inspect_geometry(report_file: str) -> dict[str, Any]:
    """List Mechanical bodies, assigned materials and geometric face IDs from an inspected project."""
    return {"bodies": report(report_file)["mechanical"]["bodies"]}


def inspect_mesh(report_file: str) -> dict[str, Any]:
    """Get native Mechanical mesh counts and size from a model report, or quality data from Meshing mesh-stats.json."""
    data = json.loads(Path(report_file).read_text(encoding="utf-8-sig"))
    if "mechanical" in data:
        return {k: data["mechanical"][k] for k in ("nodes", "elements", "mesh_size")}
    if "nodes" in data and "elements" in data:
        return data
    raise ValueError("Expected mesh statistics or a Mechanical model report")


def get_boundary_conditions(report_file: str) -> dict[str, Any]:
    """Read scoped Mechanical analysis objects or native Fluent boundary settings from a report."""
    data = report(report_file)
    if data["kind"] == "fluent":
        return data["boundaries"]
    return {"analyses": data["mechanical"]["analyses"]}


def audit_model(report_file: str) -> dict[str, Any]:
    """Check native model evidence for materials, mesh and scoped boundary assignments."""
    return models.audit(report(report_file))


def compare_model(before_report: str, after_report: str) -> dict[str, Any]:
    """Compare two native inspection reports and return changed fields with both values."""
    return {"changes": models.compare(report(before_report), report(after_report))}


def snapshot_model(model_file: str, snapshot_dir: str) -> dict[str, Any]:
    """Copy a Workbench project and companion tree or a Fluent case with a SHA-256 manifest."""
    return models.snapshot(Path(model_file).resolve(), Path(snapshot_dir).resolve())


def restore_model(snapshot_dir: str, output_dir: str) -> dict[str, Any]:
    """Verify every snapshot member and restore to a fresh directory."""
    return models.restore(Path(snapshot_dir).resolve(), Path(output_dir).resolve())


def start_workflow(steps: list[workflows.Step]) -> dict[str, Any]:
    """Start an ordered dependency graph. Stage inputs and declared @step/output references in isolated attempt directories."""
    return workflows.create(runtime().RUNS_DIR / "workflows", steps)


def workflow_dir(workflow_id):
    return workflows.directory(runtime().RUNS_DIR / "workflows", workflow_id)


def get_workflow(workflow_id: str) -> dict[str, Any]:
    """Read persisted step progress, accepted artifacts, diagnosed attempts and validation results."""
    with workflows.state_record(workflow_dir(workflow_id)) as state:
        return state


def resume_workflow(workflow_id: str) -> dict[str, Any]:
    """Restart orchestration after a worker or host restart, reconciling the same durable solver jobs."""
    folder = workflow_dir(workflow_id)
    state = workflows.advance(folder)
    if state["state"] == "running":
        workflows.wake(folder)
    return state


def stop_workflow(workflow_id: str) -> dict[str, Any]:
    """Stop the active solver job and prevent later stages from starting."""
    return workflows.advance(workflow_dir(workflow_id), cancel=True)


def verify_physics(csv_file: str, checks: list[verification.Equation]) -> dict[str, Any]:
    """Check signed mass/energy/force balances and analytical references against a metric,unit,value CSV."""
    return verification.equations(Path(csv_file).resolve(), checks)


def verify_refinement(
    csv_file: str,
    metric: str,
    unit: str,
    relative_tolerance: float,
    absolute_tolerance: float = 0,
) -> dict[str, Any]:
    """Check convergence of a mesh/time refinement series with spacing,metric,unit,value columns."""
    return verification.refinement(
        Path(csv_file).resolve(), metric, unit, relative_tolerance, absolute_tolerance
    )


def verify_coupling(
    csv_file: str,
    end_time_s: float,
    rms_limit: float,
    force_rtol: float,
    force_atol: float,
) -> dict[str, Any]:
    """Verify end time, force/displacement RMS and mapped vector force balance at every completed coupling step."""
    return verification.coupling(
        Path(csv_file).resolve(), end_time_s, rms_limit, force_rtol, force_atol
    )


TOOLS = (
    update_knowledge_base,
    search_knowledge,
    search_commands,
    search_examples,
    search_errors,
    get_document,
    inspect_model,
    edit_model,
    inspect_geometry,
    inspect_mesh,
    get_boundary_conditions,
    audit_model,
    compare_model,
    snapshot_model,
    restore_model,
    start_workflow,
    get_workflow,
    resume_workflow,
    stop_workflow,
    verify_physics,
    verify_refinement,
    verify_coupling,
)
