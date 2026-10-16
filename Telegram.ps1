param([switch]$Stop, [switch]$Restart)

$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv-win/Scripts/python.exe'
Push-Location $projectPath
try {
    if ($Stop -or $Restart) {
        & $pythonPath -m src.commands.run_dev_bot --stop
        if ($LASTEXITCODE -ne 0) { throw 'Could not request development shutdown.' }
        $shutdownDeadline = [DateTime]::UtcNow.AddSeconds(20)
        while (Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue) {
            if ([DateTime]::UtcNow -ge $shutdownDeadline) { throw 'Port 8002 is still occupied; inspect the current process.' }
            Start-Sleep -Milliseconds 250
        }
        if ($Stop) { Write-Output 'Development bot stopped.'; return }
    }
    if (Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue) {
        throw 'Port 8002 is already occupied. Use .\Telegram.ps1 -Restart for this development bot.'
    }
    $check = (& $pythonPath -m src.commands.run_dev_bot --check) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $check.status -ne 'development_ready') {
        throw "Development check failed: $($check.status). Free RAM: $($check.free_mib) MiB; required: $($check.required_mib) MiB."
    }
    $stateDirectory = Join-Path $projectPath 'data/pc-app'
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff')
    $stdoutPath = Join-Path $stateDirectory "development.$stamp.stdout.log"
    $stderrPath = Join-Path $stateDirectory "development.$stamp.stderr.log"
    $process = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'src.commands.run_dev_bot', '--execute') `
        -WorkingDirectory $projectPath -WindowStyle Hidden -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath -PassThru
    @{ pid = $process.Id; startedAtUtc = [DateTime]::UtcNow.ToString('o'); mode = 'development';
       module = 'src.commands.run_dev_bot'; stdout = $stdoutPath; stderr = $stderrPath } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stateDirectory 'development-process.json') -Encoding utf8
    $startupDeadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $startupDeadline) {
        if ($process.HasExited) { throw "Development bot exited. Inspect $stderrPath and $stdoutPath locally." }
        if ((Test-Path -LiteralPath $stdoutPath) -and
            (Select-String -LiteralPath $stdoutPath -Pattern '"status": "polling_private_bot"' -Quiet)) {
            Write-Output 'Private development bot is running: https://t.me/AIScholarLensbot'
            Write-Output 'After editing the agent: .\Telegram.ps1 -Restart'
            Write-Output 'To stop: .\Telegram.ps1 -Stop'
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Startup is still pending. Inspect $stdoutPath and $stderrPath locally before starting another instance."
}
finally {
    Pop-Location
}
