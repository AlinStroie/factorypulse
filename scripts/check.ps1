# Echivalentul lui `make check` pe Windows, unde `make` nu exista.
# Rulare: powershell -ExecutionPolicy Bypass -File scripts/check.ps1
$ErrorActionPreference = "Stop"
$bin = Join-Path $PSScriptRoot "..\.venv\Scripts"

& "$bin\ruff.exe" check .;          if ($LASTEXITCODE) { exit $LASTEXITCODE }
& "$bin\ruff.exe" format --check .; if ($LASTEXITCODE) { exit $LASTEXITCODE }
& "$bin\mypy.exe";                  if ($LASTEXITCODE) { exit $LASTEXITCODE }
& "$bin\pytest.exe" --cov --cov-report=term
exit $LASTEXITCODE
