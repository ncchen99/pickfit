"""WindowsBox: the Box interface on one provider's fresh Windows VM (win_machine.WinSshMachine).

The Windows counterpart of LinuxBox: everything here happens inside the machine, through the two logins the
machine carries, so it is the same on every provider. ec2_windows.Ec2WindowsBox is this box on EC2. VBoxBox
(vbox_box.py) is the older Windows box, on VirtualBox on a PC; the guest side is the same on purpose, and this
module takes it from there: the harness directory and its scripts (run.ps1, which starts a command in
PowerShell 7, ends its process tree at the timeout and prints the exit code last), the box's settings, the
hardened check every box runs before a model command, and how commands, files and background processes are
written in PowerShell. What differs is how a command gets in (VBoxManage there, SSH here) and where the
network is cut (a router VM there, the provider and the machine's firewall here).

- Model commands run as sbx, a standard user, in PowerShell 7, in sbx's own session at the machine's console:
  the one Windows logs it on to by itself, with a desktop, as a person's programs run. An SSH session is a logon
  over the network instead: no desktop, WMI refuses the user (measured 2026-11-17: Get-CimInstance, "Access
  denied"), and sshd ends every process of a command when the command returns. So the SSH side of a command
  only relays. In sbx's session at the console a job.exe waits on a named pipe, with the command's shell already
  started; the image's task starts it there, as sbx with the token of its console logon. relay.exe, which sshd
  starts, connects, hands the command over that pipe, copies two pipes of its own to its stdout and stderr as the
  bytes arrive, and ends with the exit code the first pipe brings back. job.exe passes the command to its shell
  (PowerShell 7, with an empty stdin), ends the shell's process tree at the timeout or when the relay is gone,
  reports the exit code, and has the next job.exe started. Nothing of a command is on a command line or in a
  file. Measured 2026-11-17 from Taiwan on an instance in Taipei: WMI and DPAPI answer, the token is the
  interactive one (S-1-5-4), and a command takes 0.3 s when the last one ended a second or more before and 0.5 s
  right after another (a bare program over ssh: 0.13 s). As a script for Windows PowerShell at both ends, with the
  shell started when the command came, it took 1.1 to 1.5 s.
- Over SSH a Windows exit code arrives modulo 256, so the last line carries the real one and the host takes it
  only when it agrees with what SSH said.
- The harness's own checks run as the administrator in Windows PowerShell 5.1, in the harness directory, straight
  over SSH through run.ps1: the administrator has no session at the console, and WMI answers it.
- A process a command leaves behind stays, as on a person's PC; run_background starts one with its output in a
  log. Without a display nobody sees the desktop. A box made with display=True (an image that has one, see
  gui_win) shows pickfit its screen over VNC and launches and operates GUI apps there (gui_win.launch).
- Windows has no per-user process, file-size or memory cap; the VM's own RAM and disk are the caps.
- Containment is checked, never assumed: at start and after every change the box user's probe must find the
  link-local addresses closed and the internet as the mode says (set_network), and validate_containment() adds
  the controls for the limits test, among them a connection the box user holds open across the cut.
"""

from __future__ import annotations

import base64
import re
import secrets
import time
from collections.abc import Callable
from typing import Any

from pickfit.verify import gui_win
from pickfit.verify.box import HOST_GRACE_S, Box, BoxError, BoxLimits, ExecResult
from pickfit.verify.vbox_box import (
    ADMIN_USER,
    HARDENED_CHECK,
    HARNESS_DIR,
    PROBE_LINE,
    PROBE_PS1,
    PROBE_SCRIPT,
    PUBLIC_URL,
    RUN_PS1,
    SENTINEL,
    WIN_ENV,
    WIN_HOME,
    WIN_USER,
    WIN_WORKDIR,
    VBoxBox,
    encode_ps,
    ps_quote,
    with_exit_code,
)
from pickfit.verify.win_machine import WinSshMachine

JOB_EXE = HARNESS_DIR + r"\job.exe"  # waits in the box user's session at the console for one command
RELAY_EXE = HARNESS_DIR + r"\relay.exe"  # the SSH side of a box user's command
JOB_TASK = "pickfit-run"  # the image's task: job.exe as the box user, in its session at the console
JOB_PIPE = "pickfit-job"  # where a waiting job.exe listens; a command's own pipes are pickfit-<id>-o and -e
JOB_FIRST_MS = 500  # how long the relay looks for a job.exe that waits or is on its way before it starts one
JOB_START_S = 60  # from asking the Task Scheduler to a job.exe that answers (the first, on a machine just up)
JOB_IDLE_S = 600  # a waiting job.exe nobody came for ends
NOT_STARTED_EXIT = 125  # the relay's exit code when the command never started
# Both programs are C# 5, which the compiler Windows carries takes, and are built when the image is made (MAKE_JOB).
# What they share: UTF-8 without a mark, and asking the Task Scheduler for another job.exe.
_SHARED = r"""  static readonly UTF8Encoding Utf8 = new UTF8Encoding(false);
  static void StartJob() {
    Type t = Type.GetTypeFromProgID("Schedule.Service"); object s = Activator.CreateInstance(t);
    t.InvokeMember("Connect", BindingFlags.InvokeMethod, null, s, new object[0]);
    object folder = t.InvokeMember("GetFolder", BindingFlags.InvokeMethod, null, s, new object[] { "\\" });
    object task = folder.GetType().InvokeMember("GetTask", BindingFlags.InvokeMethod, null, folder, new object[] { "@TASK@" });
    task.GetType().InvokeMember("Run", BindingFlags.InvokeMethod, null, task, new object[] { null }); }
"""
# What the command's shell runs first: PowerShell 7 is started with job.exe and waits on a pipe of its job's for
# what to run, so a command does not wait for it to start (measured 2026-11-17: 0.3 s). Output as UTF-8; then
# the lines the relay sent: the box's settings, the directory, the command as run.ps1 takes it.
JOB_BOOT = ("[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
            "$__pf_c=[IO.Pipes.NamedPipeClientStream]::new('.',$env:PF_BOOT,'In');Remove-Item env:PF_BOOT;"
            "$__pf_c.Connect();$__pf_r=[IO.StreamReader]::new($__pf_c);"
            "while(($__pf_l=$__pf_r.ReadLine()) -ne 'go'){if($null -eq $__pf_l){exit 125};"
            "$__pf_n,$__pf_v=$__pf_l -split '=',2;"
            "$__pf_v=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($__pf_v));"
            "if($__pf_n -eq 'enc'){$__pf=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($__pf_v))}"
            "elseif($__pf_n -ne 'cwd'){Set-Item -LiteralPath $__pf_n -Value $__pf_v}"
            "elseif(Test-Path -LiteralPath $__pf_v -PathType Container){Set-Location -LiteralPath $__pf_v;"
            "[Environment]::CurrentDirectory=$__pf_v}"
            "else{[Console]::Error.WriteLine('pickfit: cannot start pwsh: no directory '+$__pf_v);exit 127}};"
            "$__pf_c.Dispose();Remove-Variable __pf_c,__pf_r,__pf_l,__pf_n,__pf_v;Invoke-Expression $__pf")
assert '"' not in JOB_BOOT and "\\" not in JOB_BOOT  # it is one argument of a command line, inside a C# string
# Runs in the box user's session at the console, started by the Task Scheduler, and waits there for one command:
# the relay (RELAY_SOURCE) connects to its pipe, hands the command over, and gets the exit code back on it; stdout
# and stderr go down two pipes the relay made for this command. It has no window. The command's shell is started
# at once (JOB_BOOT) with the environment Windows would give a process of this user now (CreateEnvironmentBlock:
# what the registry holds, a PATH an installer just added). When the command comes job.exe asks Windows again; if
# the answer has changed, or the shell is gone, it says so and ends, and the relay takes another. When its command
# has ended it has the Task Scheduler start the next job.exe, so a command seldom waits for one. It ends the
# shell's process tree at the timeout or when the relay is gone. The pipes are asynchronous at both ends, or a
# read that waits would hold a write back. (To 2026-11-17 this was a script for Windows PowerShell, which took
# 0.7 s to start and compared the registry's variables with what it had read 0.7 s after its own environment was
# made: a command that came in between could get a shell without the PATH the command before it had set.)
JOB_SOURCE = r"""using System; using System.Collections.Generic; using System.Diagnostics; using System.IO; using System.IO.Pipes; using System.Reflection; using System.Runtime.InteropServices; using System.Security.Principal; using System.Text; using System.Threading; using System.Threading.Tasks;
public static class PfJob {
@SHARED@  [DllImport("userenv.dll", SetLastError = true)] static extern bool CreateEnvironmentBlock(out IntPtr env, IntPtr token, bool inherit);
  [DllImport("userenv.dll")] static extern bool DestroyEnvironmentBlock(IntPtr env);
  static SortedDictionary<string, string> FreshEnv() {
    IntPtr env; var found = new SortedDictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    using (var me = WindowsIdentity.GetCurrent()) { if (!CreateEnvironmentBlock(out env, me.Token, false)) throw new Exception("no environment block (" + Marshal.GetLastWin32Error() + ")"); }
    try { for (IntPtr at = env; ; ) { string pair = Marshal.PtrToStringUni(at); if (pair.Length == 0) break;
        int eq = pair.IndexOf('=', 1); if (eq > 0) found[pair.Substring(0, eq)] = pair.Substring(eq + 1);
        at = IntPtr.Add(at, (pair.Length + 1) * 2); } }
    finally { DestroyEnvironmentBlock(env); }
    return found; }
  static string Flat(SortedDictionary<string, string> env) { var t = new StringBuilder(); foreach (var pair in env) t.Append(pair.Key).Append('=').Append(pair.Value).Append('\n'); return t.ToString(); }
  static string D(string value) { return Utf8.GetString(Convert.FromBase64String(value)); }
  static void EndTree(Process p) {
    if (p == null || p.HasExited) return;
    try { var kill = Process.Start(new ProcessStartInfo("taskkill.exe", "/T /F /PID " + p.Id) { UseShellExecute = false, CreateNoWindow = true }); kill.WaitForExit(15000); } catch (Exception) { } }
  static void Tell(StreamWriter writer, NamedPipeServerStream ctl, string line) { try { writer.Write(line + "\n"); writer.Flush(); ctl.WaitForPipeDrain(); } catch (Exception) { } }
  public static int Main() { try { return Run(); } catch (Exception) { return 1; } }
  static int Run() {
    var env = FreshEnv(); string made = Flat(env), why = "", boot = "pickfit-boot-" + Process.GetCurrentProcess().Id;
    var feed = new NamedPipeServerStream(boot, PipeDirection.Out, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous, 65536, 65536);
    var fed = feed.WaitForConnectionAsync();
    Process p = null;
    try {
      var psi = new ProcessStartInfo(File.ReadAllText("C:\\ProgramData\\pickfit\\pwsh.path").Trim(),
                                     "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command \"@BOOT@\"");
      psi.UseShellExecute = false; psi.CreateNoWindow = true; psi.WorkingDirectory = env["USERPROFILE"];
      psi.RedirectStandardInput = true; psi.RedirectStandardOutput = true; psi.RedirectStandardError = true;
      foreach (var pair in env) psi.Environment[pair.Key] = pair.Value;
      psi.Environment["PF_BOOT"] = boot;
      p = Process.Start(psi); p.StandardInput.Close();
    } catch (Exception e) { why = e.Message; p = null; }
    var ctl = new NamedPipeServerStream("@PIPE@", PipeDirection.InOut, 254, PipeTransmissionMode.Byte, PipeOptions.Asynchronous, 65536, 65536);
    if (!ctl.WaitForConnectionAsync().Wait(@IDLE@000)) { EndTree(p); return 0; }
    var reader = new StreamReader(ctl, Utf8); var writer = new StreamWriter(ctl, Utf8);
    if ((p != null && p.HasExited) || Flat(FreshEnv()) != made) { EndTree(p); Tell(writer, ctl, "stale"); return 0; }
    writer.Write("ready\n"); writer.Flush();
    string id = null, line; int timeout = 0; var hand = new StringBuilder();
    while ((line = reader.ReadLine()) != null && line != "go") {
      int eq = line.IndexOf('='); if (eq < 1) continue;
      string name = line.Substring(0, eq), value = line.Substring(eq + 1);
      if (name == "id") id = D(value); else if (name == "timeout") timeout = int.Parse(D(value)); else hand.Append(line).Append('\n'); }
    if (line != "go" || id == null) { EndTree(p); return 3; }
    var o = new NamedPipeClientStream(".", "pickfit-" + id + "-o", PipeDirection.Out, PipeOptions.Asynchronous);
    var e2 = new NamedPipeClientStream(".", "pickfit-" + id + "-e", PipeDirection.Out, PipeOptions.Asynchronous);
    o.Connect(10000); e2.Connect(10000);
    if (p != null && !fed.Wait(20000)) { why = "its shell did not come for the command"; EndTree(p); p = null; }
    if (p == null) {
      var m = Utf8.GetBytes("pickfit: cannot start pwsh: " + why + "\n"); e2.Write(m, 0, m.Length); e2.Flush();
      Tell(writer, ctl, "rc=127"); return 0; }
    var copy = new Task[] { p.StandardOutput.BaseStream.CopyToAsync(o, 8192), p.StandardError.BaseStream.CopyToAsync(e2, 8192) };
    var h = Utf8.GetBytes(hand.ToString() + "go\n");
    try { feed.Write(h, 0, h.Length); feed.Flush(); } catch (Exception) { }
    var gone = reader.ReadLineAsync();  // the relay says nothing more: this ends when it is no longer there
    var deadline = DateTime.UtcNow.AddSeconds(timeout); int rc = 0; bool ended = false;
    while (!p.WaitForExit(100)) {
      if (gone.IsCompleted) { EndTree(p); rc = -1; ended = true; break; }
      if (DateTime.UtcNow >= deadline) { EndTree(p); rc = 137; ended = true; break; } }
    if (!ended) rc = p.ExitCode;
    // What the command wrote is copied first; something it started may hold the pipes open, and is not waited for.
    try { Task.WaitAll(copy, 3000); } catch (Exception) { }
    try { o.Dispose(); e2.Dispose(); } catch (Exception) { }
    Tell(writer, ctl, "rc=" + rc);
    try { StartJob(); } catch (Exception) { }
    return 0; }
}
""".replace("@SHARED@", _SHARED).replace("@BOOT@", JOB_BOOT).replace("@PIPE@", JOB_PIPE).replace(
    "@IDLE@", str(JOB_IDLE_S)).replace("@TASK@", JOB_TASK)
# The task, as the Task Scheduler keeps it. Any number at once; no time limit of its own (job.exe has the
# command's); normal priority (a task's default is below normal, and what it starts inherits that).
JOB_TASK_XML = rf"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>pickfit: one command of the box user, in its session at the console</Description></RegistrationInfo>
  <Principals><Principal id="Author"><UserId>@SID@</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>Parallel</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>4</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{JOB_EXE}</Command>
    </Exec>
  </Actions>
</Task>
"""
# As the administrator, when the image is made: job.exe and relay.exe next to run.ps1, built here from their
# sources by the compiler Windows carries (the box user may read and run them, not change them; job.exe is a
# program without a console, so nothing of it shows on the desktop), and the task, which the box user may read
# and run and nobody but administrators may change.
MAKE_JOB = rf"""$ErrorActionPreference = 'Stop'
foreach ($build in @(@('{JOB_EXE}', '@JOB@', 'WindowsApplication'), @('{RELAY_EXE}', '@RELAY@', 'ConsoleApplication'))) {{
  Remove-Item $build[0] -Force -ErrorAction SilentlyContinue
  Add-Type -TypeDefinition ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($build[1]))) `
    -OutputAssembly $build[0] -OutputType $build[2] -ReferencedAssemblies System.Core
  icacls.exe $build[0] /reset | Out-Null }}
$sid = (Get-LocalUser {WIN_USER}).SID.Value
$xml = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('@XML@')).Replace('@SID@', $sid)
$sched = New-Object -ComObject Schedule.Service; $sched.Connect()
$null = $sched.GetFolder('\').RegisterTask('{JOB_TASK}', $xml, 6, $null, $null, 3, "D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FRFX;;;$sid)")
'job-made'
"""
# As the administrator, at every start: the two programs and the task are the image's, and the box user cannot
# change any (on the task it may read and run: Windows adds a read entry of its own for the user a task runs as).
# The task's own proof is the first command.
JOB_CHECK = r"""$bad = @()
foreach ($f in '@JOB@', '@RELAY@') {
  if (-not (Test-Path $f)) { $bad += "$(Split-Path -Leaf $f) is missing"; continue }
  foreach ($a in (Get-Acl $f).Access) {
    if ($a.IdentityReference.Value -match 'sbx|Users|Everyone|Authenticated' -and $a.AccessControlType -eq 'Allow' -and
        $a.FileSystemRights.ToString() -match 'Write|Modify|FullControl|ChangePermissions|TakeOwnership|Delete') {
      $bad += "$($a.IdentityReference.Value) can change $(Split-Path -Leaf $f)" } } }
try {
  $sched = New-Object -ComObject Schedule.Service; $sched.Connect()
  $task = $sched.GetFolder('\').GetTask('@TASK@')
  $exec = ([xml]$task.Xml).Task.Actions.Exec
  if (-not $task.Enabled -or $exec.Command -ne '@JOB@' -or $exec.Arguments) { $bad += "the task runs $($exec.Command) $($exec.Arguments)" }
  $sid = (Get-LocalUser @USER@).SID.Value
  $sd = $task.GetSecurityDescriptor(4)
  $runs = $false
  foreach ($m in [regex]::Matches($sd, '\(([^)]*)\)')) {
    $ace = $m.Groups[1].Value -split ';'
    if ($ace[0] -eq 'A' -and $ace[5] -in 'SY', 'BA') { continue }
    if ($ace[0] -eq 'A' -and $ace[5] -eq $sid -and $ace[2] -in 'FR', 'FX', 'FRFX', '0x120089', '0x1200a0', '0x1200a9') {
      if ($ace[2] -ne 'FR' -and $ace[2] -ne '0x120089') { $runs = $true }
      continue }
    $bad += "the task's access is $sd"; break }
  if (-not $runs) { $bad += "the box user may not run the task ($sd)" }
} catch { $bad += "the task @TASK@ cannot be read: $($_.Exception.Message)" }
if ($bad) { 'job-bad: ' + ($bad -join '; ') } else { 'job-ok' }
""".replace("@JOB@", JOB_EXE).replace("@RELAY@", RELAY_EXE).replace("@TASK@", JOB_TASK).replace("@USER@", WIN_USER)
# The SSH side of a box user's command: relay.exe, which sshd starts by its path, the same line every time. The
# command comes on its stdin as lines: nonce=<the exit-code line's>, then what job.exe is to have, down to "go".
# It takes a job.exe that waits, giving one that is on its way a moment, or has the Task Scheduler start one; one
# that says its environment is old is passed over. It asks for the pipe in short tries: .NET's own wait for a pipe
# that is not there yet spins a core. A program and not a script because Windows PowerShell takes 0.3 s to start
# (measured 2026-11-17; the script it replaced did the same, line for line).
# Its stdin, stdout and stderr are the handles sshd gave it, as files: through .NET's Console class one start in
# six never saw its stdin (measured 2026-11-17, 5 of 30 with Console.OpenStandardInput, 0 of 60 this way).
RELAY_SOURCE = r"""using System; using System.Diagnostics; using System.IO; using System.IO.Pipes; using System.Reflection; using System.Runtime.InteropServices; using System.Text; using System.Threading; using System.Threading.Tasks; using Microsoft.Win32.SafeHandles;
public static class PfRelay {
@SHARED@  [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int which);
  static FileStream Std(int which, FileAccess access) { return new FileStream(new SafeFileHandle(GetStdHandle(which), false), access, access == FileAccess.Read ? 4096 : 1, false); }
  static void Say(Stream to, string text) { var b = Utf8.GetBytes(text + "\r\n"); to.Write(b, 0, b.Length); to.Flush(); }
  public static int Main() {
    Stream stdin = Std(-10, FileAccess.Read), stdout = Std(-11, FileAccess.Write), stderr = Std(-12, FileAccess.Write);
    string nonce = "", id = "", line; var spec = new StringBuilder();
    NamedPipeServerStream po, pe; StreamReader r = null;
    try {
      var input = new StreamReader(stdin, Utf8);
      while ((line = input.ReadLine()) != null) {
        if (line.StartsWith("nonce=")) { nonce = line.Substring(6); continue; }
        if (line.StartsWith("id=")) id = Utf8.GetString(Convert.FromBase64String(line.Substring(3)));
        spec.Append(line).Append('\n');
        if (line == "go") break; }
      if (id.Length == 0 || nonce.Length == 0 || line != "go") throw new Exception("no command came on stdin");
      po = new NamedPipeServerStream("pickfit-" + id + "-o", PipeDirection.In, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous, 65536, 65536);
      pe = new NamedPipeServerStream("pickfit-" + id + "-e", PipeDirection.In, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous, 65536, 65536);
      var waits = new Task[] { po.WaitForConnectionAsync(), pe.WaitForConnectionAsync() };
      NamedPipeClientStream ctl = null; bool asked = false; var clock = Stopwatch.StartNew(); long until = @FIRST@;
      while (ctl == null) {
        var c = new NamedPipeClientStream(".", "@PIPE@", PipeDirection.InOut, PipeOptions.Asynchronous);
        string hello = "none";
        try { c.Connect(1); r = new StreamReader(c, Utf8); hello = r.ReadLine(); } catch (Exception) { }
        if (hello == "ready") { ctl = c; break; }
        c.Dispose();
        if (hello == "none" && clock.ElapsedMilliseconds < until) { Thread.Sleep(30); continue; }
        if (asked && hello == "none") throw new Exception("no job process answered in @START@ s");
        if (!asked) { StartJob(); asked = true; clock.Restart(); until = @START@000; } }
      var w = new StreamWriter(ctl, Utf8); w.Write(spec.ToString()); w.Flush();
      if (!Task.WaitAll(waits, 15000)) throw new Exception("the job process did not open the output pipes");
    } catch (Exception e) {
      var cause = e is TargetInvocationException && e.InnerException != null ? e.InnerException : e;
      Say(stderr, "pickfit: the command could not be started in the box user's session at the console: " + cause.Message);
      return @NOTSTARTED@; }
    var copy = new Task[] { po.CopyToAsync(stdout, 8192), pe.CopyToAsync(stderr, 8192) };
    string last = null; int rc;
    try { last = r.ReadLine(); } catch (Exception) { }
    try { Task.WaitAll(copy, 5000); } catch (Exception) { }
    stdout.Flush(); stderr.Flush();
    if (last == null || !last.StartsWith("rc=") || !int.TryParse(last.Substring(3), out rc)) {
      Say(stderr, "pickfit: the command's session ended without its exit code"); return 1; }
    Say(stdout, "\n@SENTINEL@" + nonce + "=" + rc);
    return rc; }
}
""".replace("@SHARED@", _SHARED).replace("@TASK@", JOB_TASK).replace("@PIPE@", JOB_PIPE).replace(
    "@FIRST@", str(JOB_FIRST_MS)).replace("@START@", str(JOB_START_S)).replace(
    "@NOTSTARTED@", str(NOT_STARTED_EXIT)).replace("@SENTINEL@", SENTINEL)
WRITE_CHUNK = 96 * 1024  # bytes of a file per command: the script that carries them stays well under a megabyte
PROBE_NAME = "pypi.org"  # resolved by the box user's probe: online it must, offline it must not
# probe.ps1 as VBoxBox installs it, with one more question: does a name resolve? The box user asks the system's
# resolver, as any program of its would.
_PROBE_PARAMS = "[string]$Url = '')"
assert _PROBE_PARAMS in PROBE_SCRIPT
WIN_PROBE_SCRIPT = PROBE_SCRIPT.replace(_PROBE_PARAMS, "[string]$Url = '', [string]$Dns = '')", 1) + (
    'if ($Dns) { try { $null = [Net.Dns]::GetHostAddresses($Dns); "probe dns=resolved" } '
    'catch { "probe dns=failed" } }\n')
# Never reachable for the box user: the cloud's metadata address, the other services clouds put on link-local
# addresses (a resolver, a licence server), and a private address.
MUST_NOT_OPEN = {"metadata": "169.254.169.254:80", "linklocal_dns": "169.254.169.253:53",
                 "linklocal_kms": "169.254.169.250:1688", "private": "10.255.255.1:80"}
INTERNET = "1.1.1.1:443"
REACHED = ("open", "refused")  # the packet arrived; anything else (timeout, unreachable) means it did not
# The box user holds a connection open, waits for a file, then asks over that connection and writes what came
# back. Started online; the file is made after the cut (or before it, as the control).
HOLD_SCRIPT = r"""$c = New-Object Net.Sockets.TcpClient
$c.Connect('1.1.1.1', 80)
Set-Content -Path "$HOME\.pickfit-bg\@TAG@.held" -Value 'held'
foreach ($i in 1..240) { if (Test-Path "$HOME\.pickfit-bg\@TAG@.go") { break }; Start-Sleep -Milliseconds 500 }
try {
  $s = $c.GetStream(); $s.ReadTimeout = 6000; $s.WriteTimeout = 6000
  $q = [Text.Encoding]::ASCII.GetBytes("GET /cdn-cgi/trace HTTP/1.1`r`nHost: 1.1.1.1`r`nConnection: close`r`n`r`n")
  $s.Write($q, 0, $q.Length); $b = New-Object byte[] 256; $n = $s.Read($b, 0, 256)
  $r = "answered $n"
} catch { $r = 'nothing' }
Set-Content -Path "$HOME\.pickfit-bg\@TAG@.result" -Value $r
"""


def read_sentinel(stdout: str, nonce: str, ssh_code: int | None) -> tuple[str, int | None, str | None]:
    """(stdout without run.ps1's exit-code line, the exit code or None, a warning or None). The LAST line for this
    nonce counts, and only when its code, modulo 256, is what SSH reported: otherwise something in the box
    printed it."""
    matches = list(re.finditer(rf"^{SENTINEL}{re.escape(nonce)}=(-?\d+)\r?$", stdout, re.M))
    if not matches:
        return stdout, None, None
    last = matches[-1]
    code = int(last.group(1))
    head = stdout[:last.start()]  # run.ps1 starts the line with a newline of its own
    head = head[:-2] if head.endswith("\r\n") else head[:-1] if head.endswith("\n") else head
    cleaned = head + stdout[last.end():].lstrip("\r\n")
    if ssh_code is None or code & 0xFF != ssh_code:
        return cleaned, None, (f"[pickfit: the exit-code line said {code} but the session ended with {ssh_code}; "
                               "not trusted]")
    return cleaned, code, None


def relay_input(command: str, timeout_s: int, cwd: str, nonce: str, job_id: str) -> bytes:
    """What relay.exe reads for one command of the box user's: the nonce its exit-code line carries, then the lines
    it sends down the pipe to job.exe (the name of this command's output pipes, the timeout, the directory, the
    box's settings, the command as run.ps1 takes it), each value in base64."""
    def b64(text: str) -> str:
        return base64.b64encode(text.encode()).decode()

    spec = [f"nonce={nonce}", f"id={b64(job_id)}", f"timeout={b64(str(int(timeout_s)))}", f"cwd={b64(cwd)}",
            *(f"env:{key}={b64(value)}" for key, value in WIN_ENV.items()),
            f"enc={b64(encode_ps(with_exit_code(command)))}", "go"]
    return ("\n".join(spec) + "\n").encode()


def make_job() -> str:
    """MAKE_JOB with the two programs' sources and the task in it: what an image's build runs as the
    administrator."""
    def b64(text: str) -> str:
        return base64.b64encode(text.encode()).decode()

    return MAKE_JOB.replace("@JOB@", b64(JOB_SOURCE)).replace("@RELAY@", b64(RELAY_SOURCE)).replace(
        "@XML@", b64(JOB_TASK_XML))


class WindowsBox(Box):
    """A provider's Windows VM driven like the other boxes."""

    runner = "windows"
    os = "windows"
    arch = "x86_64"
    home = WIN_HOME
    workdir = WIN_WORKDIR
    kind = "Windows virtual machine"
    shell = "pwsh"
    user_rule = VBoxBox.user_rule
    detach = ""  # run_background is PowerShell here; see background()

    harness_python = r"C:\Program Files\Python312\python.exe"  # the image's, which the box user cannot change

    def __init__(self, machine: WinSshMachine, *, limits: BoxLimits = BoxLimits(),
                 log: Callable[[str], None] = print, display: bool = False) -> None:
        self.machine = machine
        self.display = "vnc" if display else None  # the desktop, seen and driven over VNC (gui_win)
        self.session: dict[str, list[str]] | None = None  # the box user's desktop session at the start
        self.user_sid: str | None = None
        self.vnc_password: str | None = None  # made by the host for this box; only its stored form goes to it
        self._screen: Any = None
        self.limits = limits
        self.runner = f"{machine.provider}-windows"
        self.image = machine.image
        self.log = log
        self.manifest: dict[str, str] = {}  # what the image says it holds: Windows' build, the tools' versions
        self.started = False
        self.start_s: float | None = None
        self.network_enabled = True

    def describe(self) -> str:
        m = self.manifest
        tools = ", ".join(f"{k} {m[k]}" for k in ("python", "uv", "pipx", "node", "npm", "git", "winget") if m.get(k))
        return (f"Box: {m.get('product', 'Windows Server 2025')} {m.get('windows', '')} {self.arch} virtual "
                f"machine (a server edition of Windows, not Windows 11), user {WIN_USER} (standard user, not an "
                f"administrator, no UAC elevation), USERPROFILE={self.home}, work dir {self.workdir}. Commands run "
                f"in PowerShell 7 (pwsh {m.get('pwsh', '7')}): use PowerShell syntax (&& and || chain as in bash; "
                "$env:NAME for variables; here-strings @' '@ for files). "
                f"Installed: {tools}; curl.exe, tar.exe. Each command runs in a new shell with the environment "
                "Windows has at that moment, so a PATH entry an installer adds is there from the next command on; "
                "to use it within the same command: $env:Path = [Environment]::GetEnvironmentVariable('Path',"
                "'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User'). winget installs from "
                "its own source (--source winget); the Microsoft Store source is off in this box. Network: on. No "
                "API keys, no accounts. " + (
                    f"A desktop ({gui_win.SCREEN_W}x{gui_win.SCREEN_H}) where {WIN_USER} is logged in: start GUI apps "
                    "with launch_gui." if self.display else
                    "Commands run in the user's own desktop session, but nobody sees the screen: a window that opens "
                    "cannot be looked at or clicked."))

    # -- lifecycle

    def start(self) -> None:
        if self.started:
            return
        began = time.monotonic()
        self.machine.start()
        self.image = self.machine.image
        self.manifest = dict(getattr(self.machine, "manifest", {}) or {})
        self.started = True
        try:
            self._setup()
        except BaseException:
            self.close()
            raise
        self.start_s = round(time.monotonic() - began, 2)

    def _setup(self) -> None:
        code, out, err = self._admin(HARDENED_CHECK, 120)
        if code != 0:
            raise BoxError(f"the image is not hardened ({(out + err).strip()[-300:]})")
        # The work directory, and sbx's own logon at the console: Windows logs it on a little after the machine
        # answers, and background() starts its processes in that session.
        code, out, err = self._admin(
            f"New-Item -ItemType Directory -Force -Path {ps_quote(WIN_WORKDIR)} | Out-Null; "
            f"icacls {ps_quote(WIN_WORKDIR)} /grant 'sbx:(OI)(CI)F' | Out-Null; Write-Output setup-ok\n"
            f"\"sid=$((Get-LocalUser {WIN_USER}).SID.Value)\"\n" + JOB_CHECK +
            "foreach ($i in 1..75) { if ((quser 2> $null | Out-String) -match '(?m)^.?sbx\\s+console\\s') { "
            "Write-Output console-logon; break }; Start-Sleep 2 }", 200)
        if "setup-ok" not in out:
            raise BoxError(f"box setup failed: {(out + err).strip()[-400:]}")
        if "job-ok" not in out:
            raise BoxError("the image's task for the box user's commands is not as the image makes it "
                           f"({(out + err).strip()[-300:]})")
        if "console-logon" not in out:
            raise BoxError("the box user did not log on at the machine's console")
        sid = re.search(r"^sid=(S-1-5-[\d-]+)\s*$", out, re.M)
        if not sid:
            raise BoxError(f"the box user's SID could not be read: {(out + err).strip()[-200:]}")
        self.user_sid = sid.group(1)
        self.network_enabled = True
        self._check_containment(online=True)
        if self.display:
            self._setup_display()

    def _setup_display(self) -> None:
        """The display's own start: its parts are the image's and closed to the box user, the VNC server takes this
        box's password, the screen is the virtual display alone at its size, and the box user's desktop session
        is noted (what a launch's stop leaves)."""
        password = gui_win.new_vnc_password()
        code, out, err = self._admin(gui_win.display_start(password), 180)
        if "display-ok" not in out:
            raise BoxError(f"the box's display is not as the image makes it: {(out + err).strip()[-400:]}")
        self.vnc_password = password
        size = self.screen().size
        if size != (gui_win.SCREEN_W, gui_win.SCREEN_H):
            raise BoxError(f"the screen is {size[0]}x{size[1]}, not the virtual display's "
                           f"{gui_win.SCREEN_W}x{gui_win.SCREEN_H}")
        self.session = gui_win.session_procs(self)

    def close(self) -> None:
        if not self.started:
            return
        if self._screen is not None:
            self._screen.close()
            self._screen = None
        try:
            self.machine.close()
        except Exception as err:  # already gone; the provider's lifetime cap reaps it anyway
            self.log(f"{self.machine.provider} close: {type(err).__name__}: {err}")
        self.started = False

    def usd_per_second(self) -> float:
        return self.machine.usd_per_second()

    # -- commands and files

    def _require_started(self) -> None:
        if not self.started:
            raise BoxError("box is not started")

    def run_script(self, user: str, command: str, timeout_s: int, cwd: str, nonce: str) -> str:
        """What Windows PowerShell runs over SSH for a command of the administrator's (tests check it): the box's
        settings, the command for run.ps1 in $env:PF_ENC (run.ps1's shell reads it there and drops it), and
        run.ps1's exit code as its own. Nothing of the command is on a command line."""
        shell = "powershell" if user == ADMIN_USER else "pwsh"
        settings = "".join(f"$env:{key} = {ps_quote(value)}\n" for key, value in WIN_ENV.items())
        return (f"{settings}$env:PF_ENC = '{encode_ps(with_exit_code(command))}'\n"
                f"& {ps_quote(RUN_PS1)} -Timeout {int(timeout_s)} -Cwd {ps_quote(cwd)} -Nonce {nonce} -Shell {shell}\n"
                "exit $LASTEXITCODE\n")

    def job_input(self, command: str, timeout_s: int, cwd: str, nonce: str, job_id: str) -> bytes:
        """What relay.exe reads over SSH for a command of the box user's (tests check it)."""
        return relay_input(command, timeout_s, cwd, nonce, job_id)

    def _run(self, user: str, command: str, timeout_s: int, cwd: str, *,
             head: int | None = None) -> tuple[int, str, str, bool, bool, float]:
        """(exit code, stdout, stderr, host gave up, output was dropped, seconds), as VBoxBox._run returns."""
        nonce = secrets.token_hex(8)
        kw: dict[str, Any] = {"head": head, "tail": 0} if head else {}
        began = time.monotonic()
        if user == ADMIN_USER:
            script = self.run_script(user, command, timeout_s, cwd, nonce)
            code, out, err, truncated = self.machine.run_ps(user, script, timeout_s + 30 + HOST_GRACE_S, **kw)
        else:
            data = self.job_input(command, timeout_s, cwd, nonce, secrets.token_hex(8))
            code, out, err, truncated = self.machine.run_exe(user, RELAY_EXE, data,
                                                             JOB_START_S + timeout_s + 30 + HOST_GRACE_S, **kw)
        seconds = round(time.monotonic() - began, 2)
        out, guest_code, warning = read_sentinel(out, nonce, code)
        if guest_code is None:
            if code is None:
                guest_code = 124
            elif code == NOT_STARTED_EXIT and user != ADMIN_USER:
                raise BoxError(f"a command of the box user's did not start: {err.strip()[-300:]}")
            else:  # no trusted exit-code line: all that is known is whether the session ended well
                guest_code = 0 if code == 0 else 1
                err += "\n" + (warning or "[pickfit: the command ended without its exit-code line]")
        return guest_code, out, err, code is None, truncated, seconds

    def _admin(self, script: str, timeout_s: int = 60) -> tuple[int, str, str]:
        """Harness-only administrator command (checks, probes); never used for model commands. It runs in the
        harness directory, which sbx cannot write."""
        script = "$ProgressPreference = 'SilentlyContinue'\n" + script  # no progress CLIXML on stderr
        code, out, err, _, _, _ = self._run(ADMIN_USER, script, timeout_s, HARNESS_DIR)
        return code, out, err

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        return VBoxBox.exec(self, command, timeout_s, cwd=cwd)  # type: ignore[arg-type]

    def _guest_path(self, path: str) -> str:
        return VBoxBox._guest_path(self, path)  # type: ignore[arg-type]

    def read_file(self, path: str, max_bytes: int = 64_000) -> bytes:
        return VBoxBox.read_file(self, path, max_bytes)  # type: ignore[arg-type]

    def list_command(self, path: str) -> str:
        return VBoxBox.list_command(self, path)  # type: ignore[arg-type]

    def screen(self) -> Any:
        """The desktop as pickfit sees and drives it (gui_win.WinVncDisplay)."""
        if not self.display:
            raise BoxError("this box has no display")
        if self._screen is None:
            self._screen = gui_win.WinVncDisplay(self)
        return self._screen

    def launch_gui(self, command: str, tag: str | int, wait_s: int, *,
                   timeout_s: int | None = None) -> tuple[ExecResult, Any, bytes | None]:
        """gui.launch for this box: (the record to keep, what it showed, the screenshot PNG)."""
        return gui_win.launch(self, command, tag, wait_s, timeout_s=timeout_s)

    def harness_exec(self, argv: list[str], timeout_s: int, *, stdin: bytes | None = None) -> ExecResult:
        """A program of the image's as the administrator (pickfit's own checks, such as gui_operate's file check),
        with `stdin` piped to it; never the box user's. The script goes to Windows PowerShell on the ssh session's
        stdin, not through run.ps1: run.ps1 hands its command over in an environment variable, which Windows caps
        at 32,767 characters, and the file check's script with its parameters came to about 37,000 (measured
        2026-11-17: every file check of a run on this box ended with exit 1 and no answer)."""
        exe, *args = argv
        call = f"& {ps_quote(exe)} " + " ".join(ps_quote(a) for a in args)
        if stdin is not None:
            call = ("$OutputEncoding = New-Object Text.UTF8Encoding $false\n"
                    f"[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{base64.b64encode(stdin).decode()}'))"
                    f" | {call}")
        began = time.monotonic()
        code, out, err, _ = self.machine.run_ps(ADMIN_USER, f"Set-Location {ps_quote(HARNESS_DIR)}\n{call}\n"
                                                "exit $LASTEXITCODE\n", timeout_s + 30)
        return ExecResult(command=" ".join(argv), exit_code=124 if code is None else code, stdout=out, stderr=err,
                          seconds=round(time.monotonic() - began, 2), timed_out=code is None)

    def background(self, command: str, port: int | None, wait_s: int, tag: int | str) -> str:
        """PowerShell for run_background, VBoxBox's own: the command that runs it is in the box user's session at
        the console, where a process it starts stays when the command returns (over SSH it would not: sshd ends
        every process of a command's session; measured 2026-11-17)."""
        return VBoxBox.background(self, command, port, wait_s, tag)  # type: ignore[arg-type]

    def write_file(self, path: str, content: str | bytes) -> None:
        """Create or replace a file as the box user, a chunk per command."""
        self._require_started()
        data = content.encode("utf-8") if isinstance(content, str) else content
        target = ps_quote(self._guest_path(path))
        for offset in range(0, max(len(data), 1), WRITE_CHUNK):
            chunk = base64.b64encode(data[offset:offset + WRITE_CHUNK]).decode()
            if offset == 0:
                write = (f"New-Item -ItemType Directory -Force -Path (Split-Path -Parent {target}) | Out-Null\n"
                         f"[IO.File]::WriteAllBytes({target}, [Convert]::FromBase64String('{chunk}'))\n")
            else:
                write = (f"$f = [IO.File]::Open({target}, 'Append'); $b = [Convert]::FromBase64String('{chunk}')\n"
                         "$f.Write($b, 0, $b.Length); $f.Close()\n")
            script = ("$ErrorActionPreference = 'Stop'\ntry {\n" + write + "'written'\n} catch { "
                      "[Console]::Error.WriteLine($_.Exception.Message); exit 1 }\n")
            code, out, err, _ = self.machine.run_ps(WIN_USER, script, 120)
            if code != 0 or "written" not in out:
                raise BoxError(f"cannot write {path}: {(err or out).strip()[-300:]}")

    # -- network

    def _probe(self, user: str, targets: dict[str, str], *, url: str = "", dns: str = "",
               ms: int = 3000) -> dict[str, str]:
        """probe.ps1 as that user: each target open, refused, timeout or unreachable; the URL; the name."""
        arg = ",".join(f"{k}={v}" for k, v in targets.items())
        script = (f"& {ps_quote(PROBE_PS1)} -Targets {ps_quote(arg)} -Ms {ms}"
                  + (f" -Url {ps_quote(url)}" if url else "") + (f" -Dns {ps_quote(dns)}" if dns else ""))
        if user == ADMIN_USER:
            code, out, err = self._admin(script, 90)
        else:
            code, out, err, _, _, _ = self._run(WIN_USER, script, 90, WIN_HOME)
        found = {m.group(1): m.group(2) for m in PROBE_LINE.finditer(out)}
        missing = [n for n in [*targets, *(["public"] if url else []), *(["dns"] if dns else [])] if n not in found]
        if missing:
            raise BoxError(f"containment probe could not run (no result for {', '.join(missing)}): "
                           f"{(out + err).strip()[-200:]}")
        return found

    def _check_containment(self, *, online: bool) -> None:
        """Fail closed unless, for the box user, the addresses it must never reach stay closed and the internet
        is as the mode says."""
        res = self._probe(WIN_USER, {**MUST_NOT_OPEN, "internet": INTERNET}, url=PUBLIC_URL, dns=PROBE_NAME)
        bad = [f"{name} {res[name]}" for name in MUST_NOT_OPEN if res[name] in REACHED]
        if online:
            if res["internet"] != "open" or res["public"] != "curl0":
                bad.append(f"internet unreachable online ({res['internet']}, {res['public']})")
            if res["dns"] != "resolved":
                bad.append("names do not resolve online")
        else:
            if res["internet"] in REACHED or res["public"] == "curl0":
                bad.append(f"internet reachable with the network cut ({res['internet']}, {res['public']})")
            if res["dns"] != "failed":
                bad.append("a name resolves with the network cut")
        if bad:
            raise BoxError(f"containment check ({'online' if online else 'offline'}) failed: {'; '.join(bad)}")

    def set_network(self, enabled: bool) -> None:
        self._require_started()
        if enabled == self.network_enabled:
            return
        if enabled:
            self._check_containment(online=False)  # the cut held for as long as the box said offline
        self.machine.set_egress(enabled)  # BoxError if either half was not made
        self._check_containment(online=enabled)
        self.network_enabled = enabled

    def _hold(self, tag: str) -> None:
        """Start the box user's held connection and wait until it is open."""
        script = HOLD_SCRIPT.replace("@TAG@", tag)
        started = self.exec(self.background(script, None, 3, tag), 60)
        held = self.exec(f"foreach ($i in 1..40) {{ if (Test-Path \"$HOME\\.pickfit-bg\\{tag}.held\") {{ 'held'; break }}; "
                         "Start-Sleep -Milliseconds 500 }", 40)
        if "held" not in held.stdout:
            raise BoxError(f"the held connection did not open: {(started.stdout + started.stderr).strip()[-200:]}")

    def _release(self, tag: str) -> str:
        """Let the held connection ask, and return what it got: 'answered N' or 'nothing'."""
        got = self.exec(f"Set-Content \"$HOME\\.pickfit-bg\\{tag}.go\" go; foreach ($i in 1..40) {{ "
                        f"if (Test-Path \"$HOME\\.pickfit-bg\\{tag}.result\") {{ Get-Content "
                        f"\"$HOME\\.pickfit-bg\\{tag}.result\"; break }}; Start-Sleep -Milliseconds 500 }}", 40)
        return got.stdout.strip() or "no result"

    def _display_controls(self, rec: Callable[[str, bool, str, str], None]) -> None:
        """The display's own controls for the limits test: what pickfit sees and drives is the box user's desktop,
        and nothing of it (the VNC server's password and service, the session helper, the display's settings) is
        the box user's to read, stop, run as SYSTEM or change."""
        from pickfit.verify.vnc import VncClient, VncError

        screen = self.screen()
        shot = screen.screenshot()
        rec("display_screen", screen.size == (gui_win.SCREEN_W, gui_win.SCREEN_H) and len(shot) > 5000,
            f"pickfit's screenshot is the {gui_win.SCREEN_W}x{gui_win.SCREEN_H} desktop",
            f"{screen.size[0]}x{screen.size[1]}, {len(shot)} bytes")
        word = "pickfit" + secrets.token_hex(4)
        self.exec(f"Set-Clipboard -Value '{word}'", 30)
        got = screen.clipboard()
        rec("display_clipboard", got == word.encode(), "the session helper reads what the box user put on the clipboard",
            repr(got))
        settings = self.exec(f"try {{ Get-ItemProperty '{gui_win.VNC_KEY}' -ErrorAction Stop | Out-Null; 'read' }} "
                             "catch { 'refused' }", 30)
        admin = self._admin(f"if ((Get-ItemProperty '{gui_win.VNC_KEY}').Password) {{ 'read' }}", 30)[1]
        rec("vnc_settings_closed", "refused" in settings.stdout and "read" in admin,
            "the box user cannot read the VNC server's settings (its password); the administrator can",
            f"box user {settings.stdout.strip()}; administrator {admin.strip()}")
        password = self.vnc_password or ""
        wrong = ("y" if password.startswith("x") else "x") + password[1:]
        try:
            VncClient("127.0.0.1", screen._port, wrong).connect().close()
            refused = "accepted"
        except VncError as err:
            refused = f"refused: {err}"
        rec("vnc_wrong_password", refused.startswith("refused"), "the VNC server refuses any password but this box's",
            refused)
        stopped = self.exec("sc.exe stop tvnserver; \"sc=$LASTEXITCODE\"", 30)
        running = self._admin("(Get-Service tvnserver).Status", 30)[1].strip()
        rec("vnc_service_locked", "sc=0" not in stopped.stdout and running == "Running",
            "the box user cannot stop the VNC server", f"sc.exe: {stopped.stdout.strip()[-80:]}; service {running}")
        listening = self._admin(f"@(Get-NetTCPConnection -State Listen -LocalPort {gui_win.VNC_PORT} | "
                                "ForEach-Object LocalAddress | Sort-Object -Unique) -join ','", 30)[1].strip()
        rec("vnc_loopback_only", listening == "127.0.0.1", "the VNC server listens on the machine's loopback only",
            listening or "nothing")
        helper = gui_win.desk(self, "procs")
        theirs = self.exec(f"& '{gui_win.DESK_EXE}' procs", 60)
        rec("session_helper_system", helper.get("sid") == "S-1-5-18" and int(helper.get("session") or 0) >= 1
            and '"S-1-5-18"' not in theirs.stdout,
            "the session helper runs as SYSTEM in the console session for the administrator, and as nobody for "
            "the box user", f"administrator: {helper.get('sid')} session {helper.get('session')}; box user: "
            f"{(theirs.stdout + theirs.stderr).strip()[-120:]}")
        files = [gui_win.DESK_EXE, gui_win.DESKIN_EXE, gui_win.VDD_DIR + r"\vdd_settings.xml"]
        tried = self.exec("; ".join(f"try {{ [IO.File]::AppendAllText('{f}', 'x'); 'changed {f}' }} catch {{ 'kept' }}"
                                    for f in files), 30)
        rec("display_files_locked", "changed" not in tried.stdout and tried.stdout.count("kept") == len(files),
            "the box user cannot change the session helper or the display's settings", tried.stdout.strip()[-200:])

    def validate_containment(self) -> list[tuple[str, bool, str, str]]:
        """Positive and negative controls for the limits test. Cuts and restores the live network, so only the
        limits test (no untrusted code has run) calls it; leaves the box online."""
        results: list[tuple[str, bool, str, str]] = []

        def rec(name: str, ok: bool, expect: str, detail: str) -> None:
            results.append((name, ok, expect, detail))

        if self.display:
            self._display_controls(rec)

        closed = ", ".join(MUST_NOT_OPEN)
        targets = {**MUST_NOT_OPEN, "internet": INTERNET}
        on = self._probe(WIN_USER, targets, url=PUBLIC_URL, dns=PROBE_NAME)
        admin = self._probe(ADMIN_USER, targets, url=PUBLIC_URL)
        rec("link_local_and_private_closed", not [n for n in MUST_NOT_OPEN if on[n] in REACHED],
            f"the box user reaches none of {closed}", ", ".join(f"{n}={on[n]}" for n in MUST_NOT_OPEN))
        rec("link_local_control_admin", admin["metadata"] in REACHED,
            "the administrator's packet to the metadata address arrives: what stops the box user is the rule",
            f"metadata={admin['metadata']}; the service, turned off, said {getattr(self.machine, 'metadata_answer', None)!r}")
        rec("private_closed_for_admin", admin["private"] not in REACHED,
            "a private address is closed to the administrator too (the provider's rule, outside the machine)",
            admin["private"])
        rec("internet_online", on["internet"] == "open" and on["public"] == "curl0" and admin["public"] == "curl0",
            "the internet answers online (the probe sees an open port)",
            f"box user {on['internet']} {on['public']}; administrator {admin['public']}")
        rec("names_resolve_online", on["dns"] == "resolved", f"{PROBE_NAME} resolves online", on["dns"])
        self._hold("limits-held-control")
        control = self._release("limits-held-control")
        rec("held_connection_control", control.startswith("answered") and control != "answered 0",
            "online, a connection held open still gets its answer (the next probe is not a no-op)", control)
        self._hold("limits-held")
        self.set_network(False)
        try:
            off = self._probe(WIN_USER, targets, url=PUBLIC_URL, dns=PROBE_NAME)
            admin_off = self._probe(ADMIN_USER, {"internet": INTERNET}, url=PUBLIC_URL)
            held = self._release("limits-held")
        finally:
            self.set_network(True)
        rec("internet_offline", off["internet"] not in REACHED and off["public"] != "curl0",
            "the internet is closed to the box user offline", f"{off['internet']} {off['public']}")
        rec("internet_offline_for_admin", admin_off["internet"] not in REACHED and admin_off["public"] != "curl0",
            "and to the administrator: the provider closed it outside the machine",
            f"{admin_off['internet']} {admin_off['public']}")
        rec("names_do_not_resolve_offline", off["dns"] == "failed", f"{PROBE_NAME} does not resolve offline", off["dns"])
        reached = sorted(n for n, r in off.items() if r in REACHED)
        rec("nothing_reached_offline", not reached, "no target answers the box user offline", ", ".join(reached) or "none")
        rec("held_connection_ended", held == "nothing",
            "a connection the box user opened online carries nothing after the cut", held)
        return results
