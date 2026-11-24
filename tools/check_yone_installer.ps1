$ErrorActionPreference = 'Stop'
$path = Join-Path $PSScriptRoot 'install-yone.cmd'
$text = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
$marker = '@POWERSHELL_PAYLOAD@'
$position = $text.LastIndexOf($marker, [StringComparison]::Ordinal)
if ($position -lt 0) { throw 'Missing embedded PowerShell marker' }
$payload = $text.Substring($position + $marker.Length)
$tokens = $errors = $null
[void][System.Management.Automation.Language.Parser]::ParseInput($payload, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
if ($payload -notmatch '(?m)^\$releaseHash = ''[0-9a-f]{64}''') { throw 'Expected a pinned shared release ZIP checksum' }
foreach ($required in @('samira_shopkeeper.lua','samira_shop_crafting.lua','shopkeeper_north.anm2','shopkeeper_south.anm2','shop_ui.anm2')) {
    if (-not $payload.Contains($required)) { throw "Missing shop install requirement: $required" }
}
. ([scriptblock]::Create($payload)) -LibraryOnly

function Assert($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Write-Fixture([string]$Path, [string]$Content, [Text.Encoding]$Encoding = [Text.Encoding]::UTF8) {
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))
    [IO.File]::WriteAllText($Path, $Content, $Encoding)
}

function New-MenuFixture([int[]]$Ids) {
    $layers = ($Ids | ForEach-Object { "<Layer Id=`"$_`" />" }) -join ''
    $tracks = ($Ids | ForEach-Object { "<LayerAnimation LayerId=`"$_`" />" }) -join ''
    return ('<AnimatedActor><Content><Layers>' + $layers + '</Layers></Content>' +
        '<Animations><Animation Name="Yone"><LayerAnimations>' + $tracks +
        '</LayerAnimations></Animation></Animations></AnimatedActor>')
}

$temp = [IO.Path]::GetTempPath()
$fixture = Join-Path $temp ('Yone-test-' + [guid]::NewGuid().ToString('N'))
$ourMetadata = '<metadata><name>Soul Fighter Samira</name><directory>samira_testroom</directory></metadata>'
try {
    $unicode = -join ([char]0x0419, [char]0x043e, [char]0x043d, [char]0x0435)
    $game = Join-Path $fixture 'Isaac Host'
    $runtime = Join-Path $game 'Repentogon'
    $save = Join-Path $fixture "$unicode Save"
    $customHost = Join-Path $fixture "$unicode Data"
    $mods = Join-Path $customHost 'mods'
    $rootFile = Join-Path $game 'savedatapath.txt'
    $nestedFile = Join-Path $runtime 'savedatapath.txt'
    Write-Fixture $rootFile "Save Data Path: $save`r`nModding Data Path: `"$mods/`"`r`n" ([Text.Encoding]::UTF8)
    $paths = Get-IsaacPaths $runtime $game
    Assert ($paths.Log -eq (Join-Path $save 'log.txt')) 'Fresh runtime lost Unicode root save path'
    Assert ($paths.Mods -ceq "$mods/") 'Fresh runtime rewrote the explicit mods path'
    Assert ($paths.Status -eq (Join-Path $customHost 'data\samira_testroom_link')) 'The mods directory did not resolve to sibling data'

    $nestedSave = Join-Path $fixture "$unicode Nested Save"
    $nestedMods = Join-Path $fixture "$unicode Custom Content"
    Write-Fixture $nestedFile "Save Data Path: $nestedSave`r`nModding Data Path: $nestedMods`r`n" ([Text.Encoding]::Unicode)
    $paths = Get-IsaacPaths $runtime $game
    Assert ($paths.Log -eq (Join-Path $nestedSave 'log.txt') -and $paths.Mods -eq $nestedMods) 'UTF-16 nested paths did not override root'
    Assert ($paths.Status -eq (Join-Path $game 'data\samira_testroom_link')) 'Custom non-mods folder did not use standard host data'

    $plain = Join-Path $fixture 'Binding of Isaac Repentance'
    Write-Fixture $rootFile "Save Data Path: $plain/`nModding Data Path: $mods/`n"
    $paths = Get-IsaacPaths '' $game
    Assert ($paths.Log -eq (Join-Path ($plain + '+') 'log.txt')) 'Fresh runtime would read a stale vanilla Repentance log'

    $source = Join-Path $fixture 'new mod'
    $destination = Join-Path $mods 'samira_testroom'
    $backupRoot = Join-Path $customHost '.yone-mod-backups'
    Write-Fixture (Join-Path $source 'metadata.xml') $ourMetadata
    Write-Fixture (Join-Path $source 'main.lua') 'fresh'
    Write-Fixture (Join-Path $source 'content\players.xml') '<players><player name="Samira" /></players>'
    $missingRoster = $false
    try { Install-OwnedMod $source $mods } catch { $missingRoster = $true }
    Assert ($missingRoster -and -not [IO.Directory]::Exists($destination)) 'A Samira-only package was installed as Yone'
    Write-Fixture (Join-Path $source 'content\players.xml') '<players><player name="Samira" /><player name="Yone" /></players>'
    Write-Fixture (Join-Path $source 'content\gfx\charactermenu.anm2') (New-MenuFixture @(0, 1, 2, 3, 4))
    $missingPortrait = $false
    try { Install-OwnedMod $source $mods } catch { $missingPortrait = $true }
    Assert ($missingPortrait -and -not [IO.Directory]::Exists($destination)) 'A package without Yone portrait animation was installed'
    $portrait = Join-Path $source 'content\gfx\characterportraits.anm2'
    Write-Fixture $portrait ((New-MenuFixture @(0, 1)).Replace('<LayerAnimation LayerId="0" />', ''))
    $sparse = $false
    try { Install-OwnedMod $source $mods } catch { $sparse = $true }
    Assert ($sparse -and -not [IO.Directory]::Exists($destination)) 'Sparse v6 portrait tracks were accepted'
    Write-Fixture $portrait (New-MenuFixture @(0))
    Write-Fixture (Join-Path $mods 'unrelated\personal.txt') 'retain'
    Install-OwnedMod $source $mods
    Assert ([IO.File]::ReadAllText((Join-Path $destination 'main.lua')) -eq 'fresh') 'Fresh install did not write the mod'
    Assert (Test-YoneRoster $destination) 'Installed payload failed the roster check'
    Assert (-not [IO.Directory]::Exists($backupRoot)) 'Fresh install created a spurious backup'
    Install-OwnedMod $source $mods
    Assert (-not [IO.Directory]::Exists($backupRoot)) 'An unchanged run created a backup'

    Remove-Item -LiteralPath (Join-Path $destination '.yone-bootstrap-owned')
    Write-Fixture (Join-Path $destination 'personal-lua-file.lua') 'retain in backup'
    Write-Fixture (Join-Path $source 'main.lua') 'upgrade'
    Install-OwnedMod $source $mods
    $backups = @(Get-ChildItem -LiteralPath $backupRoot -Directory -Force)
    Assert ($backups.Count -eq 1) 'Legacy upgrade did not create exactly one backup outside mods'
    Assert ([IO.File]::ReadAllText((Join-Path $backups[0].FullName 'main.lua')) -eq 'fresh') 'Backup lost the previous release'
    Assert ([IO.File]::Exists((Join-Path $backups[0].FullName 'personal-lua-file.lua'))) 'Backup lost a custom file in the old release'
    Assert ([IO.File]::ReadAllText((Join-Path $destination 'main.lua')) -eq 'upgrade') 'Legacy migration did not install the update'
    Install-OwnedMod $source $mods
    Assert (@(Get-ChildItem -LiteralPath $backupRoot -Directory -Force).Count -eq 1) 'Repeated upgrade spammed backups'
    Assert (@(Get-ChildItem -LiteralPath $mods -Force).Count -eq 2) 'Installer left temporary or backup directories in engine-scanned mods'
    Assert ([IO.File]::ReadAllText((Join-Path $mods 'unrelated\personal.txt')) -eq 'retain') 'Installer changed an unrelated mod'

    Write-Fixture (Join-Path $destination 'disable.it') ''
    Install-OwnedMod $source $mods
    $backups = @(Get-ChildItem -LiteralPath $backupRoot -Directory -Force)
    Assert (-not [IO.File]::Exists((Join-Path $destination 'disable.it'))) 'Our installed mod is still disabled'
    Assert (@($backups | Where-Object { [IO.File]::Exists((Join-Path $_.FullName 'disable.it')) }).Count -eq 1) 'Previous disabled state was not preserved'
    Install-OwnedMod $source $mods
    Assert (@(Get-ChildItem -LiteralPath $backupRoot -Directory -Force).Count -eq 2) 'Re-enabled mod created another backup on rerun'

    $foreignMods = Join-Path $fixture 'foreign\mods'
    $foreign = Join-Path $foreignMods 'samira_testroom'
    $wrongMetadata = $ourMetadata.Replace('Soul Fighter Samira', 'Someone Else')
    Write-Fixture (Join-Path $foreign 'metadata.xml') $wrongMetadata
    Write-Fixture (Join-Path $foreign 'main.lua') 'foreign'
    $blocked = $false
    try { Install-OwnedMod $source $foreignMods } catch { $blocked = $true }
    Assert $blocked 'A foreign same-directory mod was accepted'
    Assert ([IO.File]::ReadAllText((Join-Path $foreign 'main.lua')) -eq 'foreign') 'A foreign mod was overwritten'

    $legacy = Join-Path $fixture "$unicode Old Release\companion"
    $python = Join-Path $legacy 'python\pythonw.exe'
    $renderer = Join-Path $legacy 'tools\run_testroom_renderer.py'
    Write-Fixture $renderer 'fixture, never run'
    $status = Join-Path $customHost 'data\samira_testroom_link'
    $candidate = @{ ProcessId = 12345; ExecutablePath = $python; CommandLine = ('"{0}" -u "{1}" --status-dir "{2}"' -f $python, $renderer, $status) }
    Assert ((Find-CompanionProcess $candidate @($status) @()) -eq $legacy) 'An exact extracted legacy companion was missed'
    Assert (-not (Find-CompanionProcess $candidate @($paths.HostStatus) @())) 'A renderer for another status directory was accepted'
    Write-Fixture (Join-Path $legacy 'work\portable-renderer.pid') '12345'
    Assert ((Find-CompanionProcess $candidate @($paths.HostStatus) @($legacy)) -eq $legacy) 'Known cache PID did not cover an old status path'
    $candidate.CommandLine = $candidate.CommandLine.Replace('renderer.py', 'renderer.py.unrelated')
    Assert (-not (Find-CompanionProcess $candidate @($status) @($legacy))) 'Non-exact script identity was accepted'
    $candidate.CommandLine = $null
    Assert (-not (Find-CompanionProcess $candidate @($status) @($legacy))) 'An uninspectable process was treated as a verified companion'

    $stdout = Join-Path $fixture 'renderer.log'
    Write-Fixture $stdout 'Ready: Soul Fighter; GPU mock'
    Assert (-not (Test-RendererReady $stdout)) 'Samira-only readiness was accepted'
    Write-Fixture $stdout 'Yone model loaded'
    Assert (-not (Test-RendererReady $stdout)) 'A partially initialized Companion was accepted'
    Write-Fixture $stdout "Yone model loaded`r`nReady: Soul Fighter; GPU mock`r`n"
    Assert (Test-RendererReady $stdout) 'Full Companion readiness was missed'
    Assert (-not (Test-PresentedFrame $stdout)) 'GPU initialization was treated as an in-game frame'
    Add-Content -LiteralPath $stdout 'LIVE frame presented: {"hero":"yone"}'
    Assert (Test-PresentedFrame $stdout) 'A presented frame was missed'

    $exe = Join-Path $game 'isaac-ng.exe'
    $launcherArgs = '--isaac="' + $exe + '" --skip-wizard --launch-mode=repentogon --stealth-mode'
    Assert ((Get-LauncherArguments $exe) -ceq $launcherArgs) 'Official launcher arguments were changed'
    $localCache = Join-Path $fixture "$unicode Cache"
    $programs = Join-Path $fixture "$unicode Start Menu"
    $download = Join-Path $fixture 'Install-Yone.cmd'
    Write-Fixture $download 'first installer'
    [void][IO.Directory]::CreateDirectory($localCache)
    Install-PlayShortcut $download $localCache $programs $exe
    $play = Join-Path $localCache 'Play-Yone.cmd'
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path $programs 'Isaac - Yone.lnk'))
    Assert ((Test-SamePath $link.TargetPath $play) -and (Test-SamePath $link.WorkingDirectory $localCache)) 'Start Menu shortcut does not use the installed copy'
    Write-Fixture $download 'updated installer'
    Install-PlayShortcut $download $localCache $programs $exe
    Install-PlayShortcut $play $localCache $programs $exe
    Assert ([IO.File]::ReadAllText($play) -eq 'updated installer') 'Rerun did not preserve the updated launcher'

    $zip = Join-Path $fixture 'verified.zip'
    Compress-Archive -LiteralPath $source -DestinationPath $zip
    $sha256 = (Get-FileHash -LiteralPath $zip).Hash
    Get-VerifiedFile 'https://invalid.invalid/not-requested' $zip $sha256
    $cached = Join-Path $fixture 'cached'
    Install-CachedArchive $zip $cached $sha256 'new mod' @('main.lua')
    Write-Fixture (Join-Path $cached 'retained.cache') 'cache used'
    Install-CachedArchive $zip $cached $sha256 'new mod' @('main.lua')
    Assert ([IO.File]::Exists((Join-Path $cached 'retained.cache'))) 'Verified payload was extracted again'

    Write-Host 'PASS: Windows PowerShell parser, paths, fresh install, legacy migration, unchanged rerun, foreign protection, companion identity, readiness and cache'
} finally {
    if ([IO.Directory]::Exists($fixture)) {
        Remove-OwnedStage $fixture $temp 'Yone-test-'
    }
}
