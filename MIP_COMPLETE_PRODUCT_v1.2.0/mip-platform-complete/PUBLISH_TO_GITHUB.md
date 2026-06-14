# Publish MIP v1 to GitHub

The target repository is public. Do not copy proprietary mainframe source, generated databases, output reports, internal logs, credentials, or organization-specific documentation into it.

## PowerShell

```powershell
git clone https://github.com/slakkojulearnings/mip-platform.git
cd mip-platform

# Copy the extracted release contents into this directory, replacing the placeholder README.

git status
git add .
git commit -m "Build complete MIP v1 platform"
git push origin main
```

## Verify after push

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python scripts\validate_skills.py
ruff check src tests
ruff format --check src tests
mypy src\mip
pytest --cov=mip --cov-fail-under=80
mip analyze examples\sample-mainframe --db data\demo.db --output output\demo
mip validate --db data\demo.db
```

## Recommended release

Create GitHub release `v1.0.0` only after Actions passes on `main`.
