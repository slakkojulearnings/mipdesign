$ErrorActionPreference = "Stop"
.\.venv\Scripts\Activate.ps1
Remove-Item data\demo.db -ErrorAction SilentlyContinue
mip analyze examples\sample-mainframe --db data\demo.db --output output\demo
mip stats --db data\demo.db
mip validate --db data\demo.db
mip graph-export --db data\demo.db --output output\demo\graph
