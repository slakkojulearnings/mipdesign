param(
  [Parameter(Mandatory=$true)][string]$SourcePath,
  [string]$Database = "data\mip.db",
  [string]$Output = "output"
)
$ErrorActionPreference = "Stop"
.\.venv\Scripts\Activate.ps1
mip analyze $SourcePath --db $Database --output $Output
mip validate --db $Database
