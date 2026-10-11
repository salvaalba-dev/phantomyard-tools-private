$ErrorActionPreference = 'Stop'
$pvDirectory = $PSScriptRoot
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m venv (Join-Path $pvDirectory '.venv')
} else {
    & py -3 -m venv (Join-Path $pvDirectory '.venv')
}
if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python.' }
& (Join-Path $pvDirectory '.venv/Scripts/python.exe') -m pip install -r (Join-Path $pvDirectory 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' }
Write-Output 'PhantomView instalado. Inicia: .\run.cmd serve --open'
