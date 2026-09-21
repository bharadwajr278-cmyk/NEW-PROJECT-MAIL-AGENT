$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

if (-not (Test-Path -LiteralPath '.venv')) {
    python -m venv .venv
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt

if (-not (Test-Path -LiteralPath '.env')) {
    throw 'Create .env from .env.example and set ADMIN_PASSWORD first.'
}

Get-Content -LiteralPath '.env' | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#')) {
        $name, $value = $line -split '=', 2
        [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), 'Process')
    }
}

if (-not $env:ADMIN_PASSWORD -or $env:ADMIN_PASSWORD -eq 'replace-with-a-long-random-password') {
    throw 'Set a strong ADMIN_PASSWORD in .env before starting the dashboard.'
}

& '.\.venv\Scripts\waitress-serve.exe' --host=127.0.0.1 --port=$env:ADMIN_PORT admin:app
