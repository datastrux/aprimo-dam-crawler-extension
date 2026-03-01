param(
  [Parameter(Mandatory = $true)]
  [string]$ExtensionId,
  [string]$PythonExe = "",
  [string]$HostScript = ""
)

$ErrorActionPreference = "Stop"

if (-not $PythonExe) {
  $PythonExe = (Get-Command python).Source
}
if (-not $HostScript) {
  $HostScript = Join-Path $PSScriptRoot "native_host.py"
}

if (-not (Test-Path $PythonExe)) {
  throw "Python executable not found: $PythonExe"
}
if (-not (Test-Path $HostScript)) {
  throw "Host script not found: $HostScript"
}

$templatePath = Join-Path $PSScriptRoot "native_host_manifest.template.json"
if (-not (Test-Path $templatePath)) {
  throw "Template manifest not found: $templatePath"
}

$hostDir = Join-Path $env:LOCALAPPDATA "AprimoDamAuditNativeHost"
New-Item -ItemType Directory -Force -Path $hostDir | Out-Null

$launcherPath = Join-Path $hostDir "run_dam_audit_host.cmd"
$launcher = "@echo off`r`n`"$PythonExe`" `"$HostScript`"`r`n"
Set-Content -Path $launcherPath -Value $launcher -Encoding Ascii

$manifestPath = Join-Path $hostDir "com.datastrux.dam_audit_host.json"
$template = Get-Content -Raw -Path $templatePath
$template = $template.Replace("__HOST_LAUNCHER__", ($launcherPath -replace '\\', '\\\\'))
$template = $template.Replace("__EXTENSION_ID__", $ExtensionId)
Set-Content -Path $manifestPath -Value $template -Encoding UTF8

$regPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.datastrux.dam_audit_host"
if (-not (Test-Path $regPath)) {
  New-Item -Path $regPath -Force | Out-Null
}
Set-ItemProperty -Path $regPath -Name "(default)" -Value $manifestPath

Write-Host "Native host registered."
Write-Host "Manifest: $manifestPath"
Write-Host "Launcher: $launcherPath"
Write-Host "Registry: $regPath"
Write-Host "Extension ID: $ExtensionId"
