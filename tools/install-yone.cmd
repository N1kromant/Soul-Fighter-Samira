@echo off
setlocal
set "YONE_BOOTSTRAP=%~f0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -Sta -Command "$t=[IO.File]::ReadAllText($env:YONE_BOOTSTRAP,[Text.Encoding]::UTF8);$m='@POWERSHELL_PAYLOAD@';$i=$t.LastIndexOf($m,[StringComparison]::Ordinal);if($i -lt 0){throw 'Missing payload'};& ([scriptblock]::Create($t.Substring($i+$m.Length)))"
set "YONE_EXIT=%errorlevel%"
if not "%YONE_EXIT%"=="0" pause
exit /b %YONE_EXIT%
@POWERSHELL_PAYLOAD@
param([switch]$LibraryOnly)
$ErrorActionPreference = 'Stop'
$modDirectory = 'samira_testroom'
$modMarker = '.yone-bootstrap-owned'

function Read-PathFile([string]$File) {
    try {
        $utf8 = New-Object Text.UTF8Encoding($false, $true)
        return [IO.File]::ReadAllText($File, $utf8)
    } catch [Text.DecoderFallbackException] {
        return [IO.File]::ReadAllText($File, [Text.Encoding]::Default)
    }
}

function Get-IsaacPaths([string]$Runtime, [string]$Game) {
    $save = $null
    $mods = $null
    foreach ($base in @($Runtime, $Game) | Select-Object -Unique) {
        if (-not $base) { continue }
        $file = Join-Path $base 'savedatapath.txt'
        if (-not [IO.File]::Exists($file)) { continue }
        $text = Read-PathFile $file
        if (-not $save -and $text -match '(?im)^\s*Save Data Path:[ \t]*(.+?)\s*$') {
            $save = $Matches[1].Trim().Trim('"')
            if ($base -eq $Game -and [IO.Path]::GetFileName($save.TrimEnd('\', '/')) -eq 'Binding of Isaac Repentance') {
                # An old vanilla run may have left the previous DLC's default path here.
                $save = $save.TrimEnd('\', '/') + '+'
            }
        }
        if (-not $mods -and $text -match '(?im)^\s*Modding Data Path:[ \t]*(.+?)\s*$') {
            $mods = $Matches[1].Trim().Trim('"')
        }
    }
    if (-not $save) {
        $documents = [Environment]::GetFolderPath('MyDocuments')
        if (-not $documents) { $documents = Join-Path $env:USERPROFILE 'Documents' }
        $save = Join-Path $documents 'My Games\Binding of Isaac Repentance+'
    }
    if (-not $mods) { $mods = Join-Path $Game 'mods' }
    foreach ($path in @($save, $mods)) {
        if ($path -notmatch '^(?:[a-zA-Z]:[\\/]|[\\/]{2}[^\\/]+[\\/][^\\/]+)') {
            throw "В savedatapath.txt указан неполный путь: $path"
        }
    }
    $modsPath = [IO.Path]::GetFullPath($mods).TrimEnd('\', '/')
    $dataHost = $Game
    if ([IO.Path]::GetFileName($modsPath) -ieq 'mods') {
        $dataHost = [IO.Path]::GetDirectoryName($modsPath)
    }
    return @{
        Log = Join-Path $save 'log.txt'
        Mods = $mods
        Status = Join-Path $dataHost 'data\samira_testroom_link'
        HostStatus = Join-Path $Game 'data\samira_testroom_link'
    }
}

function Read-ModXml([string]$Path) {
    $settings = New-Object Xml.XmlReaderSettings
    $settings.DtdProcessing = 'Prohibit'
    $reader = [Xml.XmlReader]::Create($Path, $settings)
    try {
        $xml = New-Object Xml.XmlDocument
        $xml.Load($reader)
        return $xml
    } finally { $reader.Dispose() }
}

function Test-OurMod([string]$Path) {
    try {
        $xml = Read-ModXml (Join-Path $Path 'metadata.xml')
        $name = $xml.SelectSingleNode('/metadata/name')
        $directory = $xml.SelectSingleNode('/metadata/directory')
        return $name -and $directory -and $name.InnerText -ceq 'Soul Fighter Samira' -and
            $directory.InnerText -ceq $modDirectory
    } catch { return $false }
}

function Test-YoneRoster([string]$Path) {
    try {
        $players = Read-ModXml (Join-Path $Path 'content\players.xml')
        if ($players.SelectNodes('/players/player[@name="Yone"]').Count -ne 1) { return $false }
        foreach ($file in @('charactermenu.anm2', 'characterportraits.anm2')) {
            $menu = Read-ModXml (Join-Path $Path "content\gfx\$file")
            if ($menu.SelectNodes('/AnimatedActor/Animations/Animation[@Name="Yone"]').Count -ne 1) {
                return $false
            }
            $layers = $menu.SelectNodes('/AnimatedActor/Content/Layers/Layer')
            $expected = if ($file -eq 'charactermenu.anm2') { '0,1,2,3,4' } else { '0' }
            if ((($layers | ForEach-Object { $_.GetAttribute('Id') }) -join ',') -cne $expected) { return $false }
            foreach ($animation in $menu.SelectNodes('/AnimatedActor/Animations/Animation')) {
                $tracks = $animation.SelectNodes('LayerAnimations/LayerAnimation')
                if ((($tracks | ForEach-Object { $_.GetAttribute('LayerId') }) -join ',') -cne $expected) { return $false }
            }
        }
        return $true
    } catch { return $false }
}

function Assert-ModDestination([string]$Destination) {
    if (-not (Test-Path -LiteralPath $Destination)) { return }
    $item = Get-Item -LiteralPath $Destination -Force
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        (-not [IO.File]::Exists((Join-Path $Destination $modMarker)) -and -not (Test-OurMod $Destination))) {
        throw "Папка $Destination принадлежит другому моду. Установка оставила её без изменений."
    }
}

function Test-ModFiles([string]$Source, [string]$Destination) {
    foreach ($file in Get-ChildItem -LiteralPath $Source -File -Recurse -Force) {
        $relative = $file.FullName.Substring($Source.Length).TrimStart('\', '/')
        $target = Join-Path $Destination $relative
        if (-not [IO.File]::Exists($target) -or (Get-Item -LiteralPath $target).Length -ne $file.Length -or
            (Get-FileHash -LiteralPath $target).Hash -ne (Get-FileHash -LiteralPath $file.FullName).Hash) {
            return $false
        }
    }
    return $true
}

function Remove-OwnedStage([string]$Path, [string]$Parent, [string]$Prefix) {
    if (-not [IO.Directory]::Exists($Path)) { return }
    $item = Get-Item -LiteralPath $Path -Force
    $expectedParent = [IO.Path]::GetFullPath($Parent).TrimEnd('\', '/')
    if ($item.Parent.FullName.TrimEnd('\', '/') -eq $expectedParent -and
        $item.Name -match ('^' + [regex]::Escape($Prefix) + '[0-9a-f]{32}$') -and
        -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Remove-Item -LiteralPath $item.FullName -Recurse -Force
    }
}

function Install-OwnedMod([string]$Source, [string]$Mods) {
    if (-not (Test-OurMod $Source) -or -not [IO.File]::Exists((Join-Path $Source 'main.lua'))) {
        throw 'В архиве отсутствует рабочая копия Soul Fighter Samira.'
    }
    if (-not (Test-YoneRoster $Source)) {
        throw 'Архив не прошёл проверку записи Ёнэ и слоёв меню выбора.'
    }
    $source = [IO.Path]::GetFullPath($Source).TrimEnd('\', '/')
    $modsFull = [IO.Path]::GetFullPath($Mods)
    $parent = [IO.Directory]::GetParent($modsFull.TrimEnd('\', '/'))
    if (-not $parent) { throw "Невозможно подготовить резервную копию рядом с mods: $Mods" }
    $destination = Join-Path $modsFull $modDirectory
    Assert-ModDestination $destination
    if ([IO.Directory]::Exists($destination) -and -not [IO.File]::Exists((Join-Path $destination 'disable.it')) -and
        (Test-ModFiles $source $destination)) {
        $installedMarker = Join-Path $destination $modMarker
        if (-not [IO.File]::Exists($installedMarker)) { [IO.File]::WriteAllText($installedMarker, 'Soul Fighter Samira') }
        Write-Host 'Мод уже установлен.'
        return
    }

    [void][IO.Directory]::CreateDirectory($modsFull)
    $id = [guid]::NewGuid().ToString('N')
    $stage = Join-Path $parent.FullName ".yone-mod-stage-$id"
    $backup = $null
    try {
        Copy-Item -LiteralPath $source -Destination $stage -Recurse -Force
        if (-not (Test-ModFiles $source $stage)) { throw 'Копирование файлов мода не прошло проверку.' }
        [IO.File]::WriteAllText((Join-Path $stage $modMarker), 'Soul Fighter Samira')
        Assert-ModDestination $destination
        if ([IO.Directory]::Exists($destination)) {
            $backups = Join-Path $parent.FullName '.yone-mod-backups'
            [void][IO.Directory]::CreateDirectory($backups)
            $backup = Join-Path $backups "samira_testroom-$id"
            [IO.Directory]::Move($destination, $backup)
        }
        [IO.Directory]::Move($stage, $destination)
    } catch {
        if ($backup -and [IO.Directory]::Exists($backup) -and -not (Test-Path -LiteralPath $destination)) {
            [IO.Directory]::Move($backup, $destination)
        }
        throw
    } finally { Remove-OwnedStage $stage $parent.FullName '.yone-mod-stage-' }
    if ($backup) { Write-Host "Резервная копия предыдущей версии: $backup" }
}

function Get-Steam {
    $keys = @('HKCU:\Software\Valve\Steam', 'HKLM:\SOFTWARE\Valve\Steam',
        'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam')
    $candidates = @(
        foreach ($process in Get-Process -Name 'steam' -ErrorAction SilentlyContinue) {
            try { if ($process.Path) { Split-Path -Path $process.Path -Parent } } catch {}
        }
        foreach ($key in $keys) {
            $value = Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
            if ($value.SteamPath) { $value.SteamPath }
            if ($value.InstallPath) { $value.InstallPath }
            if ($value.SteamExe) { Split-Path -Path $value.SteamExe -Parent }
        }
        foreach ($programFiles in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
            if ($programFiles) { Join-Path $programFiles 'Steam' }
        }
    )
    foreach ($candidate in $candidates | Select-Object -Unique) {
        $root = [IO.Path]::GetFullPath($candidate)
        $exe = Join-Path $root 'steam.exe'
        if ([IO.File]::Exists($exe)) { return @{ Root = $root; Exe = $exe } }
    }
}

function Find-Game([string]$Steam) {
    $libraries = @($Steam)
    $vdf = Join-Path $Steam 'steamapps\libraryfolders.vdf'
    if ([IO.File]::Exists($vdf)) {
        foreach ($match in [regex]::Matches((Read-PathFile $vdf), '(?im)^\s*"path"\s+"([^"]+)"')) {
            $libraries += $match.Groups[1].Value.Replace('\\', '\')
        }
    }
    foreach ($library in $libraries | Select-Object -Unique) {
        $manifest = Join-Path $library 'steamapps\appmanifest_250900.acf'
        if (-not [IO.File]::Exists($manifest)) { continue }
        $text = Read-PathFile $manifest
        if ($text -notmatch '"installdir"\s+"([^"\\/:]+)"' -or $Matches[1] -in @('.', '..')) { continue }
        $root = Join-Path $library ('steamapps\common\' + $Matches[1])
        $exe = Join-Path $root 'isaac-ng.exe'
        if (-not [IO.File]::Exists($exe)) { continue }
        $plus = $text -match '"dlcappid"\s+"3353470"' -and [IO.File]::Exists((Join-Path $root 'EOSSDK-Win32-Shipping.dll'))
        return @{ Root = $root; Exe = $exe; RepentancePlus = $plus }
    }
}

function Get-VerifiedFile([string]$Url, [string]$Destination, [string]$Expected) {
    if ($Expected -notmatch '^[0-9a-fA-F]{64}$') { throw 'В этом установщике отсутствует контрольная сумма выпуска.' }
    if ([IO.File]::Exists($Destination) -and (Get-FileHash -LiteralPath $Destination).Hash -eq $Expected) { return }
    $temp = $Destination + '.download'
    try {
        $ProgressPreference = 'SilentlyContinue'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Write-Host ('Скачиваю ' + [IO.Path]::GetFileName($Destination) + '…')
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $temp
        if ((Get-FileHash -LiteralPath $temp).Hash -ne $Expected) {
            throw "Контрольная сумма скачанного файла не совпала: $Url"
        }
        Move-Item -LiteralPath $temp -Destination $Destination -Force
    } finally {
        if ([IO.File]::Exists($temp)) { Remove-Item -LiteralPath $temp -Force }
    }
}

function Test-RequiredFiles([string]$Directory, [string[]]$Files) {
    foreach ($file in $Files) {
        if (-not [IO.File]::Exists((Join-Path $Directory $file))) { return $false }
    }
    return $true
}

function Install-CachedArchive([string]$Zip, [string]$Destination, [string]$Hash,
    [string]$ArchiveRoot, [string[]]$Required) {
    $markerName = '.yone-verified-archive'
    $marker = Join-Path $Destination $markerName
    if ([IO.File]::Exists($marker) -and [IO.File]::ReadAllText($marker) -eq $Hash -and
        (Test-RequiredFiles $Destination $Required)) { return }

    $parent = Split-Path -Path $Destination -Parent
    $id = [guid]::NewGuid().ToString('N')
    $stage = Join-Path $parent "extract-$id"
    $old = $null
    try {
        Expand-Archive -LiteralPath $Zip -DestinationPath $stage
        $extracted = $stage
        if ($ArchiveRoot) { $extracted = Join-Path $stage $ArchiveRoot }
        if (-not (Test-RequiredFiles $extracted $Required)) { throw "В архиве не хватает файлов: $Zip" }
        [IO.File]::WriteAllText((Join-Path $extracted $markerName), $Hash)
        if ([IO.Directory]::Exists($Destination)) {
            $old = "$Destination-invalid-$id"
            [IO.Directory]::Move($Destination, $old)
        }
        [IO.Directory]::Move($extracted, $Destination)
    } catch {
        if ($old -and [IO.Directory]::Exists($old) -and -not (Test-Path -LiteralPath $Destination)) {
            [IO.Directory]::Move($old, $Destination)
        }
        throw
    } finally { Remove-OwnedStage $stage $parent 'extract-' }
}

function Test-SamePath([string]$Left, [string]$Right) {
    if (-not $Left -or -not $Right -or -not [IO.Path]::IsPathRooted($Left) -or -not [IO.Path]::IsPathRooted($Right)) {
        return $false
    }
    try {
        return [IO.Path]::GetFullPath($Left).TrimEnd('\', '/') -ieq [IO.Path]::GetFullPath($Right).TrimEnd('\', '/')
    } catch { return $false }
}

function Get-RendererPid([string]$Companion) {
    $file = Join-Path $Companion 'work\portable-renderer.pid'
    $number = 0
    if ([IO.File]::Exists($file) -and [int]::TryParse([IO.File]::ReadAllText($file).Trim(), [ref]$number) -and $number -gt 0) {
        return $number
    }
}

function Find-CompanionProcess($Candidate, [string[]]$Statuses, [string[]]$Installed) {
    if (-not $Candidate.ExecutablePath -or -not $Candidate.CommandLine) { return }
    $pythonFolder = [IO.Directory]::GetParent($Candidate.ExecutablePath)
    if (-not $pythonFolder -or $pythonFolder.Name -ine 'python' -or $pythonFolder.Parent.Name -ine 'companion' -or
        [IO.Path]::GetFileName($Candidate.ExecutablePath) -ine 'pythonw.exe') { return }
    $companion = $pythonFolder.Parent.FullName
    $script = Join-Path $companion 'tools\run_testroom_renderer.py'
    if (-not [IO.File]::Exists($script)) { return }

    $argsFound = @([regex]::Matches($Candidate.CommandLine, '(?:[^\s"]+|"[^"]*")+') | ForEach-Object { $_.Value.Replace('"', '') })
    $scriptIndex = 1
    if ($argsFound.Count -gt 1 -and $argsFound[1] -ceq '-u') { $scriptIndex = 2 }
    if ($argsFound.Count -le $scriptIndex -or -not (Test-SamePath $argsFound[$scriptIndex] $script)) { return }
    for ($index = $scriptIndex + 1; $index -lt $argsFound.Count; $index++) {
        $argument = $argsFound[$index]
        $status = $null
        if ($argument -ceq '--status-dir' -and $index + 1 -lt $argsFound.Count) { $status = $argsFound[++$index] }
        elseif ($argument.StartsWith('--status-dir=', [StringComparison]::Ordinal)) { $status = $argument.Substring(13) }
        foreach ($expected in $Statuses) {
            if (Test-SamePath $status $expected) { return $companion }
        }
    }
    foreach ($payload in $Installed) {
        if ((Test-SamePath $companion $payload) -and (Get-RendererPid $payload) -eq $Candidate.ProcessId) { return $companion }
    }
}

function Stop-Companion([Diagnostics.Process]$Process, [string]$Companion) {
    if ($Process.HasExited) { return }
    $work = Join-Path $Companion 'work'
    [void][IO.Directory]::CreateDirectory($work)
    [IO.File]::WriteAllText((Join-Path $work 'testroom-renderer.stop'), 'stop')
    if (-not $Process.WaitForExit(12000)) {
        throw "Companion не завершился. Закрой предыдущую сборку и запусти установщик снова. Папка: $Companion"
    }
}

function Stop-OldCompanions([string]$Cache, [string[]]$Statuses) {
    $installed = @(
        Get-ChildItem -LiteralPath $Cache -Directory -Filter 'payload*' | ForEach-Object { Join-Path $_.FullName 'companion' }
    )
    $candidates = @()
    try { $candidates = @(Get-CimInstance -ClassName Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction Stop) }
    catch { Write-Host 'Windows не предоставила сведения о запущенных Companion. Установщик проверит сохранённые PID.' }

    $stopped = @{}
    foreach ($candidate in $candidates) {
        $companion = Find-CompanionProcess $candidate $Statuses $installed
        if (-not $companion) { continue }
        $process = Get-Process -Id $candidate.ProcessId -ErrorAction SilentlyContinue
        if ($process) { Stop-Companion $process $companion }
        $stopped[[int]$candidate.ProcessId] = $true
    }
    foreach ($payload in $installed) {
        $renderId = Get-RendererPid $payload
        if (-not $renderId -or $stopped.ContainsKey($renderId)) { continue }
        $process = Get-Process -Id $renderId -ErrorAction SilentlyContinue
        if ($process -and $process.ProcessName -eq 'pythonw' -and
            (-not $process.Path -or (Test-SamePath $process.Path (Join-Path $payload 'python\pythonw.exe')))) {
            throw "Windows не подтвердила команду запущенного Companion. Закрой предыдущую сборку и повтори установку. Папка: $payload"
        }
    }
}

function Test-RendererReady([string]$Log) {
    if (-not [IO.File]::Exists($Log)) { return $false }
    $text = Get-Content -LiteralPath $Log -Raw -ErrorAction SilentlyContinue
    return $text -match '(?m)^Yone model loaded\r?$' -and $text -match '(?m)^Ready: Soul Fighter(?:[;\r]|$)'
}

function Get-LauncherArguments([string]$Isaac) {
    return '--isaac="' + $Isaac + '" --skip-wizard --launch-mode=repentogon --stealth-mode'
}

function Install-PlayShortcut([string]$Source, [string]$Cache, [string]$Programs, [string]$Isaac) {
    $target = Join-Path $Cache 'Play-Yone.cmd'
    if (-not (Test-SamePath $Source $target)) {
        $stage = Join-Path $Cache 'Play-Yone.cmd.new'
        try {
            [IO.File]::Copy($Source, $stage, $true)
            if ([IO.File]::Exists($target)) { [IO.File]::Replace($stage, $target, [NullString]::Value) }
            else { [IO.File]::Move($stage, $target) }
        } finally {
            if ([IO.File]::Exists($stage)) { [IO.File]::Delete($stage) }
        }
    }
    [void][IO.Directory]::CreateDirectory($Programs)
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path $Programs 'Isaac - Yone.lnk'))
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = $Cache
    $shortcut.IconLocation = "$Isaac,0"
    $shortcut.Description = 'Launch Isaac with REPENTOGON and the Yone Companion'
    $shortcut.Save()
}

function Test-PresentedFrame([string]$Log) {
    if (-not [IO.File]::Exists($Log)) { return $false }
    return [bool](Select-String -LiteralPath $Log -Pattern '^LIVE frame presented: ' -Quiet -ErrorAction SilentlyContinue)
}

if ($LibraryOnly) { return }

$releaseHash = '0b7f3ebfa48ee7a6d3db1d78baadd14f6d8071703df11c4a3df05e007b575ce3'
$releaseUrl = 'https://github.com/N1kromant/Soul-Fighter-Samira/releases/download/mf-v0.5.48/Soul-Fighter-Miss-Fortune-Local-Windows.zip'
$launcherHash = '7e4a45d8b9f099ea79e42f86bc24c2a05b35e239d7bc4d597c11b5bceaccfd6a'
$launcherUrl = 'https://github.com/TeamREPENTOGON/Launcher/releases/download/v0.4.9-beta/REPENTOGONLauncher.zip'
$cache = Join-Path $env:LOCALAPPDATA 'YoneInstaller'
$diagnostic = Join-Path $cache 'installer.log'
$lock = $child = $companion = $null
$transcriptStarted = $false
try {
    [void][IO.Directory]::CreateDirectory($cache)
    try { $lock = [IO.File]::Open((Join-Path $cache 'installer.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
    catch [IO.IOException] { throw 'Установщик уже открыт. Дождись завершения текущего запуска.' }
    Start-Transcript -LiteralPath $diagnostic -Append | Out-Null
    $transcriptStarted = $true
    if (Get-Process -Name 'isaac-ng', 'REPENTOGONLauncher' -ErrorAction SilentlyContinue) {
        throw 'Закрой Isaac и REPENTOGON Launcher, затем снова открой этот установщик.'
    }

    $steam = Get-Steam
    if (-not $steam) {
        Start-Process 'https://store.steampowered.com/about/'
        throw 'Установи Steam и войди в свой аккаунт. Установи The Binding of Isaac: Rebirth с Repentance+, затем снова открой этот файл.'
    }
    $game = Find-Game $steam.Root
    if (-not $game) {
        Start-Process 'steam://install/250900'
        throw 'Установи The Binding of Isaac: Rebirth в Steam. Дождись окончания загрузки игры и Repentance+, затем снова открой этот файл.'
    }
    if (-not $game.RepentancePlus) {
        Start-Process 'steam://store/3353470'
        throw 'Добавь бесплатное Repentance+ в свою библиотеку, включи его в свойствах Isaac в разделе DLC и дождись загрузки. Затем снова открой этот файл.'
    }
    if (-not (Get-Process -Name 'steam' -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath $steam.Exe
        Write-Host 'Steam запущен. Войди в свой аккаунт, если Steam попросит.'
    }

    $runtime = Join-Path $game.Root 'Repentogon'
    foreach ($base in @($runtime, $game.Root)) {
        if (Test-RequiredFiles $base @('zhlSamiraCompanion.dll', 'samira-companion.ini')) {
            throw "В папке $base уже встроен другой Samira Companion. Отключи его штатным способом и повтори установку."
        }
    }
    $paths = Get-IsaacPaths $runtime $game.Root
    Write-Host "Isaac: $($game.Root)"
    Write-Host "Мод: $($paths.Mods)"
    Write-Host "Журнал игры: $($paths.Log)"
    Write-Host "Папка обмена Companion: $($paths.Status)"
    Assert-ModDestination (Join-Path $paths.Mods $modDirectory)

    $releaseZip = Join-Path $cache 'Soul-Fighter-0.5.48.zip'
    $launcherZip = Join-Path $cache 'REPENTOGONLauncher-0.4.9-beta.zip'
    Get-VerifiedFile $releaseUrl $releaseZip $releaseHash
    Get-VerifiedFile $launcherUrl $launcherZip $launcherHash
    $payload = Join-Path $cache ('payload-' + $releaseHash.Substring(0, 16))
    $launcherDir = Join-Path $cache 'REPENTOGONLauncher-0.4.9-beta'
    Stop-OldCompanions $cache @($paths.Status, $paths.HostStatus)
    Install-CachedArchive $releaseZip $payload $releaseHash 'Soul-Fighter-Samira' @(
        'samira_testroom\main.lua', 'samira_testroom\metadata.xml', 'samira_testroom\content\players.xml',
        'samira_testroom\resources\gfx\yone\ability_icons.anm2', 'samira_testroom\resources\gfx\yone\ability_icons.png',
        'samira_testroom\samira_shopkeeper.lua',
        'samira_testroom\samira_shop_crafting.lua',
        'samira_testroom\resources\gfx\league_shop\shopkeeper_north.anm2',
        'samira_testroom\resources\gfx\league_shop\shopkeeper_north.png',
        'samira_testroom\resources\gfx\league_shop\shopkeeper_south.anm2',
        'samira_testroom\resources\gfx\league_shop\shopkeeper_south.png',
        'samira_testroom\resources\gfx\league_shop\shop_ui.anm2',
        'samira_testroom\resources\gfx\league_shop\shop_ui.png',
        'companion\assets\yone-local\yone.glb', 'companion\assets\yone-local\actions.json',
        'companion\python\pythonw.exe', 'companion\tools\run_testroom_renderer.py'
    )
    Install-CachedArchive $launcherZip $launcherDir $launcherHash '' @('REPENTOGONLauncher.exe', 'launcher-data.bin')
    $launcher = Join-Path $launcherDir 'REPENTOGONLauncher.exe'
    Install-OwnedMod (Join-Path $payload $modDirectory) $paths.Mods
    if (-not (Test-YoneRoster (Join-Path $paths.Mods $modDirectory))) {
        throw 'Запись Ёнэ не найдена в установленной копии. Проверь указанный выше путь к mods.'
    }
    Write-Host 'Запись Yone и обе анимации выбора установлены в каталог модов REPENTOGON.'
    Install-PlayShortcut $env:YONE_BOOTSTRAP $cache ([Environment]::GetFolderPath('Programs')) $game.Exe
    Write-Host 'Для следующих запусков используй «Isaac - Yone» в меню Пуск.'

    $companion = Join-Path $payload 'companion'
    $work = Join-Path $companion 'work'
    [void][IO.Directory]::CreateDirectory($work)
    [void][IO.Directory]::CreateDirectory($paths.Status)
    $stop = Join-Path $work 'testroom-renderer.stop'
    if ([IO.File]::Exists($stop)) { Remove-Item -LiteralPath $stop -Force }
    $python = Join-Path $companion 'python\pythonw.exe'
    $renderer = Join-Path $companion 'tools\run_testroom_renderer.py'
    $stdout = Join-Path $work 'testroom-renderer.log'
    $stderr = Join-Path $work 'testroom-renderer.err'
    foreach ($oldLog in @($stdout, $stderr)) {
        if ([IO.File]::Exists($oldLog)) { Remove-Item -LiteralPath $oldLog -Force }
    }
    $rendererArgs = '-u "' + $renderer + '" --log "' + $paths.Log + '" --status-dir "' + $paths.Status + '"'
    $child = Start-Process -FilePath $python -ArgumentList $rendererArgs -WorkingDirectory $companion `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    [IO.File]::WriteAllText((Join-Path $work 'portable-renderer.pid'), [string]$child.Id, [Text.Encoding]::ASCII)
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while (-not $child.HasExited -and $timer.Elapsed.TotalSeconds -lt 60 -and -not (Test-RendererReady $stdout)) {
        Start-Sleep -Milliseconds 250
    }
    $rendererReady = -not $child.HasExited -and (Test-RendererReady $stdout)
    if (-not $rendererReady) {
        Write-Warning "Companion не загрузил модель. Isaac запустится со штатным спрайтом и эффектами. Журналы: $stdout и $stderr"
    }
    Write-Host 'Запускаю REPENTOGON. При первой установке подтверди установку, если появится запрос.'
    Write-Host 'В игре включи Soul Fighter Samira в Mods, если мод выключен, и выбери Yone в новом одиночном забеге.'
    $gameLauncher = Start-Process -FilePath $launcher -ArgumentList (Get-LauncherArguments $game.Exe) -WorkingDirectory $launcherDir -PassThru
    if ($rendererReady) {
        Write-Host 'Жду первый кадр Companion после входа в забег.'
        $frameTimer = $null
        $reportedDelay = $false
        while (-not $child.HasExited -and -not (Test-PresentedFrame $stdout)) {
            if ($gameLauncher.HasExited -and -not (Get-Process -Name 'isaac-ng' -ErrorAction SilentlyContinue)) { break }
            if (-not $frameTimer -and (Select-String -LiteralPath $stdout -Pattern '^Playable Isaac frame received$' -Quiet -ErrorAction SilentlyContinue)) {
                $frameTimer = [Diagnostics.Stopwatch]::StartNew()
            }
            if ($frameTimer -and $frameTimer.Elapsed.TotalSeconds -ge 12 -and -not $reportedDelay) {
                $reportedDelay = $true
                Write-Warning "Companion получает данные игры, но пока не вывел кадр. Причина и параметры экрана в журнале: $stdout"
            }
            Start-Sleep -Milliseconds 700
        }
        if (Test-PresentedFrame $stdout) { Write-Host 'Первый кадр Companion показан в игре.' }
        elseif ($child.HasExited) { Write-Warning "Companion завершился до первого кадра. Журналы: $stdout и $stderr" }
    }
} catch {
    $failure = $_.Exception.Message
    if ($child -and $companion) {
        try { Stop-Companion $child $companion } catch { Write-Host $_.Exception.Message }
    }
    Write-Host $failure -ForegroundColor Red
    Write-Host "Журнал установщика: $diagnostic"
    exit 1
} finally {
    if ($transcriptStarted) { Stop-Transcript -ErrorAction SilentlyContinue | Out-Null }
    if ($lock) { $lock.Dispose() }
}
