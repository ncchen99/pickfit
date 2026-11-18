"""Ec2WinMachine and Ec2WindowsBox: a Windows box on EC2. The Windows half of the EC2 provider.

ec2_machine.Ec2Instance is the part every pickfit instance on EC2 shares (security groups, lifetime, the
metadata service, the pool); win_machine.WinSshMachine is how a Windows VM is reached; windows_box.WindowsBox is
the box. What is here is the image and how the two meet.

- The image is an AMI pickfit bakes from Amazon's Windows Server 2025 (bake_win_image). EC2 includes the Windows
  Server licence in the instance's price; Windows 11 is not offered that way, so a run on this box is a run on
  Windows Server and its record says so. On a throwaway instance, as the administrator over SSH: Windows Update,
  Remote Desktop, WinRM and the SSM agent off; sbx and the harness directory as VBoxBox's base has them, with a
  password made on the instance that never leaves it except to the harness's own administrator; the firewall
  rules; the task and the two programs that run sbx's commands at its desktop (windows_box.MAKE_JOB); winget's
  source; Git, Node and Python from winget and PowerShell 7 from its release (winget's is a packaged app); sbx's
  own side, as sbx; a restart so sbx logs on at the console once; the current App Installer, and the Store's
  install service off (WIN_APPS); one command of sbx's through the task, which must find a desktop session and
  WMI answering; the hardening and the check every box runs. The last command removes the keys, makes sshd wait
  for the boot script, and resets Amazon's boot agent so the next instance runs its user data. No Sysprep: an
  instance of the image is the builder's Windows as it was shut down, which is what makes it start in about a
  minute.
- A display image (display=True, named pickfit-win-server2025-gui-..., with a pool of its own) adds gui_win's
  parts after the tools (MAKE_DISPLAY: the session helper, a virtual display, the VNC server) and, once sbx is
  logged on, sets sbx's screen to the virtual display alone (gui_win.SCREEN).
- The user data is the boot script in the boot agent's envelope. EC2Launch runs it as SYSTEM from a file under
  SYSTEM's own profile and logs only that file's path (measured 2026-11-16: no script text in the event log).
- Size: Windows wants more memory than the Linux box under it gets, so the box is at least WIN_MEMORY_MB and the
  instance the type that holds it (m7i-flex.large, 8 GiB).

Measured 2026-11-17 on m7i-flex.large, with the harness in Taiwan (ap-east-2 unless another region is named):

- `pickfit verify --limits-test --runner ec2-windows` holds 32 of 32, among them: sbx is a standard user at
  Medium integrity; the logon secret is refused to it; no command line in the PowerShell log carries a script;
  link-local addresses are closed to it by the machine's rule while the administrator's packet arrives; offline,
  nothing answers either of them, no name resolves, and a connection sbx held open carries nothing more.
- One full verification (graphtty, `uv tool install`): level function, replayed, offline, judged working.
- Baking takes 17 minutes: 7.5 for the scripts (2 of them the App Installer), the rest EC2's snapshot of 40 GB.
  One bake in five ended at sbx's winget source (0x8a15000f) before that step fetched it again.
- A new instance answers ssh 65 to 90 s after it is launched (us-east-1: 115 to 150 s) and is a box 125 to 140 s
  after the start was asked for (us-east-1: 220 s). A pool member answers ssh in 20 s and is a box in 40 to 51 s
  (us-east-1: 61 to 71 s). The verification above took 383 s with two new instances, one of which waited 95 s
  for room in the account's vCPU quota; on the image before job.exe and relay.exe it took 318 s with a new
  instance and a pool member, 237 s with two pool members (us-east-1: 519 s and 256 s).
- A member's one boot takes 225 s. Reading one file after another it took ten minutes (WARM_READER has the
  figures); thirty-two readers, exempt from Defender's scan, read 54,000 files and 8.5 GB inside that.
- A box costs about US$0.21 an hour (the licence is US$0.088 of it; us-east-1: US$0.19); a stopped member,
  US$3.46 a month for its disk.
- A command of sbx's takes 0.3 to 0.6 s when the one before it ended a second or more ago, 0.5 s right after
  another, and 1.2 to 1.4 s as a box's first (a bare program over ssh: 0.13 to 0.16 s). With Windows PowerShell
  on both sides and the shell started when the command came, it took 1.1 to 1.5 s: in the verification above
  `graphtty graph.json` went from 1.5 s to 0.4 s.
- winget is 1.29.380 in the image (WIN_APPS has what was measured on the way). An instance of an image made
  this way still had it after fourteen minutes, with the Store's install service still disabled and
  `winget search --source winget` answering.

- The display image: baking takes 17 minutes (its own parts 15 s). Its limits test holds 40 of 40, the 32 above
  and the display's own: pickfit's screenshot is the 1280x800 desktop of a new instance; the session helper reads
  the box user's clipboard, runs as SYSTEM in the console session for the administrator and not at all for the
  box user; the box user cannot read the VNC server's settings, stop it, change the helper or the display's
  settings; the server refuses another password and listens on the loopback alone. A display box's own start adds
  6 s; a window listing takes 0.2 to 0.8 s, a screenshot 0.1 s per frame (1.2 s with the wait for the screen to
  settle).
- KeePassXC on the display image (the Opus agent): its portable .zip installed and its window counted; its own
  screen-capture protection kept the window out of every screenshot until it was launched with
  --allow-screencapture (gui_win says so in the launch). Then the operator created a database, added an entry
  named with the nonce and exported it to CSV, and the file check found the export: level function, replayed in
  a fresh box (the recorded clicks missed offline, the operating loop passed online), judged working, with the
  replay's recording (verify-keepassxc-20261117-155444-e224, 1,450 s, model US$1.32, box US$0.08). Two runs
  before it lost their replay: once the AWS session ended, once the box's ssh connection broke in the middle of
  a command (this host's public address changed four times that day).

What a run on this box does not see (2026-11-17):

- winget's msstore source: the service that installs from it is off (see WIN_APPS).
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import subprocess
import time
from collections.abc import Callable
from typing import Any

from pickfit.verify import gui_win
from pickfit.verify.box import BoxError, BoxLimits
from pickfit.verify.ec2_machine import (
    Ec2Instance,
    _code,
    _instance,
    _sleep,
    _tag,
    _tags,
    _wait,
    ec2_client,
    find_image,
)
from pickfit.verify.vbox_box import (
    CLEAR_PS_LOGS,
    HARDEN,
    HARDENED_CHECK,
    LSA_TYPE,
    PROVISION_SBX,
    PROVISION_USERS,
    RUN_SCRIPT,
)
from pickfit.verify.win_machine import ADMIN_USER, BOX_USER, MAKE_RULES, WinSshMachine
from pickfit.verify.windows_box import RELAY_EXE, WIN_HOME, WIN_PROBE_SCRIPT, WindowsBox, make_job, relay_input



def _b64_text(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


WIN_BASE_OWNER = "amazon"
WIN_BASE_NAME = "Windows_Server-2025-English-Full-Base-*"
WIN_MEMORY_MB = 6144  # the least a Windows box is given (VBoxBox's guest has the same)
WIN_DISK_GB = 40  # Windows and the tools take about 26 GB; the rest is the box user's
WIN_BAKE_TYPE = "m7i-flex.large"
WIN_BAKE_LIFETIME_S = 2 * 3600
WIN_WARM_LIFETIME_S = 25 * 60
MANIFEST_TAGS = ("product", "windows", "tools", "display")  # the image's tags pickfit:<name>, read back by every box
TOOLS = ("pwsh", "python", "uv", "pipx", "node", "npm", "git", "winget")

# The boot agent's own tasks for an instance of the image: no wallpaper, no SSM agent. The administrator's
# password is made new and random at every boot, and nobody reads it.
AGENT_CONFIG = """version: "1.0"
config:
  - stage: boot
    tasks:
      - task: extendRootPartition
  - stage: preReady
    tasks:
      - task: activateWindows
        inputs:
          activation:
            type: amazon
      - task: setDnsSuffix
        inputs:
          suffixes:
            - $REGION.ec2-utilities.amazonaws.com
      - task: setAdminAccount
        inputs:
          password:
            type: random
"""
# sshd as the image keeps it: the administrator by key, sbx by password (see win_machine), nobody else.
SSHD_CONFIG = """AuthorizedKeysFile	.ssh/authorized_keys
Subsystem	sftp	sftp-server.exe
AllowUsers administrator sbx
PasswordAuthentication no
MaxSessions 64
MaxStartups 64:30:128
Match User sbx
       PasswordAuthentication yes
       PubkeyAuthentication no
Match Group administrators
       AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys
"""

WIN_SYSTEM = r"""$ErrorActionPreference = 'Continue'
powercfg /hibernate off 2> $null
$wu = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
New-Item $wu -Force | Out-Null
Set-ItemProperty $wu NoAutoUpdate 1 -Type DWord
Stop-Service wuauserv -Force -ErrorAction SilentlyContinue
Set-Service wuauserv -StartupType Disabled
Set-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server' fDenyTSConnections 1 -Type DWord
foreach ($s in 'WinRM', 'AmazonSSMAgent') {
  Stop-Service $s -Force -ErrorAction SilentlyContinue
  Set-Service $s -StartupType Disabled -ErrorAction SilentlyContinue }
New-ItemProperty 'HKLM:\SOFTWARE\Microsoft\ServerManager' DoNotOpenServerManagerAtLogon -Value 1 -PropertyType DWord -Force | Out-Null
[IO.File]::WriteAllText('C:\ProgramData\Amazon\EC2Launch\config\agent-config.yml', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('@AGENT@')))
'system-ok'
"""
# The password is made here, on the instance, and is in no script: sbx's account, then the LSA secret Winlogon
# reads for the auto logon (no password in the registry).
WIN_SECRET = r"""$__pf_bytes = New-Object byte[] 24
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($__pf_bytes)
$__pf_secret = 'Pf1-' + [Convert]::ToBase64String($__pf_bytes).Replace('+', '-').Replace('/', '_')
$env:PF_SECRET = $__pf_secret
"""
WIN_AUTOLOGON = r"""
$rc = [PfLsa]::Store('DefaultPassword', $__pf_secret)
Remove-Variable __pf_secret, __pf_bytes
if ($rc -ne 0) { "lsa store failed: $rc"; exit 1 }
$wl = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
Remove-ItemProperty $wl DefaultPassword, AutoLogonCount -ErrorAction SilentlyContinue
Set-ItemProperty $wl AutoAdminLogon '1'
Set-ItemProperty $wl DefaultUserName 'sbx'
Set-ItemProperty $wl DefaultDomainName '.'
'logon-set'
"""
# The App Installer is in the image but belongs to nobody until a user registers it, and its package source is
# a package of its own: without it every winget command ends with 0x8a15000f (measured 2026-11-16).
WINGET_SOURCE = "https://cdn.winget.microsoft.com/cache/source2.msix"
WIN_WINGET = rf"""$ErrorActionPreference = 'Stop'
Add-AppxPackage -RegisterByFamilyName -MainPackage Microsoft.DesktopAppInstaller_8wekyb3d8bbwe
Add-AppxPackage -Path '{WINGET_SOURCE}'
$env:Path += ";$env:LOCALAPPDATA\Microsoft\WindowsApps"
"winget=$(winget --version)"
"""
WIN_TOOLS = r"""$ErrorActionPreference = 'Continue'
$env:Path += ";$env:LOCALAPPDATA\Microsoft\WindowsApps"
$common = '--exact', '--scope', 'machine', '--silent', '--source', 'winget', '--accept-package-agreements',
          '--accept-source-agreements', '--disable-interactivity'
foreach ($id in 'Git.Git', 'OpenJS.NodeJS.LTS') {
  winget install --id $id @common | Out-Null; "winget $id -> $LASTEXITCODE" }
winget install --id Python.Python.3.12 @common --override '/quiet InstallAllUsers=1 PrependPath=1 Include_test=0' | Out-Null
"winget Python.Python.3.12 -> $LASTEXITCODE"
& 'C:\Program Files\Python312\python.exe' -m pip install --no-input --disable-pip-version-check --no-warn-script-location uv pipx | Out-Null
"pip uv pipx -> $LASTEXITCODE"
$tag = (& curl.exe -sI https://github.com/PowerShell/PowerShell/releases/latest | Select-String 'location:.*/tag/(v[\d.]+)').Matches.Groups[1].Value
if (-not $tag) { 'no PowerShell release found'; exit 4 }
$zip = Join-Path $env:TEMP 'pwsh.zip'
& curl.exe -fsSL -o $zip "https://github.com/PowerShell/PowerShell/releases/download/$tag/PowerShell-$($tag.TrimStart('v'))-win-x64.zip"
if ($LASTEXITCODE) { "download failed: $tag"; exit 5 }
"pwsh_sha256=$((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower())"
$dir = 'C:\Program Files\PowerShell\7'
New-Item -ItemType Directory -Force $dir | Out-Null
Expand-Archive -Path $zip -DestinationPath $dir -Force
Remove-Item $zip -Force
$sig = Get-AuthenticodeSignature "$dir\pwsh.exe"
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
  "pwsh.exe is not signed by Microsoft ($($sig.Status))"; exit 6 }
"pwsh_signer=$($sig.SignerCertificate.Subject)"
$machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
if (($machine -split ';') -notcontains $dir) { [Environment]::SetEnvironmentVariable('Path', "$machine;$dir", 'Machine') }
[IO.File]::WriteAllText('C:\ProgramData\pickfit\pwsh.path', "$dir\pwsh.exe")
"pwsh_path=$dir\pwsh.exe"
"""
WIN_SSHD = r"""$ErrorActionPreference = 'Stop'
[IO.File]::WriteAllText('C:\ProgramData\ssh\sshd_config', [Text.Encoding]::ASCII.GetString([Convert]::FromBase64String('@CONFIG@')))
& "$env:SystemRoot\System32\OpenSSH\sshd.exe" -t
if ($LASTEXITCODE -ne 0) { 'sshd refuses its configuration'; exit 1 }
Set-Service sshd -StartupType Automatic
Restart-Service sshd -Force
'sshd-ok'
"""
# As sbx: winget for this user, then VBoxBox's own account of sbx's side (user-level bin directories on PATH, the
# versions the box's description gives). The source's package is fetched again when winget does not find it: one
# bake in five ended here with 0x8a15000f (measured 2026-11-17).
WIN_SBX = rf"""$ErrorActionPreference = 'Continue'
Add-AppxPackage -RegisterByFamilyName -MainPackage Microsoft.DesktopAppInstaller_8wekyb3d8bbwe
Add-AppxPackage -Path '{WINGET_SOURCE}'
""" + PROVISION_SBX + rf"""
foreach ($try in 1..4) {{
  & "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe" search --id jqlang.jq --exact --source winget --accept-source-agreements --disable-interactivity | Out-Null
  if ($LASTEXITCODE -eq 0) {{ break }}
  Start-Sleep 15
  Add-AppxPackage -Path '{WINGET_SOURCE}' }}
"winget_source=$LASTEXITCODE"
"""
# As sbx, through the image's task (windows_box.JOB_SOURCE), once it is logged on at the console: the proof that a
# box's commands will run there, with a desktop and with WMI answering, and the winget they will find, which
# must still answer from its own source with the Store's install service off.
WIN_DESK = r"""$os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
"desk=$((Get-Process -Id $PID).SessionId) interactive=$([Environment]::UserInteractive) wmi=$([bool]$os.Caption)"
"winget=$(winget --version)"
winget search --id jqlang.jq --exact --source winget --accept-source-agreements --disable-interactivity | Out-Null
"winget_search=$LASTEXITCODE"
"""
# As the administrator, once sbx is logged on at the console: the App Installer (winget) a person's PC has, and
# nothing left that replaces it later. Amazon's image has winget 1.9. On instances of an image some hours old,
# Windows replaced it by itself with the current one (1.29) 4.5 to 7 minutes after the start, in the middle of
# whatever ran (measured 2026-11-17 on four instances; the Store's policy, its own setting and disabling its scan
# tasks did not prevent it). On a machine just made it does not, however long one waits (the builder, 549 s; an
# instance of a fresh image, 468 s), and neither the MDM update scan, the Store's scan task nor UsoClient made it.
# So the bake installs it the way Microsoft documents for a Windows without the Store: Repair-WinGetPackageManager
# from its Microsoft.WinGet.Client module, for all users (88 s; it brought the same 1.29.380 Windows' own update
# had), and removes the module again. Then the Microsoft Store Install Service, which does the replacing, is
# disabled: with it off an instance kept its App Installer for the eleven minutes it was watched, past the minute
# the others lost theirs. What that costs: winget cannot install from its msstore source in a box; its own source
# (--source winget) does not use the service.
# The repair runs in a Windows PowerShell of its own: a session that has loaded the module cannot remove it.
WIN_REPAIR = r"""$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Install-PackageProvider -Name NuGet -Force | Out-Null
Install-Module -Name Microsoft.WinGet.Client -Force -Repository PSGallery -Scope AllUsers | Out-Null
"module=$((Get-Module -ListAvailable Microsoft.WinGet.Client | Select-Object -First 1).Version)"
Repair-WinGetPackageManager -AllUsers -Latest -Force
'repaired'
"""
WIN_APPS = r"""$ErrorActionPreference = 'Continue'
function Mine { (Get-AppxPackage -AllUsers Microsoft.DesktopAppInstaller | Where-Object {
    $_.PackageUserInformation | Where-Object { $_.UserSecurityId.Username -eq 'sbx' -and $_.InstallState -eq 'Installed' } } |
  Sort-Object { [version]$_.Version } | Select-Object -Last 1).Version }
function Top { (Get-AppxPackage -AllUsers Microsoft.DesktopAppInstaller | Sort-Object { [version]$_.Version } | Select-Object -Last 1).Version }
$was = Mine
$said = "Invoke-Expression ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('@REPAIR@')))" |
  & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command - 2>&1 | Out-String
$said.Trim()
if ($said -notmatch '(?m)^repaired\s*$') { 'the App Installer was not repaired'; exit 1 }
foreach ($i in 1..24) { if ((Mine) -and (Mine) -eq (Top)) { break }; Start-Sleep 5 }
Uninstall-Module Microsoft.WinGet.Client -AllVersions -Force -ErrorAction SilentlyContinue
"apps=$(Mine) was=$was top=$(Top) module_left=$(@(Get-Module -ListAvailable Microsoft.WinGet.Client).Count)"
Stop-Service InstallService -Force -ErrorAction SilentlyContinue
Set-Service InstallService -StartupType Disabled
"store=$((Get-Service InstallService).StartType)"
""".replace("@REPAIR@", _b64_text(WIN_REPAIR))
WIN_UPTIME = "\"boot=$([int]((Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime).TotalSeconds)\"\n"
WIN_CONSOLE = "$q = (quser 2> $null | Out-String); if ($q -match '(?m)^.?sbx\\s+console\\s.*Active') { 'console=sbx' } else { 'console=none' }\n"
WIN_FINAL = r"""$v = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
"product=$($v.ProductName)"
"build=$($v.CurrentBuild).$($v.UBR)"
"display=$($v.DisplayVersion)"
"license=$((cscript //nologo $env:SystemRoot\System32\slmgr.vbs /dli | Select-String 'License Status') -replace '.*: ','')"
"wu=$((Get-Service wuauserv).StartType)/$((Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU' -ErrorAction SilentlyContinue).NoAutoUpdate)"
"free_gb=$([int]((Get-Volume C).SizeRemaining / 1GB))"
"""
# The last command of a bake: the PowerShell logs empty, nothing of this boot's keys, sshd waiting for the next
# instance's boot script, and the boot agent as on an instance that never ran.
WIN_SEAL = CLEAR_PS_LOGS + r"""
Set-Service sshd -StartupType Manual
Remove-Item 'C:\ProgramData\ssh\ssh_host_*', 'C:\ProgramData\ssh\administrators_authorized_keys' -Force -ErrorAction SilentlyContinue
Remove-Item "$env:SystemRoot\System32\config\systemprofile\AppData\Local\Temp\EC2Launch*" -Recurse -Force -ErrorAction SilentlyContinue
& 'C:\Program Files\Amazon\EC2Launch\EC2Launch.exe' reset --clean | Out-Null
"reset=$LASTEXITCODE"
shutdown.exe /a 2> $null
'sealed'
"""
# What a pool member's one boot reads, most used first, and for how long at most. Every command starts Windows
# PowerShell and PowerShell 7; the tools and sbx's own files come next; Windows' own programs last.
WARM_ROOTS = (r"C:\ProgramData\pickfit", r"C:\Program Files\PowerShell", r"$env:SystemRoot\System32\WindowsPowerShell",
              r"$env:SystemRoot\System32\OpenSSH", r"$env:SystemRoot\Microsoft.NET\Framework64", r"C:\Program Files",
              r"C:\Users", r"$env:SystemRoot\System32", r"$env:SystemRoot\SysWOW64")
WARM_READ_S = 240
WARM_EXE = r"C:\ProgramData\pickfit\warm.exe"  # where sbx cannot write: see WIN_WARM
# The reader: the files under each root, thirty-two at a time, until all are read or the time is up. A new volume
# answers a first read slowly and many at once no slower (measured 2026-11-17 on a new instance: one file after
# another, 39 files and 1.4 MB a second; thirty-two at once, 263 files and 65 MB a second).
WARM_READER = r"""using System; using System.IO; using System.Threading; using System.Threading.Tasks; using System.Collections.Generic; using System.Diagnostics;
public static class PfWarm {
  public static int Main(string[] a) {
    var clock = Stopwatch.StartNew(); long limit = long.Parse(a[0]) * 1000; int threads = int.Parse(a[1]);
    ThreadPool.SetMinThreads(threads, threads);
    long bytes = 0; int files = 0;
    var options = new ParallelOptions { MaxDegreeOfParallelism = threads };
    for (int i = 2; i < a.Length && clock.ElapsedMilliseconds < limit; i++) {
      Parallel.ForEach(Walk(a[i]), options, (f, state) => {
        if (clock.ElapsedMilliseconds >= limit) { state.Stop(); return; }
        try { var buf = new byte[65536];
          using (var s = new FileStream(f, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 65536, FileOptions.SequentialScan)) {
            int k; while ((k = s.Read(buf, 0, buf.Length)) > 0) Interlocked.Add(ref bytes, k); }
          Interlocked.Increment(ref files); } catch (Exception) { } }); }
    Console.WriteLine("read " + files + " files, " + (bytes >> 20) + " MB in " + (clock.ElapsedMilliseconds / 1000) + " s");
    return 0; }
  static IEnumerable<string> Walk(string root) {
    var dirs = new Stack<string>(); dirs.Push(root);
    while (dirs.Count > 0) { var d = dirs.Pop(); string[] f = null, sub = null;
      try { if ((File.GetAttributes(d) & FileAttributes.ReparsePoint) != 0) continue; f = Directory.GetFiles(d); sub = Directory.GetDirectories(d); }
      catch (Exception) { continue; }
      foreach (var x in f) yield return x;
      foreach (var x in sub) dirs.Push(x); } }
}
"""
# A pool member's one boot, as SYSTEM: wait for sbx's logon at the console and let it settle, then read what a
# box's commands read (WARM_READER, built here into the harness directory). Defender scans every file a process
# opens for the first time, which held the reader to two thirds of what the volume gives; the reader alone is
# exempt while it runs, by its path, which only administrators can write, and the exemption and the reader are
# removed after it. The boot agent cannot be made to forget a boot it is still in (it writes its record when the
# script returns; measured 2026-11-17, a member reset from inside the script ran no user data at its next boot),
# so the rest is left to a task of its own: wait for the agent to end, reset it, remove what is left of this
# script, and shut down (which stops a member).
WIN_WARM = r"""shutdown.exe /s /f /t @LIFETIME@ /c pickfit-warm
$deadline = (Get-Date).AddSeconds(240)
while ((Get-Date) -lt $deadline -and -not ((quser 2> $null | Out-String) -match 'sbx\s+console')) { Start-Sleep 3 }
Start-Sleep 20
$exe = '@EXE@'
try {
  Add-Type -TypeDefinition @'
@READER@'@ -OutputAssembly $exe -OutputType ConsoleApplication
  Add-MpPreference -ExclusionProcess $exe -ErrorAction SilentlyContinue
  & $exe @SECONDS@ 32 @ROOTS@ | Out-Null
} catch { }
Remove-MpPreference -ExclusionProcess $exe -ErrorAction SilentlyContinue
Remove-Item $exe -Force -ErrorAction SilentlyContinue
$done = "$env:SystemRoot\Temp\pickfit-warm-done.ps1"
Set-Content -Path $done -Value @'
foreach ($i in 1..90) { if (-not (Get-Process EC2Launch -ErrorAction SilentlyContinue)) { break }; Start-Sleep 2 }
& 'C:\Program Files\Amazon\EC2Launch\EC2Launch.exe' reset | Out-Null
Get-ChildItem "$env:SystemRoot\System32\config\systemprofile\AppData\Local\Temp" -Filter UserScript.ps1 -Recurse -Force -ErrorAction SilentlyContinue |
  Remove-Item -Force -ErrorAction SilentlyContinue
schtasks.exe /Delete /TN pickfit-warm-done /F | Out-Null
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
shutdown.exe /a
shutdown.exe /s /f /t 0
'@
schtasks.exe /Create /TN pickfit-warm-done /RU SYSTEM /RL HIGHEST /SC ONCE /ST 23:59 /F `
  /TR "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $done" | Out-Null
schtasks.exe /Run /TN pickfit-warm-done | Out-Null
""".replace("@EXE@", WARM_EXE).replace("@READER@", WARM_READER).replace("@SECONDS@", str(WARM_READ_S)).replace(
    "@ROOTS@", " ".join(f'"{root}"' for root in WARM_ROOTS))
# As the administrator: the status line of an IMDSv2 token request ('' when nothing answers).
IMDS_PROBE = ("$c = New-Object Net.Sockets.TcpClient\n"
              "try { if ($c.ConnectAsync('169.254.169.254', 80).Wait(2000) -and $c.Connected) {\n"
              "  $s = $c.GetStream(); $s.ReadTimeout = 2000\n"
              "  $q = [Text.Encoding]::ASCII.GetBytes(\"PUT /latest/api/token HTTP/1.0`r`n"
              "X-aws-ec2-metadata-token-ttl-seconds: 60`r`n`r`n\")\n"
              "  $s.Write($q, 0, $q.Length); $b = New-Object byte[] 12; $n = $s.Read($b, 0, 12)\n"
              "  [Text.Encoding]::ASCII.GetString($b, 0, $n) } } catch { } finally { $c.Close() }\n")


_b64 = _b64_text


def _kv(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^(\w+)=(.*)$", text, re.M)}


def users_script() -> str:
    """sbx, the harness directory with run.ps1 and probe.ps1, and sbx's auto logon, in one script: the password
    it makes is in one process and nowhere else."""
    users = PROVISION_USERS.replace("{run}", _b64(RUN_SCRIPT)).replace("{probe}", _b64(WIN_PROBE_SCRIPT))
    return WIN_SECRET + users + LSA_TYPE + WIN_AUTOLOGON


def bake_steps(display: bool = False) -> dict[str, str]:
    """Every script a bake runs, by name. The image's name is a hash of them: changing one bakes a new image.
    display: the image with a desktop pickfit sees and drives (gui_win): its display's parts after the tools, and
    the box user's screen set once it is logged on."""
    shown = {"display": gui_win.MAKE_DISPLAY} if display else {}
    screen = {"screen": gui_win.SCREEN} if display else {}
    return {"system": WIN_SYSTEM.replace("@AGENT@", _b64(AGENT_CONFIG)), "users": users_script(), "rules": MAKE_RULES,
            "job": make_job(), "winget": WIN_WINGET, "tools": WIN_TOOLS, **shown,
            "sshd": WIN_SSHD.replace("@CONFIG@", _b64(SSHD_CONFIG)), "sbx": WIN_SBX, "apps": WIN_APPS, **screen,
            "desk": WIN_DESK, "harden": HARDEN, "check": HARDENED_CHECK, "final": WIN_FINAL, "seal": WIN_SEAL}


def win_image_name(display: bool = False) -> str:
    digest = hashlib.sha256((WIN_BASE_NAME + "\n".join(bake_steps(display).values())).encode()).hexdigest()[:10]
    return f"pickfit-win-server2025-{'gui-' if display else ''}{digest}"


def win_base_image(ec2: Any) -> dict[str, Any]:
    """Amazon's newest Windows Server image that WIN_BASE_NAME matches."""
    images = ec2.describe_images(Owners=[WIN_BASE_OWNER], Filters=[
        {"Name": "name", "Values": [WIN_BASE_NAME]}, {"Name": "state", "Values": ["available"]}])["Images"]
    if not images:
        raise BoxError(f"no AMI named {WIN_BASE_NAME} from Amazon in this region")
    return max(images, key=lambda i: i["CreationDate"])


def image_manifest(image: dict[str, Any]) -> dict[str, str]:
    """What a baked image says it holds, from its tags: product, windows, and each tool's version."""
    manifest = {name: _tag(image, f"pickfit:{name}") or "" for name in MANIFEST_TAGS}
    for pair in manifest.pop("tools", "").split(";"):
        if "=" in pair:
            manifest[pair.split("=", 1)[0]] = pair.split("=", 1)[1]
    return {key: value for key, value in manifest.items() if value}


class Ec2WinMachine(Ec2Instance, WinSshMachine):
    """An EC2 instance from pickfit's Windows AMI, behind pickfit's security groups."""

    platform = "windows"
    warm_boot_wait_s = 240

    def __init__(self, *, cores: float = 2, memory_mb: int = WIN_MEMORY_MB, lifetime_s: int,
                 tags: dict[str, str] | None = None, region: str | None = None, ec2: Any = None,
                 instance_type: str | None = None, usd_per_hour: float | None = None, control: str | None = None,
                 boot_image: dict[str, Any] | None = None, role: str = "box", display: bool = False,
                 log: Callable[[str], None] = print, popen: Callable[..., Any] = subprocess.Popen,
                 run: Callable[..., Any] = subprocess.run) -> None:
        WinSshMachine.__init__(self, cores=cores, memory_mb=memory_mb, lifetime_s=lifetime_s, log=log, popen=popen,
                               run=run)
        self.display = display
        self.image_name = win_image_name(display)
        self.manifest: dict[str, str] = {}
        self._init_ec2(tags=tags, region=region, ec2=ec2, instance_type=instance_type, usd_per_hour=usd_per_hour,
                       control=control, boot_image=boot_image, role=role)
        self._price()  # an unknown type or region fails here, not after a run that then has no cost

    def _size(self) -> tuple[float, int]:
        return self.cores, max(self.memory_mb, WIN_MEMORY_MB)  # the instance is the box: nothing runs next to it

    def _pool_size(self) -> tuple[float, int]:
        return 2, WIN_MEMORY_MB

    def _disk_gb(self) -> int:
        return WIN_DISK_GB

    def _ensure_image(self) -> dict[str, Any]:
        image = ensure_win_image(self.ec2, log=self.log, region=self.region, control=self.control,
                                 display=self.display)
        self.manifest = image_manifest(image)
        return image

    def wrap_user_data(self, script: str) -> str:
        return f"<powershell>\n{script}</powershell>\n"

    def _warm_user_data(self) -> str:
        return self.wrap_user_data(WIN_WARM.replace("@LIFETIME@", str(WIN_WARM_LIFETIME_S)))

    def _egress_open(self) -> bool:
        return self.egress_open()

    def _metadata_line(self) -> str:
        return self.admin(IMDS_PROBE, 20)[1].strip()

    def restart(self, log: Callable[[str], None]) -> None:
        """Restart Windows and come back as the administrator (a bake does, so sbx logs on at the console)."""
        self.admin("shutdown.exe /a 2> $null; shutdown.exe /r /f /t 2; 'restarting'", 60)
        _sleep(25)  # the old sshd still answers for a moment
        self._drop_connections((BOX_USER,))
        deadline = time.monotonic() + 600
        while True:
            self._connect(wait_s=600)
            up = _kv(self.admin(WIN_UPTIME, 60)[1]).get("boot", "")
            if up.isdigit() and int(up) < 300:
                break
            if time.monotonic() > deadline:
                raise BoxError(f"{self.machine_id} did not restart (up for {up}s)")
            self._drop_connections(())
            _sleep(10)
        self.admin(f"shutdown.exe /s /f /t {int(self.lifetime_s)} /d p:0:0 /c pickfit-lifetime", 60)
        log(f"ec2: {self.machine_id} restarted")


def bake_win_image(ec2: Any, *, log: Callable[[str], None] = print, region: str | None = None,
                   control: str | None = None, popen: Callable[..., Any] = subprocess.Popen,
                   run: Callable[..., Any] = subprocess.run, display: bool = False) -> dict[str, Any]:
    """Build the Windows AMI on a throwaway instance and return it as EC2 describes it. About 20 minutes."""
    name, steps = win_image_name(display), bake_steps(display)
    began = time.monotonic()
    builder = Ec2WinMachine(lifetime_s=WIN_BAKE_LIFETIME_S, region=region, ec2=ec2, instance_type=WIN_BAKE_TYPE,
                            control=control, boot_image=win_base_image(ec2), role="bake",
                            tags={"pickfit:image": name}, log=log, popen=popen, run=run)
    log(f"ec2: baking {name} from {builder.boot_image['Name']} (about 25 minutes)")  # type: ignore[index]
    builder.boot()
    try:
        def step(what: str, timeout_s: int, expect: str, user: str = ADMIN_USER) -> dict[str, str]:
            code, out, err, _ = builder.run_ps(user, steps[what], timeout_s)
            log(f"ec2: {name}: {what} -> {code} at {time.monotonic() - began:.0f}s")
            if expect not in out:
                raise BoxError(f"baking {name}: {what} failed ({code}): {(out + err).strip()[-800:]}")
            return _kv(out)

        step("system", 600, "system-ok")
        step("users", 300, "logon-set")
        step("rules", 300, "rules-made")
        step("job", 300, "job-made")
        step("winget", 900, "winget=v")
        tools = step("tools", 3600, "pwsh_path=")
        shown = step("display", 1200, "display-made") if display else {}
        step("sshd", 120, "sshd-ok")
        builder._box_password = builder.box_password()
        builder._connect(BOX_USER, wait_s=120)
        versions = step("sbx", 900, "winget=", user=BOX_USER)
        missing = [tool for tool in TOOLS if not versions.get(tool) or versions[tool] == "unavailable"]
        if missing or versions.get("winget_source") != "0":
            raise BoxError(f"baking {name}: sbx has no {', '.join(missing) or 'winget source'}: {versions}")
        builder.restart(log)
        _wait("sbx logging on at the console",
              lambda: "console=sbx" in builder.admin(WIN_CONSOLE, 60)[1], 600, 5)
        _sleep(30)  # the first logon's own work (the profile, the packaged apps) has the machine for a while
        apps = step("apps", 900, "apps=")
        if apps.get("apps", "").split(" ")[0] != apps.get("apps", "").split("top=")[-1].split(" ")[0]:
            raise BoxError(f"baking {name}: sbx does not have the newest App Installer on the machine ({apps})")
        if not apps.get("apps", "").endswith("module_left=0"):
            raise BoxError(f"baking {name}: the module that installed the App Installer is still there ({apps})")
        if apps.get("store") != "Disabled":
            raise BoxError(f"baking {name}: the Store's install service is still {apps.get('store')!r}")
        log(f"ec2: {name}: App Installer {apps['apps']} (Microsoft.WinGet.Client {apps.get('module', '?')})")

        def as_sbx(what: str, timeout_s: int) -> tuple[int | None, str, str]:
            code, out, err, _ = builder.run_exe(
                BOX_USER, RELAY_EXE, relay_input(steps[what], timeout_s, WIN_HOME, "bake", secrets.token_hex(8)),
                timeout_s + 180)
            log(f"ec2: {name}: {what} -> {code} at {time.monotonic() - began:.0f}s")
            return code, out, err

        if display:  # the box user's screen: the virtual display alone, at its size
            code, out, err = as_sbx("screen", 120)
            screen = _kv(out)
            if code != 0 or screen.get("screens") != f"1 primary={gui_win.SCREEN_W}x{gui_win.SCREEN_H}":
                raise BoxError(f"baking {name}: the box user's screen is not the virtual display alone: "
                               f"{(out + err).strip()[-400:]}")
        code, out, err = as_sbx("desk", 120)
        desk = _kv(out)
        if (code != 0 or not re.fullmatch(r"[1-9]\d* interactive=True wmi=True", desk.get("desk", ""))
                or not re.fullmatch(r"v[\d.]+", desk.get("winget", "")) or desk.get("winget_search") != "0"):
            raise BoxError(f"baking {name}: sbx's commands do not run at its desktop ({code}): {(out + err).strip()[-400:]}")
        versions["winget"] = desk["winget"]
        step("harden", 300, "hardened-ok")
        code, out, err, _ = builder.run_ps(ADMIN_USER, steps["check"], 180)
        if code != 0:
            raise BoxError(f"baking {name}: the hardened image fails its check: {(out + err).strip()[-400:]}")
        final = step("final", 300, "license=")
        # Automatic updates are off by policy (the /1). Windows Server 2025 keeps the update service itself from
        # being disabled (measured 2026-11-17: it stays Manual), so the service's own state is only recorded.
        if final.get("license") != "Licensed" or not final.get("wu", "").endswith("/1"):
            raise BoxError(f"baking {name}: not ready for an image: licence {final.get('license')!r}, "
                           f"Windows Update {final.get('wu')!r}")
        manifest = {"product": final.get("product", "Windows Server 2025"),
                    "windows": f"{final.get('display', '?')} (build {final.get('build', '?')})",
                    "tools": ";".join(f"{tool}={versions[tool]}" for tool in TOOLS)[:255],
                    **({"display": f"{gui_win.SCREEN_W}x{gui_win.SCREEN_H};vdd=25.7.23;"
                                   f"vnc={shown.get('vnc', '?').replace(', ', '.')}"}
                       if display else {})}
        log(f"ec2: {name}: {manifest['product']} {manifest['windows']}, {manifest['tools']}, "
            f"pwsh.zip sha256 {tools.get('pwsh_sha256', '?')[:16]}, Windows Update {final.get('wu')}, "
            f"{final.get('free_gb', '?')} GB free")
        step("seal", 300, "sealed")
        ec2.stop_instances(InstanceIds=[builder.machine_id])
        builder_id = str(builder.machine_id)
        _wait(f"builder {builder_id} stopping",
              lambda: _instance(ec2, builder_id).get("State", {}).get("Name") == "stopped", 900, 5)
        tags = {"pickfit": "verify", "pickfit:image": name, "pickfit:baked": time.strftime("%Y-%m-%d"),
                **{f"pickfit:{key}": value for key, value in manifest.items()}}
        try:
            made = ec2.create_image(InstanceId=builder.machine_id, Name=name,
                                    Description=f"pickfit Windows box: {manifest['product']} {manifest['windows']}"[:255],
                                    TagSpecifications=[_tags("image", tags), _tags("snapshot", tags)])
        except Exception as error:
            if _code(error) != "InvalidAMIName.Duplicate":  # another harness baked it meanwhile
                raise
            made = {}
        if made:
            def ready() -> bool:
                state = ec2.describe_images(ImageIds=[made["ImageId"]])["Images"][0].get("State")
                if state == "failed":
                    raise BoxError(f"AMI {name} failed to build")
                return state == "available"

            _wait(f"AMI {name} becoming available", ready, 60 * 60, 10)
    finally:
        builder.close()
    image = find_image(ec2, name)
    if image is None:
        raise BoxError(f"AMI {name} is not there after baking it")
    log(f"ec2: AMI {name} ({image['ImageId']}) ready in {time.monotonic() - began:.0f}s")
    return image


def ensure_win_image(ec2: Any | None = None, *, log: Callable[[str], None] = print, region: str | None = None,
                     control: str | None = None, display: bool = False) -> dict[str, Any]:
    """The Windows AMI (with a display: the one gui_win drives), baked if this account does not have it; call it
    before parallel boxes start."""
    ec2 = ec2 or ec2_client(region)
    return find_image(ec2, win_image_name(display)) or bake_win_image(ec2, log=log, region=region, control=control,
                                                                        display=display)


class Ec2WindowsBox(WindowsBox):
    """A Windows Server instance on EC2 driven like the other boxes: WindowsBox on an Ec2WinMachine."""

    def __init__(self, *, limits: BoxLimits = BoxLimits(), tags: dict[str, str] | None = None,
                 region: str | None = None, ec2: Any = None, control: str | None = None,
                 log: Callable[[str], None] = print, display: bool = False) -> None:
        machine = Ec2WinMachine(cores=limits.cpus, memory_mb=limits.memory_mb, lifetime_s=limits.lifetime_s,
                                tags=tags, region=region, ec2=ec2, control=control, display=display,
                                log=lambda line: self.log(line))
        super().__init__(machine, limits=limits, log=log, display=display)

    def start(self) -> None:
        if not self.started:  # the machine's size follows the box's limits, read when they are used
            lim = self.limits
            self.machine.cores, self.machine.memory_mb, self.machine.lifetime_s = lim.cpus, lim.memory_mb, lim.lifetime_s
        super().start()
        m = self.manifest
        if m:  # what the run records as its image: the Windows it ran on, then pickfit's AMI
            self.image = f"{m.get('product', 'Windows Server 2025')} {m.get('windows', '')}, EC2 {self.machine.image}"[:120]
