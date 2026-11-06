# Set up the jobkit commands for the jobkit plugin (Windows).
#   install.ps1 --check   print one line: ok:<folder> | older:<folder> | missing
#   install.ps1           install uv if it is missing, then install the commands from this plugin
# Run it only after the user has said yes: it downloads software (uv, from astral.sh).
# Keep this file ASCII only: Windows PowerShell 5.1 misreads UTF-8 without a byte order mark.
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Wanted = (Get-Content -Raw -Path (Join-Path $Root '.claude-plugin\plugin.json') | ConvertFrom-Json).version

function Fail($Message) {
    [Console]::Error.WriteLine("failed: $Message")
    exit 1
}

function Find-Uv {
    $found = Get-Command uv -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    foreach ($candidate in @("$HOME\.local\bin\uv.exe", "$HOME\.cargo\bin\uv.exe")) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

# The folder that holds the jobkit commands, or nothing.
function Get-ToolFolder {
    $uv = Find-Uv
    if (-not $uv) { return $null }
    try { $folder = (& $uv tool dir --bin 2>$null | Select-Object -First 1) } catch { return $null }
    if ($LASTEXITCODE -ne 0 -or -not $folder) { return $null }
    if (Test-Path -LiteralPath (Join-Path $folder 'jobkit.exe')) { return $folder }
    return $null
}

function Get-InstalledVersion($Folder) {
    try { $line = (& (Join-Path $Folder 'jobkit.exe') --version 2>$null | Select-Object -First 1) } catch { return '' }
    return ($line -replace '^jobkit ', '')
}

function Get-State {
    $folder = Get-ToolFolder
    if (-not $folder) { return 'missing' }
    if ((Get-InstalledVersion $folder) -eq $Wanted) { return "ok:$folder" }
    return "older:$folder"
}

if ($args.Count -gt 0 -and $args[0] -eq '--check') {
    Write-Output (Get-State)
    exit 0
}

$state = Get-State
if ($state -like 'ok:*') { Write-Output $state; exit 0 }

if (-not (Find-Uv)) {
    $scratch = Join-Path ([IO.Path]::GetTempPath()) ("jobkit-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $scratch | Out-Null
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $script = Join-Path $scratch 'uv-install.ps1'
        try {
            Invoke-WebRequest -UseBasicParsing -Uri 'https://astral.sh/uv/install.ps1' -OutFile $script
        } catch {
            Fail 'uv could not be downloaded'
        }
        $env:UV_NO_MODIFY_PATH = '1'
        & powershell -NoProfile -ExecutionPolicy Bypass -File $script *> $null
        if ($LASTEXITCODE -ne 0) { Fail 'uv could not be installed' }
    } finally {
        Remove-Item -Recurse -Force -LiteralPath $scratch -ErrorAction SilentlyContinue
    }
}

$uv = Find-Uv
if (-not $uv) { Fail 'uv was not found after installing it' }
& $uv tool install --force $Root *> $null
if ($LASTEXITCODE -ne 0) { Fail 'the jobkit commands could not be installed' }

$result = Get-State
if ($result -like 'ok:*') { Write-Output $result } else { Fail "the installed commands do not match the plugin ($result)" }
