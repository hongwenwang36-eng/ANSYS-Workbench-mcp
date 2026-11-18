import json
solver.settings.file.read_case_data(file_name="duct.cas.h5")
r=solver.settings.solution.report_definitions
r.surface["outlet_velocity"]={"report_type":"surface-areaavg","field":"x-velocity","surface_names":["outlet"]}
with open("metrics.json","w") as f:
    json.dump(r.compute(report_defs=["outlet_velocity"]),f,indent=2)
g=solver.settings.results.graphics
g.contour["velocity"]={"field":"velocity-magnitude","filled":True}
g.contour["velocity"].display()
solver.settings.results.graphics.views.auto_scale()
g.picture.use_window_resolution=False
g.picture.x_resolution=1200
g.picture.y_resolution=900
g.picture.save_picture(file_name="velocity.png")
solver.exit()
