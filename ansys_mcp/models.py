"""Inspect native solver state and edit isolated copies using vendor journals."""

from pathlib import Path
import hashlib
import json
import shutil
import tempfile

JOURNALS = Path(__file__).parent / "journals"


def members(model):
    if not model.is_file():
        raise FileNotFoundError(model)
    if model.suffix.lower() == ".wbpj":
        companion = model.with_name(model.stem + "_files")
        if not companion.is_dir():
            raise ValueError("Missing Workbench project companion directory")
        return [model, companion]
    if model.name.lower().endswith((".cas.h5", ".cas.gz", ".cas")):
        return [model]
    raise ValueError("Expected .wbpj or a Fluent case")


def copy_model(model, dest):
    sources = members(model)
    for source in sources:
        if dest.resolve().is_relative_to(source.resolve()):
            raise ValueError("Destination is inside source project")
    dest.mkdir(parents=True, exist_ok=False)
    for source in sources:
        if source.is_dir():
            shutil.copytree(source, dest / source.name)
        else:
            shutil.copy2(source, dest / source.name)
    return dest / model.name


def manifest(root):
    values = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            with p.open("rb") as stream:
                digest = hashlib.sha256()
                for block in iter(lambda: stream.read(1048576), b""):
                    digest.update(block)
            values[p.relative_to(root).as_posix()] = digest.hexdigest()
    return values


def snapshot(model, dest):
    return publish_copy(model, dest, create_manifest=True)


def publish_copy(model, dest, create_manifest=False, expected=None):
    for member in members(model):
        if dest.resolve().is_relative_to(member.resolve()):
            raise ValueError("Destination is inside the source")
    if dest.exists():
        raise FileExistsError(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix=".model-copy-") as temp:
        staged = Path(temp) / "project"
        saved = copy_model(model, staged)
        files = manifest(staged)
        if expected is not None and files != expected:
            raise ValueError("Restored files do not match snapshot hashes")
        if create_manifest:
            original = {}
            for member in members(model):
                if member.is_dir():
                    original.update(
                        {member.name + "/" + k: v for k, v in manifest(member).items()}
                    )
                else:
                    with member.open("rb") as stream:
                        original[member.name] = hashlib.file_digest(
                            stream, "sha256"
                        ).hexdigest()
            if files != original:
                raise ValueError("Source changed during snapshot")
            (staged / "snapshot.json").write_text(
                json.dumps({"model": saved.name, "files": files}, indent=2),
                encoding="utf-8",
            )
        staged.rename(dest)
    if create_manifest:
        return {"snapshot": str(dest), "files": len(files)}
    return {"project": str(dest / model.name)}


def restore(src, dest):
    record = json.loads((src / "snapshot.json").read_text(encoding="utf-8"))
    name = record["model"]
    if Path(name).name != name:
        raise ValueError("Invalid snapshot model")
    current = manifest(src)
    current.pop("snapshot.json")
    if current != record["files"]:
        raise ValueError("Snapshot contents changed")
    return publish_copy(src / name, dest, expected=record["files"])


def run(model, system, edit, work, backend, dimension="3d"):
    work.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="model-", dir=work))
    project = copy_model(model, root / "project")
    output = root / "model.json"
    cfg = dict(
        file=project.as_posix(),
        edit=edit,
        system=system,
        output=output.as_posix(),
        detail=(root / "mechanical.json").as_posix(),
        edited_case=(root / "edited.cas.h5").as_posix(),
    )
    wb = project.suffix.lower() == ".wbpj"
    if edit:
        allowed = (
            {
                "parameter",
                "mesh_size",
                "material",
                "magnitude",
                "geometry_file",
                "face_sizing",
                "boundary_scope",
                "add_temperature",
                "add_fixed_support",
                "end_time",
            }
            if wb
            else {
                "inlet_velocity",
                "outlet_pressure",
                "fluid_material",
                "viscous_model",
                "time_step",
            }
        )
        if edit["field"] not in allowed or (
            wb and edit["field"] != "parameter" and not system
        ):
            raise ValueError("Unsupported field or missing Mechanical system")
    if wb:
        cfg["mechanical"] = (
            (JOURNALS / "mechanical.py")
            .read_text(encoding="utf-8")
            .replace("__CONFIG__", ascii(cfg))
        )
    template = "inspect.wbjn" if wb else "fluent.py"
    script = root / template
    script.write_text(
        (JOURNALS / template)
        .read_text(encoding="utf-8")
        .replace("__CONFIG__", ascii(cfg)),
        encoding="utf-8",
    )
    if wb:
        result = backend.run_workbench_journal(
            str(script), str(root), expected_output=str(output)
        )
    else:
        result = backend.run_fluent_journal(
            str(script), str(root), dimension=dimension, timeout_seconds=180
        )
    run_result = json.loads(result)
    saved = project if wb or not edit else root / "edited.cas.h5"
    artifact_ready = saved.is_file() and saved.stat().st_size > 0
    if not run_result.get("ok") or not output.is_file() or not artifact_ready:
        return {
            "ok": False,
            "directory": str(root),
            "execution": run_result,
            "error": Path(str(output) + ".error").read_text(errors="replace")
            if Path(str(output) + ".error").is_file()
            else "Native solver did not produce both the model report and the saved model",
        }
    state = json.loads(output.read_text(encoding="utf-8"))
    return {
        "ok": True,
        "source": str(model),
        "project": str(saved),
        "report": str(output),
        "state": state,
    }


def audit(state):
    findings = []

    def check(name, passed, evidence):
        findings.append(
            {
                "check": name,
                "status": "pass" if passed else "fail",
                "evidence": evidence,
            }
        )

    if state.get("kind") == "workbench":
        check("systems", bool(state["systems"]), len(state["systems"]))
        if "mechanical" not in state:
            findings.append(
                {
                    "check": "Mechanical model settings",
                    "status": "unverified",
                    "evidence": "Select a Mechanical system name",
                }
            )
        else:
            model = state["mechanical"]
            bodies = [b for b in model["bodies"] if not b["suppressed"]]
            check("active bodies", bool(bodies), len(bodies))
            check(
                "material assignments",
                all(b["material"].strip() for b in bodies) and bool(bodies),
                [b["material"] for b in bodies],
            )
            check("mesh generated", model["elements"] > 0, model["elements"])
            check("analyses", bool(model["analyses"]), len(model["analyses"]))
            for b in bodies:
                check(
                    "geometry faces " + str(b["id"]),
                    bool(b.get("face_ids")),
                    b.get("face_ids", []),
                )
            for a in model["analyses"]:
                # Temperature constraints sharing a face must prescribe the same history.
                prescribed = {}
                for item in a["objects"]:
                    if item.get("suppressed") or item["type"] == "InitialCondition":
                        continue
                    if item["type"] == "Temperature" and item.get("magnitude"):
                        for face in item.get("scope_ids", []):
                            if face in prescribed:
                                check(
                                    "consistent temperature on face " + str(face),
                                    prescribed[face] == item["magnitude"],
                                    [prescribed[face], item["magnitude"]],
                                )
                            prescribed[face] = item["magnitude"]
                    if "scope_ids" in item:
                        check(
                            "scoped " + item["name"],
                            bool(item["scope_ids"]),
                            item["scope_ids"],
                        )
    elif state.get("kind") == "fluent":
        check(
            "fluid cell zones",
            bool(state["zones"].get("fluid")),
            list(state["zones"].get("fluid", {})),
        )
        for group in ("fluid", "solid"):
            for zone, settings in state["zones"].get(group, {}).items():
                assigned = settings.get("general", {}).get("material")
                check(
                    "assigned material " + zone,
                    assigned in state["materials"].get(group, {}),
                    assigned,
                )
        check(
            "boundary zones",
            any(state["boundaries"].values()),
            list(k for k, v in state["boundaries"].items() if v),
        )
        check(
            "materials",
            bool(state["materials"].get("fluid")),
            list(state["materials"].get("fluid", {})),
        )
    else:
        raise ValueError("Unknown model report")
    return {
        "passed": all(f["status"] == "pass" for f in findings),
        "checks": findings,
        "scope": "Only the listed checks were evaluated",
    }


def compare(left, right, path=""):
    if isinstance(left, dict) and isinstance(right, dict):
        changes = []
        for key in sorted(set(left) | set(right)):
            field = path + "/" + key
            if key not in left or key not in right:
                changes.append(
                    {"field": field, "before": left.get(key), "after": right.get(key)}
                )
            else:
                changes.extend(compare(left[key], right[key], field))
        return changes
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return [
            change
            for i, (a, b) in enumerate(zip(left, right))
            for change in compare(a, b, path + "/" + str(i))
        ]
    return [] if left == right else [{"field": path, "before": left, "after": right}]
