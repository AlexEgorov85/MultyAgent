<#
.SYNOPSIS
Поднимает LangGraph API, веб-интерфейс и публичный туннель cloudflared.

.DESCRIPTION
Запускает три процесса и печатает публичную ссылку вида
https://<случайное-имя>.trycloudflare.com. Ссылка живёт, пока открыт скрипт.
Ctrl+C останавливает всё.

В ui/.env.local должно быть NEXT_PUBLIC_LANGGRAPH_API_URL=/api: браузер
ходит в API через собственный прокси интерфейса, поэтому наружу нужен
только порт 3000.

.PARAMETER Dev
Запустить `next dev` вместо production-сборки (быстрее старт, но нужны
allowedDevOrigins и HMR; для показа лучше production).

.PARAMETER NoBuild
Не пересобирать UI (использовать готовый .next).

.PARAMETER TunnelName
Имя named-туннеля Cloudflare (создаётся `cloudflared tunnel create`).
Вместе с -Hostname включает режим постоянного адреса, на который можно
навесить Cloudflare Access. Требует config.yml (см. -ConfigPath).

.PARAMETER Serveo
Открыть SSH-туннель через serveo.net вместо Cloudflare. Нужен только ssh.
Полезно, если quick tunnel Cloudflare не регистрируется в вашей сети
(ошибки 1033/530, "connection with edge closed").

.PARAMETER NoAuth
Осознанно открыть демо без пароля: передаёт UI SHARE_AUTH_ENABLED=off и
печатает явное предупреждение. Без этого флага скрипт откажется поднимать
публичный туннель, если пароль не задан (ни SHARE_BASIC_AUTH_PASSWORD в
ui/.env.local, ни enabled=true в ui/.share-auth.json). Файл
ui/.share-auth.json по-прежнему приоритетнее: если в нём enabled=true,
пароль сохранится, а -NoAuth будет проигнорирован.

.PARAMETER Hostname
Публичный hostname named-туннеля, например demo.example.com.
Используется для проверки доступности и для сообщения пользователю.

.PARAMETER ConfigPath
Путь к config.yml cloudflared. По умолчанию %USERPROFILE%\.cloudflared\config.yml.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\share_ui.ps1

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\share_ui.ps1 -Dev

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\share_ui.ps1 -TunnelName audit-demo -Hostname demo.example.com
.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\share_ui.ps1 -Serveo
#>
[CmdletBinding()]
param(
    [switch]$Dev,
    [switch]$NoBuild,
    [switch]$Serveo,
    [switch]$NoAuth,
    [string]$TunnelName,
    [string]$Hostname,
    [string]$ConfigPath = (Join-Path $env:USERPROFILE ".cloudflared\config.yml")
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$UiPort = 3000
$ApiPort = 2024
$root = Split-Path -Parent $PSScriptRoot
$uiDir = Join-Path $root "ui"
$langgraphExe = Join-Path $root ".venv\Scripts\langgraph.exe"
$npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source

if (-not (Test-Path $langgraphExe)) {
    throw "Не найден $langgraphExe. Создайте .venv и установите requirements.txt."
}
if (-not $npmCmd) {
    throw "Не найден npm.cmd. Установите Node.js 20+."
}

if ($TunnelName -and -not $Hostname) {
    throw "С -TunnelName укажите -Hostname, например: -TunnelName audit-demo -Hostname demo.example.com"
}
if ($Hostname -and -not $TunnelName) {
    throw "С -Hostname укажите -TunnelName (имя named-туннеля Cloudflare)."
}
if ($TunnelName -and -not (Test-Path $ConfigPath)) {
    throw "Не найден конфиг cloudflared: $ConfigPath. Пример — docs/cloudflared.example.yml."
}

$cloudflaredCmd = $null
$sshCmd = $null
if ($Serveo) {
    $sshCmd = (Get-Command ssh -ErrorAction SilentlyContinue).Source
    if (-not $sshCmd) {
        throw "Не найден ssh. В Windows: Параметры → Приложения → Дополнительные компоненты → OpenSSH Client."
    }
} else {
    $cloudflaredCmd = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
    if (-not $cloudflaredCmd) {
        # winget ставит cloudflared в Program Files (x86), но текущий терминал
        # может не видеть обновлённый PATH.
        foreach ($candidate in @(
                (Join-Path ${env:ProgramFiles(x86)} "cloudflared\cloudflared.exe"),
                (Join-Path $env:ProgramFiles "cloudflared\cloudflared.exe"),
                (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\cloudflared.exe"))) {
            if (Test-Path $candidate) { $cloudflaredCmd = $candidate; break }
        }
    }
    if (-not $cloudflaredCmd) {
        throw "Не найден cloudflared. Установите: winget install --id Cloudflare.cloudflared  (или запустите с -Serveo)."
    }
}

$envLocal = Join-Path $uiDir ".env.local"
if (-not (Test-Path $envLocal)) {
    Copy-Item (Join-Path $uiDir ".env.local.example") $envLocal
    Write-Host "Создан ui\.env.local из .env.local.example."
}
$envText = Get-Content $envLocal -Raw
if ($envText -notmatch "(?m)^\s*NEXT_PUBLIC_LANGGRAPH_API_URL\s*=\s*/api\s*$") {
    Write-Warning "В ui\.env.local NEXT_PUBLIC_LANGGRAPH_API_URL должен быть /api, иначе браузер зрителя будет искать API на своём компьютере."
}
function Read-EnvLocalValue([string]$key) {
    if ($envText -match "(?m)^\s*$([regex]::Escape($key))\s*=\s*(.*)$") {
        return $Matches[1].Trim().Trim('"').Trim("'")
    }
    return ""
}

# Приоритет как в ui/proxy.ts: ui/.share-auth.json > SHARE_AUTH_ENABLED >
# SHARE_BASIC_AUTH_PASSWORD. Здесь считаем эффективное состояние, чтобы не
# поднять публичный туннель, который окажется открытым без пароля.
$authFilePath = Join-Path $uiDir ".share-auth.json"
$authFile = $null
if (Test-Path $authFilePath) {
    try {
        $authFile = Get-Content $authFilePath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-Warning "Не удалось прочитать $authFilePath, считаю, что файла нет."
        $authFile = $null
    }
}

$fileHasEnabled = $false
$fileEnabled = $false
$filePassword = ""
if ($authFile) {
    if ($authFile.PSObject.Properties.Name -contains "enabled" -and $authFile.enabled -is [bool]) {
        $fileHasEnabled = $true
        $fileEnabled = [bool]$authFile.enabled
    }
    if ($authFile.PSObject.Properties.Name -contains "password" -and $null -ne $authFile.password) {
        $filePassword = [string]$authFile.password
    }
}

$envPassword = Read-EnvLocalValue "SHARE_BASIC_AUTH_PASSWORD"
if (-not $envPassword) { $envPassword = [string]$env:SHARE_BASIC_AUTH_PASSWORD }

$envSwitch = Read-EnvLocalValue "SHARE_AUTH_ENABLED"
if ($env:SHARE_AUTH_ENABLED) { $envSwitch = [string]$env:SHARE_AUTH_ENABLED }
$envSwitch = $envSwitch.Trim().ToLowerInvariant()
$envSwitchOff = @("off", "0", "false", "no") -contains $envSwitch
$envSwitchOn = @("on", "1", "true", "yes") -contains $envSwitch

$effectivePassword = if ($filePassword) { $filePassword } else { $envPassword }
if ($fileHasEnabled) {
    $authEnabled = $fileEnabled
} elseif ($envSwitchOff) {
    $authEnabled = $false
} elseif ($envSwitchOn) {
    $authEnabled = $true
} else {
    $authEnabled = $effectivePassword -ne ""
}

if ($authEnabled -and -not $effectivePassword) {
    throw ("Защита паролем включена, но пароль пуст.`n" +
        "Задайте SHARE_BASIC_AUTH_PASSWORD в ui\.env.local или пароль в ui\.share-auth.json:`n" +
        "  powershell -ExecutionPolicy Bypass -File scripts\share_auth.ps1 -On -Password '<пароль>'")
}

if (-not $authEnabled) {
    if ($NoAuth) {
        Write-Warning ("ВНИМАНИЕ: -NoAuth — публичное демо будет открыто БЕЗ ПАРОЛЯ. " +
            "Ссылку сможет открыть любой, у кого она есть.")
    } elseif ($envSwitchOff) {
        Write-Warning ("ВНИМАНИЕ: SHARE_AUTH_ENABLED=off — публичное демо будет открыто БЕЗ ПАРОЛЯ. " +
            "Уберите эту настройку или задайте SHARE_BASIC_AUTH_PASSWORD в ui\.env.local.")
    } elseif ($fileHasEnabled -and -not $fileEnabled) {
        throw ("Публичный туннель не запущен: в ui\.share-auth.json стоит enabled=false, " +
            "поэтому демо было бы открыто без пароля.`n" +
            "Включите пароль: scripts\share_auth.ps1 -On -Password '<пароль>'`n" +
            "Либо осознанно отключите защиту на этот запуск флагом -NoAuth.")
    } else {
        throw ("Публичный туннель не запущен: пароль для демо не задан, и ссылка была бы открыта всем.`n" +
            "Задайте пароль одним из способов:`n" +
            "  1. В ui\.env.local: SHARE_BASIC_AUTH_PASSWORD=<пароль> (и при необходимости SHARE_BASIC_AUTH_USER).`n" +
            "  2. Или горячо, без перезапуска: scripts\share_auth.ps1 -On -Password '<пароль>'.`n" +
            "Если демо действительно должно быть открытым, запустите скрипт с -NoAuth.")
    }
}

if ($NoAuth) {
    # Наследуется процессом UI; файл .share-auth.json всё равно важнее.
    $env:SHARE_AUTH_ENABLED = "off"
}

$logDir = Join-Path ([System.IO.Path]::GetTempPath()) "audit-share-ui"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$apiLog = Join-Path $logDir "langgraph.out.log"
$apiErr = Join-Path $logDir "langgraph.err.log"
$uiLog = Join-Path $logDir "ui.out.log"
$uiErr = Join-Path $logDir "ui.err.log"
$tunnelLog = Join-Path $logDir "tunnel.out.log"
$tunnelErr = Join-Path $logDir "tunnel.err.log"

$api = $null
$front = $null
$tunnel = $null

function Stop-Tree($process) {
    if ($process -and -not $process.HasExited) {
        # npm.cmd и cloudflared запускают дочерние процессы: /T гасит всё дерево.
        & taskkill.exe /PID $process.Id /T /F *> $null
    }
}

function Wait-Http($url, $timeoutSec, $name, $logPath) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 `
                -MaximumRedirection 0 -ErrorAction Stop | Out-Null
            return
        } catch {
            $response = $_.Exception.Response
            # 401/403/404 — сервер уже отвечает, этого достаточно.
            if ($response -and [int]$response.StatusCode -lt 500) { return }
        }
        Start-Sleep -Milliseconds 700
    }
    throw "$name не ответил за $timeoutSec с. Лог: $logPath"
}

function Read-TunnelUrl {
    $pattern = "https://[a-z0-9-]+\.trycloudflare\.com"
    foreach ($file in @($tunnelLog, $tunnelErr)) {
        if (Test-Path $file) {
            $match = Select-String -Path $file -Pattern $pattern -AllMatches |
                Select-Object -First 1
            if ($match) { return $match.Matches[0].Value }
        }
    }
    return $null
}

function Read-ServeoUrl {
    $pattern = "https://[a-z0-9-]+\.serveousercontent\.com"
    foreach ($file in @($tunnelLog, $tunnelErr)) {
        if (Test-Path $file) {
            $match = Select-String -Path $file -Pattern $pattern -AllMatches |
                Select-Object -First 1
            if ($match) { return $match.Matches[0].Value }
        }
    }
    return $null
}

try {
    foreach ($port in @($ApiPort, $UiPort)) {
        if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
            throw "Порт $port уже занят. Скрипт поднимает API и UI сам: остановите старые процессы. Либо откройте только туннель вручную (см. docs/share_ui.md)."
        }
    }

    if (-not $Dev -and -not $NoBuild) {
        Write-Host "Сборка UI (npm run build)..." -ForegroundColor Cyan
        Push-Location $uiDir
        try {
            & $npmCmd run build
            if ($LASTEXITCODE -ne 0) { throw "Сборка UI завершилась с ошибкой." }
        } finally {
            Pop-Location
        }
    }

    Write-Host "Запуск LangGraph API на :$ApiPort..." -ForegroundColor Cyan
    $api = Start-Process -FilePath $langgraphExe `
        -ArgumentList @("dev", "--port", "$ApiPort", "--no-browser") `
        -WorkingDirectory $root -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $apiLog -RedirectStandardError $apiErr

    $uiArgs = if ($Dev) { @("run", "dev") } else { @("run", "start") }
    Write-Host "Запуск интерфейса на :$UiPort..." -ForegroundColor Cyan
    $front = Start-Process -FilePath $env:ComSpec `
        -ArgumentList (@("/c", "npm") + $uiArgs) `
        -WorkingDirectory $uiDir -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $uiLog -RedirectStandardError $uiErr

    Wait-Http "http://127.0.0.1:$ApiPort/ok" 90 "LangGraph API" $apiErr
    Wait-Http "http://127.0.0.1:$UiPort/" 180 "Интерфейс" $uiErr

    if ($Serveo) {
        Write-Host "Открываю SSH-туннель serveo.net..." -ForegroundColor Cyan
        $tunnel = Start-Process -FilePath $sshCmd -ArgumentList @(
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "UserKnownHostsFile=$env:TEMP\audit_known_hosts",
            "-o", "ServerAliveInterval=30",
            "-R", "80:localhost:$UiPort",
            "serveo.net") -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $tunnelLog -RedirectStandardError $tunnelErr
    } elseif ($TunnelName) {
        Write-Host "Открываю named-туннель '$TunnelName'..." -ForegroundColor Cyan
        $tunnel = Start-Process -FilePath $cloudflaredCmd -ArgumentList @(
            "--config", $ConfigPath, "tunnel", "run", $TunnelName) -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $tunnelLog -RedirectStandardError $tunnelErr
    } else {
        Write-Host "Открываю быстрый туннель..." -ForegroundColor Cyan
        $tunnel = Start-Process -FilePath $cloudflaredCmd -ArgumentList @(
            "tunnel", "--url", "http://localhost:$UiPort", "--no-autoupdate") -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $tunnelLog -RedirectStandardError $tunnelErr
    }

    $publicUrl = $null
    if ($TunnelName) {
        $publicUrl = "https://$Hostname"
        try {
            Wait-Http $publicUrl 120 "Туннель $Hostname" $tunnelErr
        } catch {
            Write-Warning $_.Exception.Message
            Write-Warning "Продолжаю: DNS и сертификат Cloudflare иногда поднимаются дольше."
        }
    } else {
        $deadline = (Get-Date).AddSeconds(60)
        while (-not $publicUrl -and (Get-Date) -lt $deadline) {
            if ($tunnel.HasExited) {
                throw "Туннель завершился (код $($tunnel.ExitCode)). Лог: $tunnelErr"
            }
            $publicUrl = if ($Serveo) { Read-ServeoUrl } else { Read-TunnelUrl }
            if (-not $publicUrl) { Start-Sleep -Milliseconds 500 }
        }
    }
    if (-not $publicUrl) {
        throw "Не удалось получить публичный адрес. Лог: $tunnelErr"
    }

    Write-Host ""
    Write-Host "  Публичная ссылка: $publicUrl" -ForegroundColor Green
    if (-not $authEnabled) {
        Write-Host "  ПАРОЛЬ ОТКЛЮЧЁН: ссылку может открыть любой, у кого она есть." -ForegroundColor Red
    } elseif ($NoAuth -and $fileHasEnabled -and $fileEnabled) {
        Write-Host "  -NoAuth проигнорирован: ui\.share-auth.json требует пароль." -ForegroundColor Yellow
        Write-Host "  Вход по паролю: SHARE_BASIC_AUTH_USER / SHARE_BASIC_AUTH_PASSWORD" -ForegroundColor Yellow
    } else {
        Write-Host "  Вход по паролю: SHARE_BASIC_AUTH_USER / SHARE_BASIC_AUTH_PASSWORD" -ForegroundColor Yellow
    }
    Write-Host "  Локально: http://localhost:$UiPort" -ForegroundColor DarkGray
    Write-Host "  Логи: $logDir" -ForegroundColor DarkGray
    Write-Host "  Ctrl+C — остановить всё." -ForegroundColor DarkGray
    Write-Host ""

    while ($true) {
        Start-Sleep -Seconds 2
        if ($api.HasExited) { throw "LangGraph API остановился (код $($api.ExitCode)). Лог: $apiErr" }
        if ($front.HasExited) { throw "Интерфейс остановился (код $($front.ExitCode)). Лог: $uiErr" }
        if ($tunnel.HasExited) { throw "Туннель остановился (код $($tunnel.ExitCode)). Лог: $tunnelErr" }
    }
} finally {
    Write-Host "Останавливаю процессы..." -ForegroundColor Cyan
    Stop-Tree $tunnel
    Stop-Tree $front
    Stop-Tree $api
}
