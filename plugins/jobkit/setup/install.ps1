# Set up the jobkit commands for the jobkit plugin (Windows).
#   install.ps1 --check     print one line: ok:<folder> | older:<folder> | newer:<folder> | missing | no-uv | unsupported
#   install.ps1             install the commands from this plugin with the uv already on the computer
#   install.ps1 --with-uv   the same, and first download uv if it is missing
# Run it only after the user has said yes: uv downloads Python and packages. --with-uv also downloads uv
# (from astral.sh); pass it only when the user asked for uv to be installed for them.
# It never replaces a uv that is already there and never installs over newer commands.
# Keep this file ASCII only: Windows PowerShell 5.1 misreads UTF-8 without a byte order mark.
$ErrorActionPreference = 'Stop'

# The uv release downloaded when uv is missing. Keep it equal to the one in setup/install.
$UvVersion = '0.13.7'

# Codex on Windows is not supported yet. Codex names its session in the environment of the commands it runs.
if ($env:CODEX_THREAD_ID -and -not $env:CLAUDECODE) {
    Write-Output 'unsupported'
    exit 2
}

$Root = Split-Path -Parent $PSScriptRoot

# The package version, the oldest uv accepted, and the Python version: all read from the plugin's own files.
$Project = Get-Content -Raw -Path (Join-Path $Root 'pyproject.toml')
$Wanted = [regex]::Match($Project, '(?m)^version *= *"([^"]*)"').Groups[1].Value
$UvMinimum = [regex]::Match($Project, '(?m)^required-version *= *">=([^"]*)"').Groups[1].Value
$PythonVersion = (Get-Content -Path (Join-Path $Root '.python-version') | Select-Object -First 1).Trim()
$Constraints = Join-Path (Join-Path $Root 'setup') 'constraints.txt'

function Fail($Message, $Code = 1) {
    [Console]::Error.WriteLine("failed: $Message")
    exit $Code
}

# -1, 0 or 1 for two dotted versions, compared number by number (0.10.0 is above 0.9.0).
function Compare-Version($Left, $Right) {
    $a = @("$Left".Split('.')); $b = @("$Right".Split('.'))
    for ($i = 0; $i -lt [Math]::Max($a.Count, $b.Count); $i++) {
        $x = 0; $y = 0
        if ($i -lt $a.Count -and $a[$i] -match '^\d+') { $x = [int]$Matches[0] }
        if ($i -lt $b.Count -and $b[$i] -match '^\d+') { $y = [int]$Matches[0] }
        if ($x -lt $y) { return -1 }
        if ($x -gt $y) { return 1 }
    }
    return 0
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
    if (-not $folder) { if (Find-Uv) { return 'missing' } else { return 'no-uv' } }
    $order = Compare-Version (Get-InstalledVersion $folder) $Wanted
    if ($order -eq 0) { return "ok:$folder" }
    if ($order -gt 0) { return "newer:$folder" }
    return "older:$folder"
}

if ($args.Count -gt 0 -and $args[0] -eq '--check') {
    Write-Output (Get-State)
    exit 0
}

$state = Get-State
if ($state -like 'ok:*' -or $state -like 'newer:*') { Write-Output $state; exit 0 }

$uv = Find-Uv
if ($uv) {
    $have = ''
    try { $line = (& $uv --version 2>$null | Select-Object -First 1) } catch { $line = '' }
    if ("$line" -match '^uv (\d[\d.]*)') { $have = $Matches[1] }
    if ((Compare-Version $have $UvMinimum) -lt 0) {
        Fail "uv is too old (found $have, need $UvMinimum or newer); it was left as it is" 3
    }
} elseif (-not ($args.Count -gt 0 -and $args[0] -eq '--with-uv')) {
    Fail 'uv is not installed' 4
} else {
    $scratch = Join-Path ([IO.Path]::GetTempPath()) ("jobkit-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $scratch | Out-Null
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $script = Join-Path $scratch 'uv-install.ps1'
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "https://astral.sh/uv/$UvVersion/install.ps1" -OutFile $script
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
& $uv tool install --force --python $PythonVersion --constraints $Constraints $Root *> $null
if ($LASTEXITCODE -ne 0) { Fail 'the jobkit commands could not be installed' }

$result = Get-State
if ($result -like 'ok:*') { Write-Output $result } else { Fail "the installed commands do not match the plugin ($result)" }
