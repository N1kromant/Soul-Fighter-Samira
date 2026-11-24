﻿param([switch]$Stop)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms

$companion = Join-Path $PSScriptRoot 'companion'
$python = Join-Path $companion 'python\pythonw.exe'
$renderer = Join-Path $companion 'tools\run_testroom_renderer.py'
$work = Join-Path $companion 'work'
$sourceMod = Join-Path $PSScriptRoot 'samira_testroom'
$settingsFile = Join-Path $work 'portable-launcher.json'
$pidFile = Join-Path $work 'portable-renderer.pid'
$stopFile = Join-Path $work 'testroom-renderer.stop'
$stdout = Join-Path $work 'testroom-renderer.log'
$stderr = Join-Path $work 'testroom-renderer.err'

function Show-Notice([string]$Text, [System.Windows.Forms.MessageBoxIcon]$Icon = 'Information') {
    [void][System.Windows.Forms.MessageBox]::Show($Text, 'Soul Fighter Samira', 'OK', $Icon)
}

function Get-GameRoot([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    $item = Get-Item -LiteralPath $Path -ErrorAction SilentlyContinue
    if (-not $item -or -not $item.PSIsContainer) { return }
    if ($item.Name -eq 'Repentogon') { $item = $item.Parent }
    if (Test-Path -LiteralPath (Join-Path $item.FullName 'isaac-ng.exe') -PathType Leaf) {
        return $item.FullName
    }
}

function Find-SteamGame {
    $steam = Get-ItemPropertyValue -LiteralPath 'HKCU:\Software\Valve\Steam' -Name SteamPath -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($steam)) { return }
    $libraries = @($steam)
    $list = Join-Path $steam 'steamapps\libraryfolders.vdf'
    if (Test-Path -LiteralPath $list -PathType Leaf) {
        $vdf = Get-Content -LiteralPath $list -Raw
        foreach ($match in [regex]::Matches($vdf, '(?im)^\s*"path"\s+"([^"]+)"')) {
            $libraries += $match.Groups[1].Value.Replace('\\', '\')
        }
    }
    foreach ($library in ($libraries | Select-Object -Unique)) {
        $path = Get-GameRoot (Join-Path $library 'steamapps\common\The Binding of Isaac Rebirth')
        if ($path) { return $path }
    }
}

function Select-GameRoot {
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    try {
        $dialog.Description = 'Выбери основной каталог The Binding of Isaac Rebirth. В нём должен быть isaac-ng.exe.'
        $dialog.ShowNewFolderButton = $false
        $guess = Find-SteamGame
        if ($guess) { $dialog.SelectedPath = $guess }
        while ($dialog.ShowDialog() -eq 'OK') {
            $path = Get-GameRoot $dialog.SelectedPath
            if ($path) { return $path }
            Show-Notice 'В этой папке не найден isaac-ng.exe. Выбери каталог установленной игры.' Warning
        }
    } finally {
        $dialog.Dispose()
    }
}

function Get-LogPath([string]$GameRoot, [string]$SavedLog) {
    if ($SavedLog) { return $SavedLog }
    $documents = [Environment]::GetFolderPath('MyDocuments')
    $default = Join-Path $documents 'My Games\Binding of Isaac Repentance+\log.txt'
    $installedPath = Join-Path $GameRoot 'Repentogon\savedatapath.txt'
    if (Test-Path -LiteralPath $installedPath -PathType Leaf) {
        $match = Select-String -LiteralPath $installedPath -Pattern '^Save Data Path:\s*(.+?)\s*$' | Select-Object -First 1
        if ($match) {
            $candidate = Join-Path $match.Matches[0].Groups[1].Value 'log.txt'
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
        }
    }
    if (Test-Path -LiteralPath $default -PathType Leaf) { return $default }
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    try {
        $dialog.Title = 'Выбери log.txt, если он уже лежит в другой папке. Отмена оставит стандартный путь.'
        $dialog.Filter = 'Лог Isaac (log.txt)|log.txt|Текстовые файлы (*.txt)|*.txt'
        $dialog.InitialDirectory = $documents
        if ($dialog.ShowDialog() -eq 'OK') { return $dialog.FileName }
        return $default
    } finally {
        $dialog.Dispose()
    }
}

function Test-ModFiles([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Destination -PathType Container)) { return $false }
    foreach ($file in (Get-ChildItem -LiteralPath $Source -Recurse -File -Force)) {
        $relative = $file.FullName.Substring($Source.Length + 1)
        $target = Join-Path $Destination $relative
        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { return $false }
        if ($file.Length -ne (Get-Item -LiteralPath $target).Length) { return $false }
        if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $target).Hash) { return $false }
    }
    return $true
}

function Get-OwnRenderer {
    if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) { return }
    $childId = 0
    if (-not [int]::TryParse((Get-Content -LiteralPath $pidFile -Raw).Trim(), [ref]$childId) -or $childId -le 0) { return }
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $childId"
    if ($candidate -and $candidate.ExecutablePath -eq $python -and $candidate.CommandLine -and
        $candidate.CommandLine.IndexOf('"' + $renderer + '"', [StringComparison]::OrdinalIgnoreCase) -ge 0) {
        return $candidate
    }
}

$lock = $null
try {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or
        -not (Test-Path -LiteralPath $renderer -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $sourceMod 'main.lua') -PathType Leaf)) {
        throw 'Распакуй архив целиком, затем снова открой launch.cmd.'
    }
    [void][IO.Directory]::CreateDirectory($work)
    try {
        $lock = [IO.File]::Open((Join-Path $work 'portable-launcher.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch [IO.IOException] {
        throw 'Запускатель уже открыт. Дождись окончания текущего запуска.'
    }

    $running = Get-OwnRenderer
    if ($Stop) {
        if ($running) {
            [IO.File]::WriteAllText($stopFile, 'stop')
            Show-Notice 'Рендеру отправлена команда на завершение.'
        } else {
            Show-Notice 'Рендер из этой папки не запущен.'
        }
        exit 0
    }
    if ($running) {
        Show-Notice 'Рендер уже запущен. Открой игру через REPENTOGON и выбери Samira, Yone или Miss Fortune.'
        exit 0
    }

    $settings = $null
    if (Test-Path -LiteralPath $settingsFile -PathType Leaf) {
        try { $settings = Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json } catch {}
    }
    $gameRoot = if ($settings) { Get-GameRoot $settings.gamePath }
    if (-not $gameRoot) {
        $gameRoot = Select-GameRoot
        $settings = $null
        if (-not $gameRoot) { exit 0 }
    }
    $hasRepentogon = (Test-Path -LiteralPath (Join-Path $gameRoot 'Repentogon\zhlREPENTOGON.dll') -PathType Leaf) -or
        (Test-Path -LiteralPath (Join-Path $gameRoot 'zhlREPENTOGON.dll') -PathType Leaf)
    if (-not $hasRepentogon) {
        throw 'В выбранной игре не найден REPENTOGON. Установи его для Repentance+ и снова открой launch.cmd.'
    }
    $savedLog = if ($settings) { $settings.logPath }
    $log = Get-LogPath $gameRoot $savedLog
    $mods = Join-Path $gameRoot 'mods'
    $installedMod = Join-Path $mods 'samira_testroom'
    $status = Join-Path $gameRoot 'data\samira_testroom_link'
    if (-not (Test-ModFiles $sourceMod $installedMod)) {
        if (Get-Process -Name 'isaac-ng' -ErrorAction SilentlyContinue) {
            throw 'Закрой Isaac, чтобы обновить мод, затем снова открой launch.cmd.'
        }
        [void][IO.Directory]::CreateDirectory($mods)
        Copy-Item -LiteralPath $sourceMod -Destination $mods -Recurse -Force
        if (-not (Test-ModFiles $sourceMod $installedMod)) {
            throw 'Файлы мода скопированы не полностью. Проверь, доступен ли каталог mods для записи.'
        }
    }
    [void][IO.Directory]::CreateDirectory($status)
    @{gamePath = $gameRoot; logPath = $log} | ConvertTo-Json | Set-Content -LiteralPath $settingsFile -Encoding UTF8

    if (Test-Path -LiteralPath $stopFile -PathType Leaf) { Remove-Item -LiteralPath $stopFile -Force }
    $arguments = '-u "' + $renderer + '" --log "' + $log + '" --status-dir "' + $status + '"'
    $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $companion -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ASCII
    if ($process.WaitForExit(500)) {
        throw "Рендер завершился при запуске. Журнал находится в companion\work\testroom-renderer.err. $stderr"
    }
    Show-Notice 'Рендер запущен. Открой Isaac через REPENTOGON, включи Soul Fighter Samira в меню Mods и выбери Samira, Yone или Miss Fortune.'
} catch {
    Show-Notice $_.Exception.Message Error
    exit 1
} finally {
    if ($lock) { $lock.Dispose() }
}
