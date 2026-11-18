# Run inside Mechanical using the Workbench Model container.
import os
import traceback

with open(os.path.join(root, "mechanical.log"), "w") as log:
    try:
        ExtAPI.Application.ActiveUnitSystem = MechanicalUnitSystem.StandardMKS
        analysis = Model.Analyses[0]
        bodies = Model.Geometry.GetChildren(DataModelObjectCategory.Body, True)
        faces = list(bodies[0].GetGeoBody().Faces)
        ordered = sorted(faces, key=lambda face: face.Centroid[0])
        for name, face, value in [("Cold", ordered[0], 20), ("Hot", ordered[-1], 100)]:
            selection = ExtAPI.SelectionManager.CreateSelectionInfo(SelectionTypeEnum.GeometryEntities)
            selection.Ids = [face.Id]
            load = analysis.AddTemperature()
            load.Name = name
            load.Location = selection
            load.Magnitude.Output.SetDiscreteValue(0, Quantity(str(value) + " [C]"))
        Model.Mesh.ElementSize = Quantity("4 [mm]")
        Model.Mesh.GenerateMesh()
        temperature = analysis.Solution.AddTemperature()
        flux = analysis.Solution.AddTotalHeatFlux()
        analysis.Solve(True)
        analysis.Solution.EvaluateAllResults()
        image_settings = Ansys.Mechanical.Graphics.GraphicsImageExportSettings()
        image_settings.Width = 1600
        image_settings.Height = 1000
        image_settings.CurrentGraphicsDisplay = False
        image_settings.Background = GraphicsBackgroundType.White
        for result, filename in [(temperature, "temperature"), (flux, "heat_flux")]:
            result.Activate()
            ExtAPI.Graphics.ViewOptions.ResultPreference.ShowMinimum = False
            ExtAPI.Graphics.ViewOptions.ResultPreference.ShowMaximum = False
            ExtAPI.Graphics.Camera.SetFit()
            ExtAPI.Graphics.ExportImage(os.path.join(root, filename + ".png"), GraphicsImageExportFormat.PNG, image_settings)
            data = result.PlotData
            nodes = list(data["Node"])
            values = list(data["Values"])
            assert len(nodes) == len(values) and len(nodes) > 0
            mesh = ExtAPI.DataModel.MeshDataByName("Global")
            xs = [mesh.NodeById(node).X for node in nodes]
            x_min, x_max = min(xs), max(xs)
            unit = result.Minimum.Unit
            with open(os.path.join(root, filename + ".csv"), "w") as output:
                output.write("node,x_fraction,value,unit\n")
                max_error = 0.0
                for node, x, value in zip(nodes, xs, values):
                    fraction = (x - x_min) / (x_max - x_min)
                    output.write("%s,%.12g,%.12g,%s\n" % (node, fraction, value, unit))
                    if filename == "temperature":
                        max_error = max(max_error, abs(value - (20 + 80 * fraction)))
                if filename == "temperature":
                    log.write("Max nodal deviation from linear solution (degC): %s\n" % max_error)
                    assert max_error < 1e-4
        cold = temperature.Minimum.Value
        hot = temperature.Maximum.Value
        log.write("Temperature units: %s\n" % temperature.Minimum.Unit)
        assert abs(cold - 20) < 1e-4 and abs(hot - 100) < 1e-4
        log.write("Min/max temperature (degC): %s, %s\n" % (cold, hot))
        log.write("MECHANICAL_CHECK_PASSED\n")
    except:
        log.write(traceback.format_exc())
        raise
