import json
solver.settings.file.read_case_data(file_name="cht.cas.h5")
reports = solver.settings.solution.report_definitions
reports.flux["interface_heat"] = {"report_type":"flux-heattransfer", "boundaries":["interface"]}
reports.flux["shadow_heat"] = {"report_type":"flux-heattransfer", "boundaries":["interface-shadow"]}
reports.surface["outlet_temperature"] = {"report_type":"surface-areaavg","field":"temperature","surface_names":["outlet"]}
data = reports.compute(report_defs=["interface_heat","shadow_heat","outlet_temperature"])
with open("metrics.json","w") as f:
    json.dump(data, f, indent=2)
g = solver.settings.results.graphics
g.contour["temperature"]={"field":"temperature","filled":True}
g.contour["temperature"].display()
solver.settings.results.graphics.views.auto_scale()
g.picture.use_window_resolution = False
g.picture.x_resolution = 1200
g.picture.y_resolution = 900
g.picture.save_picture(file_name="temperature.png")
solver.exit()
