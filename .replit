modules = ["python-3.11"]
[agent]
expertMode = true

[nix]
channel = "stable-25_05"

[workflows]
runButton = "Project"

[[workflows.workflow]]
name = "Project"
mode = "parallel"
author = "cj"

[[workflows.workflow.tasks]]
task = "workflow.run"
args = "D-TOWN Bot"

[[workflows.workflow]]
name = "D-TOWN Bot"
author = "cj"

[[workflows.workflow.tasks]]
task = "shell.exec"
args = "python main.py"

[workflows.workflow.metadata]
outputType = "console"
