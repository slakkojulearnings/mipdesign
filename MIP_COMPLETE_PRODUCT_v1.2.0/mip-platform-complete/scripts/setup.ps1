$ErrorActionPreference = "Stop"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
python scripts/validate_skills.py
pytest -q
Write-Host "MIP setup completed. Open mip-platform.code-workspace in VS Code."
