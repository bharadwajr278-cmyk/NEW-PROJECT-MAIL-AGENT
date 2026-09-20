$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

if (-not (Test-Path -LiteralPath '.venv')) {
    python -m venv .venv
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt

if (-not (Test-Path -LiteralPath '.env')) {
    throw 'Create .env from .env.example and add your SMTP credentials first.'
}

Get-Content -LiteralPath '.env' | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#')) {
        $name, $value = $line -split '=', 2
        [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), 'Process')
    }
}

& '.\.venv\Scripts\python.exe' -u monitor.py
