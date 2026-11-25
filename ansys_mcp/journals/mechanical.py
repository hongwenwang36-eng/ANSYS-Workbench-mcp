# Executed inside Ansys Mechanical via the Workbench Model container.
import json
cfg = __CONFIG__
try:
    edit = cfg["edit"]
    bodies = list(Model.Geometry.GetChildren(DataModelObjectCategory.Body, True))
    if edit and edit["field"] == "mesh_size":
        Model.Mesh.ElementSize = Quantity(edit["value"])
        Model.Mesh.GenerateMesh()
    if edit and edit["field"] == "material":
        matches = [b for b in bodies if str(b.ObjectId) == edit["target"]]
        if len(matches) != 1:
            raise ValueError("Select one body by ObjectId")
        matches[0].Material = edit["value"]
    if edit and edit["field"] in ("face_sizing","boundary_scope","add_temperature","add_fixed_support"):
        selection = ExtAPI.SelectionManager.CreateSelectionInfo(SelectionTypeEnum.GeometryEntities)
        selection.Ids = edit["faces"]
        if edit["field"] == "face_sizing":
            size = Model.Mesh.AddSizing()
            size.Location = selection
            size.ElementSize = Quantity(edit["value"])
            Model.Mesh.GenerateMesh()
        elif edit["field"] == "boundary_scope":
            ExtAPI.DataModel.GetObjectById(int(edit["target"])).Location = selection
        else:
            analysis = ExtAPI.DataModel.GetObjectById(int(edit["target"]))
            if edit["field"] == "add_temperature":
                load = analysis.AddTemperature()
                load.Magnitude.Output.SetDiscreteValue(0,Quantity(edit["value"]))
            else:
                load = analysis.AddFixedSupport()
            load.Location = selection
    if edit and edit["field"] == "end_time":
        analysis = ExtAPI.DataModel.GetObjectById(int(edit["target"]))
        analysis.AnalysisSettings.StepEndTime = Quantity(edit["value"])
    if edit and edit["field"] == "magnitude":
        obj = ExtAPI.DataModel.GetObjectById(int(edit["target"]))
        obj.Magnitude.Output.SetDiscreteValue(0, Quantity(edit["value"]))
    state = {"bodies":[], "analyses":[], "mesh_size":unicode(Model.Mesh.ElementSize)}
    for b in bodies:
        state["bodies"].append({"id":b.ObjectId, "name":b.Name, "material":unicode(b.Material),
                                "face_ids":[int(face.Id) for face in b.GetGeoBody().Faces], "suppressed":bool(b.Suppressed)})
    mesh = ExtAPI.DataModel.MeshDataByName("Global")
    state["nodes"] = len(list(mesh.NodeIds)) if mesh else 0
    state["elements"] = len(list(mesh.ElementIds)) if mesh else 0
    for a in Model.Analyses:
        items = []
        for obj in a.Children:
            item = {"id":obj.ObjectId, "name":obj.Name, "type":str(obj.DataModelObjectCategory)}
            if hasattr(obj,"Suppressed"):
                item["suppressed"] = bool(obj.Suppressed)
            if hasattr(obj,"Location") and hasattr(obj.Location,"Ids"):
                item["scope_ids"] = list(obj.Location.Ids)
            if hasattr(obj,"Magnitude") and hasattr(obj.Magnitude,"Output"):
                item["magnitude"] = [unicode(v) for v in obj.Magnitude.Output.DiscreteValues]
            items.append(item)
        state["analyses"].append({"id":a.ObjectId,"name":a.Name, "objects":items})
    with open(cfg["detail"], "w") as f:
        json.dump(state,f)

except:
    import traceback
    with open(cfg["detail"],"w") as f:
        json.dump({"error":traceback.format_exc()},f)
