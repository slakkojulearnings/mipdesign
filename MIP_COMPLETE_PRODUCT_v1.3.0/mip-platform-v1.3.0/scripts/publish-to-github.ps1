param(
  [string]$Remote = "https://github.com/slakkojulearnings/mip-platform.git",
  [string]$Branch = "main"
)
$ErrorActionPreference = "Stop"

if (-not (Test-Path .git)) {
  git init
  git remote add origin $Remote
}

git checkout -B $Branch
python scripts\validate_skills.py
ruff check src tests
ruff format --check src tests
mypy src\mip
pytest --cov=mip --cov-fail-under=80
git add .
git commit -m "Build complete MIP v1 platform"
git push -u origin $Branch
