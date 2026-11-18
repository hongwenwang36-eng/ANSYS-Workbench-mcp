solid = AddParticipant(InputFile="mapdl.scp")
fluid = AddParticipant(InputFile="fluent.scp")
interface = AddInterface(SideOneParticipant=solid, SideOneRegions=["FSIN_1"],
                         SideTwoParticipant=fluid, SideTwoRegions=["wall_deforming"])
AddDataTransfer(Interface=interface, TargetSide="One",
                SideOneVariable="FORC", SideTwoVariable="force")
AddDataTransfer(Interface=interface, TargetSide="Two",
                SideOneVariable="INCD", SideTwoVariable="displacement")
setup = DatamodelRoot()
setup.SolutionControl.TimeStepSize = "0.1 [s]"
setup.SolutionControl.EndTime = "1.0 [s]"
setup.SolutionControl.MaximumIterations = 20
setup.OutputControl.GenerateCSVChartOutput = True
Solve()
