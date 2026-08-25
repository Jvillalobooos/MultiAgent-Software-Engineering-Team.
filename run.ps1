[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$LauncherArguments
)

if ($LauncherArguments -contains "--help") {
    Write-Output "Autonomous Engineering Team"
    Write-Output ""
    Write-Output "Windows:"
    Write-Output "  .\run.ps1"
    Write-Output ""
    Write-Output "macOS:"
    Write-Output "  ./run.sh"
    Write-Output ""
    Write-Output "The script expects the project to be already configured."
    exit 0
}

$projectRoot = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Write-Error "Project is not prepared."
    Write-Error "Please complete the project setup first."
    exit 1
}

function Test-Ollama {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 300
    }
    catch {
        return $false
    }
}

if (-not (Test-Ollama)) {
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if ($null -eq $ollama) {
        Write-Error "Ollama is not available. Start Ollama and try again."
        exit 1
    }

    Start-Process -FilePath $ollama.Source -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
    if (-not (Test-Ollama)) {
        Write-Error "Ollama did not respond at http://localhost:11434."
        exit 1
    }
}

Write-Host "Autonomous Engineering Team"
Write-Host "----------------------------"
Write-Host ""

do {
    $requirement = Read-Host "Enter requirement"
    if ([string]::IsNullOrWhiteSpace($requirement)) {
        Write-Host "A requirement is required."
    }
} while ([string]::IsNullOrWhiteSpace($requirement))

Write-Host ""
Write-Host "Starting engineering team..."

Push-Location $projectRoot
try {
    & $python -m engineering_team.cli run $requirement
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $exitCode
