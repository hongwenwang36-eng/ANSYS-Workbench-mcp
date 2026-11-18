# Copyright (C) 2021 - 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
#
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Adapted for the Fluent 2025 R1 embedded Python console.
solver.settings.file.read_mesh(file_name="cav.msh.gz")

solver.settings.mesh.check()

solver.settings.setup.general.solver.two_dim_space = "axisymmetric"

solver.settings.setup.models.multiphase.models = "mixture"

solver.tui.define.models.multiphase.mixture_parameters("no", "implicit")

solver.settings.setup.models.viscous = {
    "model": "k-omega",
    "k_omega_model": "sst",
}

solver.settings.setup.materials.fluid["water"] = {
    "density": {
        "option": "constant",
        "value": 1000,
    },
    "viscosity": {
        "option": "constant",
        "value": 0.001,
    },
}

solver.settings.setup.materials.database.copy_by_name(
    type="fluid", name="water-vapor"
)

solver.settings.setup.materials.fluid["water-vapor"] = {
    "density": {"value": 0.02558},
    "viscosity": {"value": 1.26e-06},
}

solver.tui.define.phases.set_domain_properties.change_phases_names(
    "vapor", "liquid"
)

solver.tui.define.phases.set_domain_properties.phase_domains.liquid.material(
    "yes", "water"
)

solver.tui.define.phases.set_domain_properties.phase_domains.vapor.material(
    "yes", "water-vapor"
)

solver.tui.define.phases.set_domain_properties.interaction_domain.heat_mass_reactions.mass_transfer(
    1, "liquid", "vapor", "cavitation", "1", "no", "no", "no"
)

inlet_1 = solver.settings.setup.boundary_conditions.pressure_inlet[
    "inlet_1"
].phase

inlet_1["mixture"] = {
    "momentum": {
        "gauge_total_pressure": {"value": 500000},
        "supersonic_or_initial_gauge_pressure": {"value": 449000},
        "direction_specification_method": "Normal to Boundary",
    },
    "turbulence": {
        "turbulent_specification": "Intensity and Viscosity Ratio",
        "turbulent_intensity": 0.05,
        "turbulent_viscosity_ratio": 10,
    },
}

inlet_1["vapor"] = {
    "multiphase": {
        "volume_fraction": {"value": 0},
    },
}

solver.settings.setup.boundary_conditions.copy(from_="inlet_1", to="inlet_2")

outlet = solver.settings.setup.boundary_conditions.pressure_outlet[
    "outlet"
].phase

outlet["mixture"] = {
    "momentum": {
        "gauge_pressure": {"value": 95000},
    },
    "turbulence": {
        "turbulent_specification": "Intensity and Viscosity Ratio",
        "turbulent_intensity": 0.04,
        "turbulent_viscosity_ratio": 10,
    },
}

outlet["vapor"] = {
    "multiphase": {
        "volume_fraction": {"value": 0},
    },
}

solver.settings.setup.general.operating_conditions.operating_pressure = 0

methods = solver.settings.solution.methods

methods.discretization_scheme = {
    "k": "first-order-upwind",
    "mom": "quick",
    "mp": "quick",
    "omega": "first-order-upwind",
    "pressure": "presto!",
}

methods.p_v_coupling.flow_scheme = "Coupled"

methods.pseudo_time_method.formulation.coupled_solver = "global-time-step"

methods.high_order_term_relaxation.enable = True

solver.settings.solution.controls.pseudo_time_explicit_relaxation_factor.global_dt_pseudo_relax[
    "mp"
] = 0.3

resid_eqns = solver.settings.solution.monitor.residual.equations

resid_eqns["continuity"].absolute_criteria = 1e-5
resid_eqns["x-velocity"].absolute_criteria = 1e-5
resid_eqns["y-velocity"].absolute_criteria = 1e-5
resid_eqns["k"].absolute_criteria = 1e-5
resid_eqns["omega"].absolute_criteria = 1e-5
resid_eqns["vf-vapor"].absolute_criteria = 1e-5

initialization = solver.settings.solution.initialization

initialization.initialization_type = "hybrid"
initialization.hybrid_init_options.general_settings.initial_pressure = True
initialization.hybrid_initialize()



solver.settings.solution.run_calculation.iterate(iter_count=500)

solver.settings.file.write_case_data(file_name="cav.cas.h5")


solver.exit()
