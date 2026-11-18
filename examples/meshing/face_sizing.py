"""Size the positive X end face of the single-body bar benchmark in Ansys Meshing."""
body = Model.Geometry.GetChildren(DataModelObjectCategory.Body, True)[0]
face = max(body.GetGeoBody().Faces, key=lambda item: item.Centroid[0])
selection = ExtAPI.SelectionManager.CreateSelectionInfo(SelectionTypeEnum.GeometryEntities)
selection.Ids = [face.Id]
sizing = Model.Mesh.AddSizing()
sizing.Location = selection
sizing.ElementSize = Quantity("2 [mm]")
