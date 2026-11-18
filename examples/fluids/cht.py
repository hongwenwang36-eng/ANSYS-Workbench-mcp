solver.settings.file.read_mesh(file_name="cht.msh")
solver.settings.mesh.check()
solver.settings.setup.models.viscous.model = "laminar"
solver.settings.setup.models.energy.enabled = True
solver.settings.setup.boundary_conditions.velocity_inlet["inlet"].momentum.velocity.value = 0.1
solver.settings.setup.boundary_conditions.velocity_inlet["inlet"].thermal.temperature.value = 300
solver.settings.setup.boundary_conditions.wall["heated"].thermal.thermal_condition = "Temperature"
solver.settings.setup.boundary_conditions.wall["heated"].thermal.temperature.value = 350
solver.settings.solution.initialization.hybrid_initialize()
solver.settings.solution.run_calculation.iterate(iter_count=500)
solver.settings.file.write_case_data(file_name="cht.cas.h5")
solver.tui.report.surface_integrals.area_weighted_avg("outlet", "()", "temperature", "no")
solver.exit()
