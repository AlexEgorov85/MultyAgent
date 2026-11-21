<#
.SYNOPSIS
Включает, выключает и показывает пароль на веб-интерфейсе.

.DESCRIPTION
Пишет ui/.share-auth.json, который ui/proxy.ts читает на каждом запросе.
Изменения применяются сразу, перезапускать UI не нужно.

Ключи:
  -Off      выключить пароль (ссылка открыта всем, у кого она есть);
  -On       включить пароль (логин/пароль берутся из ui/.env.local или из файла);
  -Status   показать текущее состояние (по умолчанию);
  -User     логин для файла (иначе из ui/.env.local);
  -Password пароль для файла (иначе из ui/.env.local).

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\share_auth.ps1 -Off

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\share_auth.ps1 -On

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\share_auth.ps1 -Status
#>
[CmdletBinding()]
param(
    [switch]$On,
    [switch]$Off,
    [switch]$Status,
    [string]$User,
    [string]$Password
)

$ErrorActionPreference = "Stop"

if ($On -and $Off) {
    throw "Укажите что-то одно: -On или -Off."
}

$root = Split-Path -Parent $PSScriptRoot
$uiDir = Join-Path $root "ui"
$authFile = Join-Path $uiDir ".share-auth.json"

function Read-EnvLocal([string]$key) {
    $envFile = Join-Path $uiDir ".env.local"
    if (-not (Test-Path $envFile)) { return "" }
    foreach ($line in Get-Content $envFile) {
        if ($line -match "^\s*$([regex]::Escape($key))\s*=\s*(.*)$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return ""
}

function Read-AuthFile {
    if (-not (Test-Path $authFile)) { return $null }
    try {
        return Get-Content $authFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-Warning "Не удалось прочитать $authFile, считаю файл отсутствующим."
        return $null
    }
}

function Write-AuthFile($state) {
    # Без BOM: JSON.parse в Node не принимает BOM в начале файла.
    $json = $state | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($authFile, $json, (New-Object System.Text.UTF8Encoding($false)))
}

$current = Read-AuthFile
$envPassword = Read-EnvLocal "SHARE_BASIC_AUTH_PASSWORD"
$envUser = Read-EnvLocal "SHARE_BASIC_AUTH_USER"
if (-not $envUser) { $envUser = "demo" }

function Show-State {
    $fileState = Read-AuthFile
    $password = if ($fileState -and $fileState.PSObject.Properties.Name -contains "password") {
        $fileState.password
    } else { $envPassword }
    $user = if ($fileState -and $fileState.PSObject.Properties.Name -contains "user") {
        $fileState.user
    } else { $envUser }

    if ($fileState -and $fileState.PSObject.Properties.Name -contains "enabled") {
        $effective = [bool]$fileState.enabled
        $source = "ui/.share-auth.json"
    } else {
        $effective = [string]$envPassword -ne ""
        $source = "ui/.env.local"
    }

    Write-Host ("Пароль: " + $(if ($effective) { "включён" } else { "выключен" })) -ForegroundColor $(if ($effective) { "Yellow" } else { "Green" })
    Write-Host "Источник: $source"
    if ($effective) {
        Write-Host "Логин: $user"
        if ([string]$password -eq "") {
            Write-Host "Пароль пуст — запросы будут получать 503, пока не задан SHARE_BASIC_AUTH_PASSWORD." -ForegroundColor Red
        }
    }
}

if (-not $On -and -not $Off) {
    Show-State
    return
}

$state = [ordered]@{ enabled = [bool]$On }
if ($current) {
    foreach ($name in @("user", "password")) {
        if ($current.PSObject.Properties.Name -contains $name) {
            $state[$name] = $current.$name
        }
    }
}
if ($User) { $state["user"] = $User }
if ($Password) { $state["password"] = $Password }

Write-AuthFile $state

$effectivePassword = if ($state.Contains("password")) { $state["password"] } else { $envPassword }
$effectiveUser = if ($state.Contains("user")) { $state["user"] } else { $envUser }

if ($On) {
    Write-Host "Пароль включён (логин: $effectiveUser). Изменение уже действует." -ForegroundColor Yellow
    if ([string]$effectivePassword -eq "") {
        Write-Host "Внимание: пароль не задан. Укажите -Password или SHARE_BASIC_AUTH_PASSWORD в ui/.env.local." -ForegroundColor Red
    }
} else {
    Write-Host "Пароль выключен. Ссылку может открыть любой, у кого она есть." -ForegroundColor Green
    Write-Host "Включить обратно: scripts\share_auth.ps1 -On" -ForegroundColor DarkGray
}
