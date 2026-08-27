# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Download, verify, install, and validate the standalone Agent Report CLI wheel on Windows.

[CmdletBinding()]
param(
    [Parameter()]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,

    [Parameter()]
    [string]$DownloadDirectory = (Join-Path $env:USERPROFILE 'Downloads')
)

$ErrorActionPreference = 'Stop'
$repository = 'martinbechard/agent-runner'
$tagPrefix = 'agent-report-cli-v'
$headers = @{ 'User-Agent' = 'agent-report-cli-installer' }

function Get-PythonCommand {
    foreach ($candidate in @('py', 'python')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            & $command.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
            if ($LASTEXITCODE -eq 0) {
                return $command.Source
            }
        }
    }
    throw 'Python 3.11 or newer is required. Install it from https://www.python.org/downloads/windows/ and run this script again.'
}

$python = Get-PythonCommand
$releasesUri = "https://api.github.com/repos/$repository/releases?per_page=100"
Write-Host 'Finding the Agent Report CLI release...'
$releases = @(Invoke-RestMethod -Uri $releasesUri -Headers $headers)

if ($Version) {
    $tagName = "$tagPrefix$Version"
    $release = $releases | Where-Object { $_.tag_name -eq $tagName } | Select-Object -First 1
} else {
    $release = $releases |
        Where-Object { -not $_.draft -and -not $_.prerelease -and $_.tag_name -like "$tagPrefix*" } |
        Select-Object -First 1
}

if ($null -eq $release) {
    $requested = if ($Version) { "version $Version" } else { 'a published release' }
    throw "Could not find $requested for Agent Report CLI."
}

$wheelAsset = $release.assets |
    Where-Object { $_.name -match '^agent_report_cli-.*-py3-none-win_amd64\.whl$' } |
    Select-Object -First 1
$checksumAsset = $release.assets |
    Where-Object { $_.name -eq 'SHA256SUMS' } |
    Select-Object -First 1

if ($null -eq $wheelAsset -or $null -eq $checksumAsset) {
    throw "Release $($release.tag_name) does not contain the Windows wheel and SHA256SUMS."
}

New-Item -ItemType Directory -Path $DownloadDirectory -Force | Out-Null
$wheelPath = Join-Path $DownloadDirectory $wheelAsset.name
$checksumPath = Join-Path $DownloadDirectory 'agent-report-SHA256SUMS'

Write-Host "Downloading $($wheelAsset.name)..."
Invoke-WebRequest -Uri $wheelAsset.browser_download_url -Headers $headers -OutFile $wheelPath
Invoke-WebRequest -Uri $checksumAsset.browser_download_url -Headers $headers -OutFile $checksumPath

$checksumLine = Get-Content $checksumPath |
    Where-Object { $_ -match [regex]::Escape($wheelAsset.name) } |
    Select-Object -First 1
if (-not $checksumLine) {
    throw "SHA256SUMS does not contain $($wheelAsset.name)."
}

$expectedHash = ($checksumLine.Trim() -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Path $wheelPath -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actualHash -ne $expectedHash) {
    throw "Checksum verification failed for $wheelPath."
}

Write-Host 'Checksum verified. Installing Agent Report CLI...'
& $python -m pip install --upgrade $wheelPath
if ($LASTEXITCODE -ne 0) {
    throw 'pip could not install Agent Report CLI.'
}

Write-Host 'Checking the installed command...'
& $python -m agent_report_cli.cli --help | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Agent Report CLI was installed, but its command check failed.'
}

Write-Host "Agent Report CLI $($release.tag_name.Substring($tagPrefix.Length)) is installed."
Write-Host "Wheel saved to $wheelPath"
Write-Host 'Run: agent-report --token-summary'
