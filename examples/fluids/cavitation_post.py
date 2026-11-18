solver.settings.file.read_case_data(file_name="cav.cas.h5")
graphics = solver.settings.results.graphics
graphics.contour["vapor"] = {"field": "vapor-vof", "filled": True}
graphics.contour["vapor"].display()
solver.settings.results.graphics.views.auto_scale()
graphics.picture.use_window_resolution = False
graphics.picture.x_resolution = 1200
graphics.picture.y_resolution = 900
graphics.picture.save_picture(file_name="vapor.png")
solver.exit()
