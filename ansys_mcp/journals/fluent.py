# Executed by Fluent's journal interpreter.
import json
cfg = __CONFIG__
settings = solver.settings
settings.file.read_case(file_name=cfg["file"])
bc = settings.setup.boundary_conditions
edit = cfg["edit"]
if edit:
    name = edit["target"]
    if edit["field"] == "inlet_velocity":
        bc.velocity_inlet[name].momentum.velocity.value = edit["value"]
    elif edit["field"] == "outlet_pressure":
        bc.pressure_outlet[name].momentum.gauge_pressure.value = edit["value"]
    elif edit["field"] == "fluid_material":
        settings.setup.cell_zone_conditions.fluid[name].general.material = edit["value"]
    elif edit["field"] == "viscous_model":
        settings.setup.models.viscous.model = edit["value"]
    elif edit["field"] == "time_step":
        settings.solution.run_calculation.transient_controls.time_step_size = edit["value"]
    settings.file.write_case(file_name=cfg["edited_case"])
state = {"kind":"fluent", "materials":settings.setup.materials.get_state(),
         "zones":settings.setup.cell_zone_conditions.get_state(),
         "boundaries":bc.get_state(), "viscous":settings.setup.models.viscous.model(),
         "time_controls":settings.solution.run_calculation.get_state()}
with open(cfg["output"],"w") as f:
    json.dump(state,f)
solver.exit()
