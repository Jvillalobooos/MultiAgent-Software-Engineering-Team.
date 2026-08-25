[CmdletBinding()]
param()

$projectRoot = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$runScript = Join-Path $projectRoot "run.ps1"

if (-not (Test-Path -LiteralPath $runScript -PathType Leaf)) {
    Write-Error "run.ps1 was not found in the project root."
    exit 1
}

$localAppData = [Environment]::GetFolderPath("LocalApplicationData")
$binDirectory = Join-Path $localAppData "NovaTeam\bin"
$launcherPath = Join-Path $binDirectory "nova-team.cmd"
New-Item -ItemType Directory -Path $binDirectory -Force | Out-Null

$launcher = @(
    "@echo off"
    "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$runScript`" %*"
)
Set-Content -LiteralPath $launcherPath -Value $launcher -Encoding ASCII

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$entries = @(
    if ($userPath) {
        $userPath -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }
)
$normalizedBin = $binDirectory.TrimEnd("\", "/")
$alreadyPresent = $entries | Where-Object {
    $_.TrimEnd("\", "/") -ieq $normalizedBin
}

if (-not $alreadyPresent) {
    [Environment]::SetEnvironmentVariable("Path", ($entries + $binDirectory) -join ";", "User")
}

Write-Output "Nova Team launcher installed."
Write-Output ""
Write-Output "Open a new PowerShell window and run:"
Write-Output ""
Write-Output "nova-team"
