"""Launch a GUI app on a Windows box's desktop, see the screen and drive it (WindowsBox made with display=True).

gui.py's check for Windows, as gui_mac.py is the Mac's: the same tiers, report and evidence rules. The guest side is
the same on every provider; ec2_windows bakes it into an image (MAKE_DISPLAY at the build, SCREEN once the box user
is logged on). Measured 2026-11-17 on EC2's Windows Server 2025 in Taipei, from Taiwan.

- The screen: EC2's own display adapter offers 800x600 and nothing else, so the image adds a virtual display
  (Virtual Display Driver, an IddCx display driver signed through SignPath, MIT) at 1280x800 and makes it the only
  one. The box user cannot change its settings file.
- pickfit sees and drives it over VNC: the image's TightVNC server (GPL-2.0, run as its own program, a service as
  SYSTEM) listens on the machine's loopback only, with a password the host makes for each box and writes into the
  server's settings, which only SYSTEM and administrators can read; its control interface has a password nobody is
  given. The host reaches the port through the administrator's ssh connection (a forwarded port). Frames come
  ZRLE-compressed: 0.1 s and 17 KB for the whole screen, against 1.5 to 3 s for the 4 MB raw frame.
- The app runs as sbx in its session at the console (windows_box's job.exe); nothing that produces evidence does.
  desk.exe, which the administrator runs, starts deskin.exe as SYSTEM in that session with a token of the
  session's own winlogon (what tools that run a program on a user's desktop do); it lists the windows there with
  their owner process (the window manager's), each process's image and user (the kernel's), and reads the
  clipboard. 0.2 s a call. A SYSTEM process is out of the app's reach.
- A window is the app's own when it is visible, not cloaked, at least MIN_WIDTH x MIN_HEIGHT on screen, and its
  owner is a process of the box user's that was not running before the launch and whose image is not Windows'
  own (under C:\\Windows: a console host, SmartScreen, Explorer). Explorer's taskbar and desktop are not counted,
  nor is pickfit's own job.exe with the shell it holds ready. An app may ask Windows to keep its window out of
  every screen capture (KeePassXC does by default): the launch says so, since no screenshot can show it.
- Afterwards the administrator stops every process of the box user's that was not in its desktop session when
  the box started (the app, its helpers, run_background servers, a waiting job.exe), in rounds until none is
  left; only the parts of Windows' own shell that Windows starts again by itself (SHELL) are left alone.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import string
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pickfit.verify import gui
from pickfit.verify.box import BoxError, ExecResult
from pickfit.verify.gui import GuiLaunch, GuiWindow
from pickfit.verify.vnc import WINDOWS_MODIFIERS, VncClient, VncError, png, vnc_stored_password

if TYPE_CHECKING:
    from pickfit.verify.windows_box import WindowsBox

HARNESS = r"C:\ProgramData\pickfit"
DESK_EXE = HARNESS + r"\desk.exe"
DESKIN_EXE = HARNESS + r"\deskin.exe"
DESK_DIR = HARNESS + r"\desk"  # requests and results: SYSTEM's and administrators' only
VNC_PORT = 5900
VNC_KEY = r"HKLM:\SOFTWARE\TightVNC\Server"
VNC_VERSION = "2.8.89"
VDD_URL = ("https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/download/25.7.23/"
           "VirtualDisplayDriver-x86.Driver.Only.zip")  # x86-64 despite the name: the INF is NTamd64
VDD_SHA256 = "e24210692b442b39af763536330ce78b423f19342b7a7792c26de3944e418b3a"
VDD_DIR = r"C:\VirtualDisplayDriver"  # where the driver reads vdd_settings.xml
SCREEN_W, SCREEN_H = 1280, 800
DISPLAY_NOTE = "Windows desktop 1280x800 (a virtual display) on EC2; pickfit's screenshot over VNC"
APP_LOG_DIR = r"$HOME\.pickfit-gui"
EARLY_EXIT_S = 10  # a launcher that hands the app to another process: none of the box user's for a moment is not yet "it exited"
POLL_S = 1.0
SETTLE_GAP_S, SETTLE_MAX_S = 0.4, 4.0  # a screenshot waits until two frames this far apart agree
STOP_ROUNDS = 25


def _sleep(seconds: float) -> None:  # tests replace it
    time.sleep(seconds)
WINDOWS_OWN = "c:\\windows\\"
# Windows' own shell in the box user's session, which Windows starts again by itself when it is gone: a stop leaves
# these alone (an app cannot put code in them; a rundll32 or a COM surrogate could carry the app's, so those go).
SHELL = frozenset({
    "c:\\windows\\explorer.exe", "c:\\windows\\system32\\sihost.exe", "c:\\windows\\system32\\ctfmon.exe",
    "c:\\windows\\system32\\taskhostw.exe", "c:\\windows\\system32\\runtimebroker.exe",
    "c:\\windows\\system32\\backgroundtaskhost.exe", "c:\\windows\\system32\\fontdrvhost.exe",
    "c:\\windows\\system32\\dwm.exe", "c:\\windows\\system32\\securityhealthsystray.exe",
})
SHELL_DIRS = ("c:\\windows\\systemapps\\",)  # Start, Search, the text input host: Windows' packaged shell parts
SHELL_CLASSES = frozenset({"Progman", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "WorkerW"})
JOB_EXE = HARNESS + r"\job.exe"  # windows_box's: it waits with the box user's next shell ready, and is not the app
# A window's display affinity (SetWindowDisplayAffinity): WDA_MONITOR shows it black in any capture, and
# WDA_EXCLUDEFROMCAPTURE leaves it out of every capture (KeePassXC does so by default, measured 2026-11-17: the VNC
# frame, a BitBlt with CAPTUREBLT and the GUI judge all saw only the wallpaper behind it).
HIDDEN_FROM_CAPTURE = {1: "shown black in any screen capture", 17: "left out of every screen capture"}

# desk.exe and deskin.exe: one program built twice, as a console program for the administrator and as a windowless
# one for the console session (nothing of it shows on the box user's desktop). C# 5, which Windows' own compiler
# takes. CreateProcessAsUser runs while impersonating the session's SYSTEM token, whose privileges it needs, with
# CREATE_BREAKAWAY_FROM_JOB: sshd keeps every process of a command in a job object, and a job's process cannot start
# one in another session (measured: "Access is denied" without it).
DESK_SOURCE = r"""using System; using System.Collections.Generic; using System.ComponentModel; using System.Diagnostics; using System.IO;
using System.Runtime.InteropServices; using System.Text; using System.Web.Script.Serialization;
public static class PfDesk {
  const string Dir = @"@DIR@";
  [DllImport("kernel32.dll")] static extern uint WTSGetActiveConsoleSessionId();
  [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr OpenProcess(int access, bool inherit, int pid);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
  [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int which);
  [DllImport("advapi32.dll", SetLastError = true)] static extern bool OpenProcessToken(IntPtr p, int access, out IntPtr tok);
  [DllImport("advapi32.dll", SetLastError = true)] static extern bool DuplicateTokenEx(IntPtr tok, int access, IntPtr attrs, int level, int type, out IntPtr dup);
  [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)] static extern bool LookupPrivilegeValue(string sys, string name, out long luid);
  [DllImport("advapi32.dll", SetLastError = true)] static extern bool AdjustTokenPrivileges(IntPtr tok, bool all, ref TP state, int len, IntPtr prev, IntPtr ret);
  [StructLayout(LayoutKind.Sequential, Pack = 4)] struct TP { public int Count; public long Luid; public int Attr; }
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] struct SI { public int cb; public string r; public string Desktop; public string Title;
    public int x, y, w, h, cx, cy, fill, Flags; public short Show, r2; public IntPtr r3, i, o, e; }
  [StructLayout(LayoutKind.Sequential)] struct PI { public IntPtr Process, Thread; public int Pid, Tid; }
  [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)] static extern bool CreateProcessAsUser(IntPtr tok, string app, string cmd, IntPtr pa, IntPtr ta, bool inherit, int flags, IntPtr env, string dir, ref SI si, out PI pi);
  [DllImport("advapi32.dll", SetLastError = true)] static extern bool ImpersonateLoggedOnUser(IntPtr tok);
  [DllImport("advapi32.dll")] static extern bool RevertToSelf();
  [DllImport("kernel32.dll")] static extern int WaitForSingleObject(IntPtr h, int ms);
  [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr h, int code);
  [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr h, out int code);
  delegate bool EnumProc(IntPtr hwnd, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] static extern int GetWindowThreadProcessId(IntPtr h, out int pid);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] static extern bool GetWindowDisplayAffinity(IntPtr h, out uint affinity);
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] struct PE { public int Size, Usage, Pid; public IntPtr Heap; public int Module, Threads, Parent, Base, Flags;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] public string Exe; }
  [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr CreateToolhelp32Snapshot(int flags, int pid);
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern bool Process32FirstW(IntPtr snap, ref PE e);
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern bool Process32NextW(IntPtr snap, ref PE e);
  [StructLayout(LayoutKind.Sequential)] struct RECT { public int L, T, R, B; }
  [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr h, int attr, out RECT r, int size);
  [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr h, int attr, out int v, int size);
  [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern bool QueryFullProcessImageName(IntPtr p, int flags, StringBuilder s, ref int n);
  [DllImport("kernel32.dll")] static extern bool GetProcessTimes(IntPtr p, out long c, out long e, out long k, out long u);
  [DllImport("advapi32.dll", SetLastError = true)] static extern bool GetTokenInformation(IntPtr t, int cls, IntPtr buf, int len, out int ret);
  [DllImport("advapi32.dll", CharSet = CharSet.Unicode)] static extern bool ConvertSidToStringSid(IntPtr sid, out string s);
  [DllImport("kernel32.dll")] static extern bool ProcessIdToSessionId(int pid, out int session);
  [DllImport("user32.dll")] static extern bool OpenClipboard(IntPtr h);
  [DllImport("user32.dll")] static extern bool CloseClipboard();
  [DllImport("user32.dll")] static extern IntPtr GetClipboardData(int fmt);
  [DllImport("kernel32.dll")] static extern IntPtr GlobalLock(IntPtr h);
  [DllImport("kernel32.dll")] static extern bool GlobalUnlock(IntPtr h);

  static void Enable(IntPtr t, string name) {
    var tp = new TP { Count = 1, Attr = 2 }; LookupPrivilegeValue(null, name, out tp.Luid);
    if (!AdjustTokenPrivileges(t, false, ref tp, 0, IntPtr.Zero, IntPtr.Zero) || Marshal.GetLastWin32Error() == 1300)
      throw new Exception("cannot enable " + name); }
  static Exception Failed(string what) { return new Exception(what + ": " + new Win32Exception().Message); }

  public static int Main(string[] a) {
    if (a.Length == 3 && a[0] == "--inner") return Inner(a[1], a[2]);
    return Outer(a);
  }

  // The administrator, in its ssh session: this program again, as SYSTEM in the console session; its answer.
  static int Outer(string[] a) {
    var stdout = new FileStream(new Microsoft.Win32.SafeHandles.SafeFileHandle(GetStdHandle(-11), false), FileAccess.Write, 1, false);
    var utf8 = new UTF8Encoding(false); string text; int code = 1;
    string id = Guid.NewGuid().ToString("N"), req = Path.Combine(Dir, id + ".req"), res = Path.Combine(Dir, id + ".res");
    try {
      File.WriteAllText(req, string.Join("\n", a), utf8);
      IntPtr me; OpenProcessToken(Process.GetCurrentProcess().Handle, 0x20 | 0x8, out me); Enable(me, "SeDebugPrivilege"); CloseHandle(me);
      uint session = WTSGetActiveConsoleSessionId();
      Process host = null;
      foreach (var p in Process.GetProcessesByName("winlogon")) if (p.SessionId == session) host = p;
      if (host == null) throw new Exception("no winlogon in the console session " + session);
      IntPtr hp = OpenProcess(0x1000, false, host.Id); if (hp == IntPtr.Zero) throw Failed("open winlogon");
      IntPtr tok, imp, dup = IntPtr.Zero;
      if (!OpenProcessToken(hp, 0x1 | 0x2 | 0x8, out tok)) throw Failed("open its token");
      if (!DuplicateTokenEx(tok, 0x02000000, IntPtr.Zero, 2, 2, out imp)) throw Failed("duplicate it");
      Enable(imp, "SeAssignPrimaryTokenPrivilege"); Enable(imp, "SeIncreaseQuotaPrivilege");
      var si = new SI(); si.cb = Marshal.SizeOf(si); si.Desktop = @"winsta0\default";
      PI pi; string exe = @"@DESKIN@";
      if (!ImpersonateLoggedOnUser(imp)) throw Failed("impersonate");
      bool made;
      try {
        if (!DuplicateTokenEx(tok, 0x02000000, IntPtr.Zero, 2, 1, out dup)) throw Failed("make a primary token");
        made = CreateProcessAsUser(dup, exe, "\"" + exe + "\" --inner \"" + req + "\" \"" + res + "\"", IntPtr.Zero, IntPtr.Zero,
                                   false, 0x08000000 | 0x01000000, IntPtr.Zero, Dir, ref si, out pi);
      } finally { RevertToSelf(); }
      if (!made) throw Failed("start the session helper");
      if (WaitForSingleObject(pi.Process, 60000) != 0) { TerminateProcess(pi.Process, 1); throw new Exception("the session helper did not finish"); }
      GetExitCodeProcess(pi.Process, out code);
      text = File.Exists(res) ? File.ReadAllText(res, utf8) : "{\"error\": \"the session helper gave no answer (exit " + code + ")\"}";
    } catch (Exception e) { text = "{\"error\": " + new JavaScriptSerializer().Serialize(e.Message) + "}"; code = 1; }
    try { File.Delete(req); File.Delete(res); } catch (Exception) { }
    var b = utf8.GetBytes(text + "\n"); stdout.Write(b, 0, b.Length); stdout.Flush();
    return code;
  }

  static string Sid(IntPtr proc) {
    IntPtr t; if (!OpenProcessToken(proc, 0x8, out t)) return null;
    try { int n; GetTokenInformation(t, 1, IntPtr.Zero, 0, out n); IntPtr buf = Marshal.AllocHGlobal(n);
      try { if (!GetTokenInformation(t, 1, buf, n, out n)) return null; string s; ConvertSidToStringSid(Marshal.ReadIntPtr(buf), out s); return s; }
      finally { Marshal.FreeHGlobal(buf); } } finally { CloseHandle(t); } }
  static Dictionary<int, int> Parents() {
    var d = new Dictionary<int, int>(); IntPtr snap = CreateToolhelp32Snapshot(2, 0); if (snap == new IntPtr(-1)) return d;
    try { var e = new PE(); e.Size = Marshal.SizeOf(e);
      for (bool more = Process32FirstW(snap, ref e); more; more = Process32NextW(snap, ref e)) d[e.Pid] = e.Parent; }
    finally { CloseHandle(snap); }
    return d; }
  static Dictionary<string, object> ProcInfo(int pid) {
    var d = new Dictionary<string, object> { { "pid", pid } };
    IntPtr p = OpenProcess(0x1000, false, pid); if (p == IntPtr.Zero) return d;
    try { var sb = new StringBuilder(1024); int n = sb.Capacity; if (QueryFullProcessImageName(p, 0, sb, ref n)) d["exe"] = sb.ToString();
      long c, e, k, u; if (GetProcessTimes(p, out c, out e, out k, out u)) d["start"] = c.ToString();
      d["sid"] = Sid(p); }
    finally { CloseHandle(p); }
    return d; }
  static List<object> Windows() {
    var list = new List<object>();
    EnumWindows((h, l) => {
      if (!IsWindowVisible(h)) return true;
      int cloaked; if (DwmGetWindowAttribute(h, 14, out cloaked, 4) != 0) cloaked = 0;
      RECT r; if (DwmGetWindowAttribute(h, 9, out r, 16) != 0) GetWindowRect(h, out r);
      int pid; GetWindowThreadProcessId(h, out pid);
      uint affinity; if (!GetWindowDisplayAffinity(h, out affinity)) affinity = 0;
      var t = new StringBuilder(512); GetWindowText(h, t, 512); var c = new StringBuilder(256); GetClassName(h, c, 256);
      list.Add(new Dictionary<string, object> { { "hwnd", h.ToInt64().ToString() }, { "pid", pid }, { "title", t.ToString() },
        { "affinity", (long)affinity },
        { "class", c.ToString() }, { "cloaked", cloaked != 0 }, { "iconic", IsIconic(h) }, { "owned", GetWindow(h, 4) != IntPtr.Zero },
        { "x", r.L }, { "y", r.T }, { "width", r.R - r.L }, { "height", r.B - r.T } });
      return true; }, IntPtr.Zero);
    return list; }
  static List<object> Procs(int session) {
    var list = new List<object>(); var parents = Parents();
    foreach (var p in Process.GetProcesses()) {
      if (p.SessionId != session) continue;
      var d = ProcInfo(p.Id); int parent; if (parents.TryGetValue(p.Id, out parent)) d["ppid"] = parent; list.Add(d); }
    return list; }

  // SYSTEM, at the console session's desktop: the answer goes to a file in Dir.
  static int Inner(string req, string res) {
    var js = new JavaScriptSerializer(); js.MaxJsonLength = 1 << 24;
    var outd = new Dictionary<string, object>();
    try {
      var a = File.ReadAllText(req).Split('\n');
      int mine; ProcessIdToSessionId(Process.GetCurrentProcess().Id, out mine);
      outd["session"] = mine; outd["sid"] = Sid(Process.GetCurrentProcess().Handle);
      if (a[0] == "look") { outd["windows"] = Windows(); outd["procs"] = Procs(mine); }
      else if (a[0] == "procs") outd["procs"] = Procs(mine);
      else if (a[0] == "windows") outd["windows"] = Windows();
      else if (a[0] == "clipboard") {
        string text = null; bool opened = false;
        for (int i = 0; i < 20 && !opened; i++) { opened = OpenClipboard(IntPtr.Zero); if (!opened) System.Threading.Thread.Sleep(100); }
        if (!opened) throw new Exception("the clipboard stayed busy");
        try { IntPtr h = GetClipboardData(13); if (h != IntPtr.Zero) { IntPtr p = GlobalLock(h); text = Marshal.PtrToStringUni(p); GlobalUnlock(h); } }
        finally { CloseClipboard(); }
        outd["clipboard"] = text;
      } else outd["error"] = "unknown request " + a[0];
    } catch (Exception e) { outd["error"] = e.GetType().Name + ": " + e.Message; }
    File.WriteAllText(res, js.Serialize(outd), new UTF8Encoding(false));
    return outd.ContainsKey("error") ? 2 : 0;
  }
}
""".replace("@DIR@", DESK_DIR).replace("@DESKIN@", DESKIN_EXE)

# The root-enumerated device the driver's INF names (Root\MttVDD) and its driver: what devcon install does.
_DEVICE_SOURCE = r"""using System; using System.Runtime.InteropServices; using System.ComponentModel;
public static class PfDev {
  [StructLayout(LayoutKind.Sequential)] struct SP_DEVINFO_DATA { public int cbSize; public Guid ClassGuid; public int DevInst; public IntPtr Reserved; }
  [DllImport("setupapi.dll", SetLastError = true)] static extern IntPtr SetupDiCreateDeviceInfoList(ref Guid g, IntPtr hwnd);
  [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode)] static extern bool SetupDiCreateDeviceInfoW(IntPtr set, string name, ref Guid g, string desc, IntPtr hwnd, int flags, ref SP_DEVINFO_DATA d);
  [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode)] static extern bool SetupDiSetDeviceRegistryPropertyW(IntPtr set, ref SP_DEVINFO_DATA d, int prop, byte[] buf, int size);
  [DllImport("setupapi.dll", SetLastError = true)] static extern bool SetupDiCallClassInstaller(int fn, IntPtr set, ref SP_DEVINFO_DATA d);
  [DllImport("setupapi.dll", SetLastError = true)] static extern bool SetupDiDestroyDeviceInfoList(IntPtr set);
  [DllImport("newdev.dll", SetLastError = true, CharSet = CharSet.Unicode)] static extern bool UpdateDriverForPlugAndPlayDevicesW(IntPtr hwnd, string hwid, string inf, int flags, out bool reboot);
  public static string Install(string inf, string hwid) {
    Guid display = new Guid("4d36e968-e325-11ce-bfc1-08002be10318");
    IntPtr set = SetupDiCreateDeviceInfoList(ref display, IntPtr.Zero);
    var d = new SP_DEVINFO_DATA(); d.cbSize = Marshal.SizeOf(d);
    if (!SetupDiCreateDeviceInfoW(set, "Display", ref display, null, IntPtr.Zero, 1, ref d)) throw new Win32Exception();
    byte[] id = System.Text.Encoding.Unicode.GetBytes(hwid + "\0\0");
    if (!SetupDiSetDeviceRegistryPropertyW(set, ref d, 1, id, id.Length)) throw new Win32Exception();
    if (!SetupDiCallClassInstaller(0x19, set, ref d)) throw new Win32Exception();
    SetupDiDestroyDeviceInfoList(set);
    bool reboot;
    if (!UpdateDriverForPlugAndPlayDevicesW(IntPtr.Zero, hwid, inf, 1, out reboot)) throw new Win32Exception();
    return "vdd=installed reboot=" + reboot;
  }
}
"""
# As the administrator, when a display image is made (winget is on PATH): the session helper, the virtual display
# (downloaded and checked by SHA-256 and signature; its publisher trusted for this driver, so it installs without
# a prompt; its settings: 1280x800 only), and the VNC server, set to loopback, VNC authentication, a control
# password, no web viewer, and stopped until a box sets its own password (WIN_DISPLAY_START).
MAKE_DISPLAY = r"""$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$env:Path += ";$env:LOCALAPPDATA\Microsoft\WindowsApps"
New-Item -ItemType Directory -Force '@DESKDIR@' | Out-Null
icacls.exe '@DESKDIR@' /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
$src = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('@DESK@'))
foreach ($b in @(@('@DESKEXE@', 'ConsoleApplication'), @('@DESKINEXE@', 'WindowsApplication'))) {
  Remove-Item $b[0] -Force -ErrorAction SilentlyContinue
  Add-Type -TypeDefinition $src -OutputAssembly $b[0] -OutputType $b[1] -ReferencedAssemblies System.Web.Extensions, System.Core
  icacls.exe $b[0] /reset | Out-Null }
'desk-made'
$dir = '@HARNESS@\vdd'
New-Item -ItemType Directory -Force $dir | Out-Null
$zip = Join-Path $env:TEMP 'vdd.zip'
& curl.exe -fsSL -o $zip '@VDDURL@'
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
if ($hash -ne '@VDDSHA@') { "the display driver's zip is $hash"; exit 2 }
Expand-Archive $zip -DestinationPath $dir -Force
Remove-Item $zip -Force
$src = Join-Path $dir 'VirtualDisplayDriver'
$sig = Get-AuthenticodeSignature "$src\mttvdd.cat"
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'CN=SignPath Foundation') { "the driver's catalog is $($sig.Status)"; exit 3 }
$store = New-Object Security.Cryptography.X509Certificates.X509Store('TrustedPublisher', 'LocalMachine')
$store.Open('ReadWrite'); $store.Add($sig.SignerCertificate); $store.Close()
New-Item -ItemType Directory -Force '@VDDDIR@' | Out-Null
icacls.exe '@VDDDIR@' /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-19:(OI)(CI)RX' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
$xml = [xml](Get-Content "$src\vdd_settings.xml" -Raw)
$res = $xml.vdd_settings.resolutions
$res.RemoveAll()
$r = $xml.CreateElement('resolution')
foreach ($p in @(@('width', '@W@'), @('height', '@H@'), @('refresh_rate', '60'))) { $e = $xml.CreateElement($p[0]); $e.InnerText = $p[1]; $null = $r.AppendChild($e) }
$null = $res.AppendChild($r)
$xml.Save('@VDDDIR@\vdd_settings.xml')
Add-Type -TypeDefinition ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('@DEVICE@')))
[PfDev]::Install("$src\MttVDD.inf", 'Root\MttVDD')
winget install --id GlavSoft.TightVNC --exact --version @VNCVERSION@ --scope machine --silent --source winget --accept-package-agreements `
  --accept-source-agreements --disable-interactivity --override '/quiet /norestart ADDLOCAL=Server SERVER_REGISTER_AS_SERVICE=1 SERVER_ADD_FIREWALL_EXCEPTION=0 SERVER_ALLOW_SAS=0' | Out-Null
"vnc_install=$LASTEXITCODE"
Stop-Service tvnserver -ErrorAction SilentlyContinue
$k = '@VNCKEY@'
New-Item $k -Force -ErrorAction SilentlyContinue | Out-Null
foreach ($n in @(@('AcceptRfbConnections', 1), @('RfbPort', @PORT@), @('LoopbackOnly', 1), @('AllowLoopback', 1),
                 @('AcceptHttpConnections', 0), @('UseVncAuthentication', 1), @('UseControlAuthentication', 1),
                 @('RepeatControlAuthentication', 1), @('QueryAcceptOnConnect', 0), @('BlockRemoteInput', 0),
                 @('BlockLocalInput', 0), @('RemoveWallpaper', 0), @('AlwaysShared', 1))) {
  Set-ItemProperty $k $n[0] $n[1] -Type DWord }
foreach ($n in 'Password', 'ControlPassword') {
  $b = New-Object byte[] 8; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  Set-ItemProperty $k $n $b -Type Binary }
$open = @((Get-Acl 'HKLM:\SOFTWARE\TightVNC').Access | Where-Object { $_.IdentityReference.Value -match 'Users|Everyone|Authenticated|INTERACTIVE' })
if ($open) { 'the VNC server settings are readable by users'; exit 4 }
Set-Service tvnserver -StartupType Manual
"vnc=$((Get-Item 'C:\Program Files\TightVNC\tvnserver.exe').VersionInfo.ProductVersion)"
'display-made'
""".replace("@DESK@", base64.b64encode(DESK_SOURCE.encode()).decode()).replace(
    "@DEVICE@", base64.b64encode(_DEVICE_SOURCE.encode()).decode()).replace("@DESKDIR@", DESK_DIR).replace(
    "@DESKEXE@", DESK_EXE).replace("@DESKINEXE@", DESKIN_EXE).replace("@HARNESS@", HARNESS).replace(
    "@VDDURL@", VDD_URL).replace("@VDDSHA@", VDD_SHA256).replace("@VDDDIR@", VDD_DIR).replace(
    "@W@", str(SCREEN_W)).replace("@H@", str(SCREEN_H)).replace("@VNCVERSION@", VNC_VERSION).replace(
    "@VNCKEY@", VNC_KEY).replace("@PORT@", str(VNC_PORT))

# As the box user at its desktop, once it is logged on (a display's layout is its user's to set): the virtual
# display alone, primary, at 1280x800; Windows keeps it for the next logon.
SCREEN = r"""Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices; using System.Collections.Generic; using System.Text;
public static class PfScreen {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] public struct DD { public int cb;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string Name; [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Desc;
    public int Flags; [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Id; [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Key; }
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] public struct DM {
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string Name; public short Spec, Drv, Size, Extra; public int Fields;
    public int X, Y, Orient, Fixed; public short Color, Duplex, YRes, TT, Collate; [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string Form;
    public short Logpx; public int Bpp, W, H, DFlags, Freq, a, b, c, d, e, f, g, h; }
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern bool EnumDisplayDevices(string dev, int i, ref DD dd, int flags);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int ChangeDisplaySettingsEx(string dev, ref DM dm, IntPtr hwnd, int flags, IntPtr param);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int ChangeDisplaySettingsEx(string dev, IntPtr dm, IntPtr hwnd, int flags, IntPtr param);
  static DM New() { var dm = new DM(); dm.Size = (short)Marshal.SizeOf(typeof(DM)); return dm; }
  public static string Only(string match, int w, int h) {
    string target = null; var others = new List<string>();
    for (int i = 0; ; i++) { var dd = new DD(); dd.cb = Marshal.SizeOf(dd); if (!EnumDisplayDevices(null, i, ref dd, 0)) break;
      if ((dd.Flags & 8) != 0) continue;
      if (dd.Desc.IndexOf(match, StringComparison.OrdinalIgnoreCase) >= 0) target = dd.Name; else others.Add(dd.Name); }
    if (target == null) return "no display matches " + match;
    var dm = New(); dm.W = w; dm.H = h; dm.Fields = 0x80000 | 0x100000 | 0x20;
    var res = new StringBuilder("primary=" + ChangeDisplaySettingsEx(target, ref dm, IntPtr.Zero, 0x1 | 0x10 | 0x10000000, IntPtr.Zero));
    foreach (var o in others) { var off = New(); off.Fields = 0x80000 | 0x100000 | 0x20;
      res.Append(" detach=" + ChangeDisplaySettingsEx(o, ref off, IntPtr.Zero, 0x1 | 0x10000000, IntPtr.Zero)); }
    res.Append(" apply=" + ChangeDisplaySettingsEx(null, IntPtr.Zero, IntPtr.Zero, 0, IntPtr.Zero));
    return res.ToString(); }
}
'@
"screen_set=$([PfScreen]::Only('Virtual Display', @W@, @H@))"
Add-Type -AssemblyName System.Windows.Forms
$all = [System.Windows.Forms.Screen]::AllScreens
"screens=$($all.Count) primary=$(($all | Where-Object Primary | ForEach-Object { "$($_.Bounds.Width)x$($_.Bounds.Height)" }))"
""".replace("@W@", str(SCREEN_W)).replace("@H@", str(SCREEN_H))

# As the administrator, at every start of a display box: the session helper, the display's settings and the VNC
# server are the image's and closed to the box user; the server gets this box's password (@STORED@, which the host
# made) and starts; it must listen on the loopback and nowhere else. Prints display-ok or display-bad: <why>.
DISPLAY_START = r"""$bad = @()
foreach ($f in '@DESKEXE@', '@DESKINEXE@', '@DESKDIR@', '@VDDDIR@', '@VDDDIR@\vdd_settings.xml', 'C:\Program Files\TightVNC\tvnserver.exe') {
  if (-not (Test-Path $f)) { $bad += "$f is missing"; continue }
  foreach ($a in (Get-Acl $f).Access) {
    if ($a.IdentityReference.Value -match 'sbx|Users|Everyone|Authenticated|INTERACTIVE' -and $a.AccessControlType -eq 'Allow' -and
        $a.FileSystemRights.ToString() -match 'Write|Modify|FullControl|ChangePermissions|TakeOwnership|Delete|CreateFiles|AppendData') {
      $bad += "$($a.IdentityReference.Value) can change $f" } } }
foreach ($a in (Get-Acl 'HKLM:\SOFTWARE\TightVNC').Access) {
  if ($a.IdentityReference.Value -match 'sbx|Users|Everyone|Authenticated|INTERACTIVE') { $bad += "$($a.IdentityReference.Value) may read the VNC server's settings" } }
$k = Get-ItemProperty '@VNCKEY@'
foreach ($n in 'LoopbackOnly', 'UseVncAuthentication', 'UseControlAuthentication') { if ($k.$n -ne 1) { $bad += "VNC $n is $($k.$n)" } }
if ($k.AcceptHttpConnections -ne 0) { $bad += 'the VNC web viewer is on' }
$svc = Get-CimInstance Win32_Service -Filter "Name='tvnserver'"
if (-not $svc -or $svc.StartName -ne 'LocalSystem') { $bad += "the VNC service is $($svc.StartName)" }
if (-not $bad) {
  Set-ItemProperty '@VNCKEY@' Password ([Convert]::FromBase64String('@STORED@')) -Type Binary
  Restart-Service tvnserver -Force
  $on = $null
  foreach ($i in 1..40) { $on = @(Get-NetTCPConnection -State Listen -LocalPort @PORT@ -ErrorAction SilentlyContinue); if ($on) { break }; Start-Sleep -Milliseconds 250 }
  $where = @($on | ForEach-Object LocalAddress | Sort-Object -Unique)
  if (-not $on) { $bad += 'the VNC server is not listening' }
  elseif ($where -join ',' -ne '127.0.0.1') { $bad += "the VNC server listens on $($where -join ',')" } }
$look = (& '@DESKEXE@' procs | Out-String) | ConvertFrom-Json
if ($look.error) { $bad += "the session helper: $($look.error)" }
elseif ($look.sid -ne 'S-1-5-18' -or $look.session -lt 1) { $bad += "the session helper ran as $($look.sid) in session $($look.session)" }
if ($bad) { 'display-bad: ' + ($bad -join '; ') } else { "display-ok session=$($look.session)" }
""".replace("@DESKEXE@", DESK_EXE).replace("@DESKINEXE@", DESKIN_EXE).replace("@DESKDIR@", DESK_DIR).replace(
    "@VDDDIR@", VDD_DIR).replace("@VNCKEY@", VNC_KEY).replace("@PORT@", str(VNC_PORT))


def new_vnc_password() -> str:
    """Eight characters, what VNC authentication uses of a password."""
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))


def display_start(password: str) -> str:
    """DISPLAY_START for a box whose VNC password is `password` (only its stored form is in the script)."""
    return DISPLAY_START.replace("@STORED@", base64.b64encode(vnc_stored_password(password)).decode())


# ---------------------------------------------------------------- the session helper


def desk(box: WindowsBox, *args: str, timeout_s: int = 90) -> dict[str, Any]:
    """desk.exe's answer as the administrator runs it; {"error": why} when there is none."""
    code, out, err = box._admin("& '" + DESK_EXE + "' " + " ".join(args), timeout_s)
    line = next((ln for ln in reversed(out.strip().splitlines()) if ln.startswith("{")), "")
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return {"error": f"the session helper said nothing readable (exit {code}): {(out + err).strip()[-200:]}"}
    return data if isinstance(data, dict) else {"error": "the session helper's answer is not an object"}


def _theirs(box: WindowsBox, rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """{pid: [start, image]} of the box user's processes among `rows`, without pickfit's own: job.exe and the shell
    it holds ready (its child)."""
    jobs = {str(r["pid"]) for r in rows if str(r.get("exe", "")).lower() == JOB_EXE.lower()}
    return {str(r["pid"]): [str(r.get("start", "")), str(r.get("exe", ""))] for r in rows
            if r.get("sid") == box.user_sid and r.get("pid") and str(r["pid"]) not in jobs
            and str(r.get("ppid", "")) not in jobs}


def procs(box: WindowsBox) -> dict[str, list[str]] | None:
    """The box user's processes in its session at the console: {pid: [start time, image]}; None if not listed."""
    data = desk(box, "procs")
    return None if "error" in data else _theirs(box, data.get("procs") or [])


def session_procs(box: WindowsBox) -> dict[str, list[str]]:
    """The box user's desktop session as it is when the box starts (Explorer, its shell parts): what a stop
    leaves. pickfit's own job.exe and the shell it holds ready are not counted (procs leaves them out), so they
    are neither stopped nor taken for the app's."""
    found = procs(box)
    if found is None:
        raise BoxError("could not list the box user's desktop session")
    return found


def _shell(image: str) -> bool:
    low = image.lower()
    return low in SHELL or low.startswith(SHELL_DIRS)


def stop(box: WindowsBox) -> tuple[bool, str]:
    """Stop every process of the box user's outside its desktop session (SHELL aside), in rounds; (whether none
    is left, the line saying so)."""
    baseline = box.session or {}
    found = 0
    for round_ in range(STOP_ROUNDS):
        now = procs(box)
        if now is None:
            return False, "PICKFIT_KILL_FAILED the box user's processes could not be listed"
        left = {pid: v for pid, v in now.items() if baseline.get(pid, [None])[0] != v[0] and not _shell(v[1])}
        if round_ == 0:
            found = len(left)
        if not left:
            return True, f"PICKFIT_KILLED {round_} found {found}"
        box._admin("Stop-Process -Force -ErrorAction SilentlyContinue -Id " + ",".join(sorted(left)), 60)
        _sleep(0.2)
    survivors = sorted({v[1] or "?" for pid, v in (procs(box) or {}).items()
                        if baseline.get(pid, [None])[0] != v[0] and not _shell(v[1])})
    return False, "PICKFIT_KILL_FAILED " + json.dumps(survivors[:20])


def stop_box_user(box: WindowsBox) -> ExecResult:
    """gui.stop_box_user for a Windows box: PICKFIT_KILLED when nothing of the box user's is left outside its
    desktop session."""
    ok, line = stop(box)
    return ExecResult(command="stop", exit_code=0 if ok else 1, stdout=line, stderr="", seconds=0.0, timed_out=False)


# ---------------------------------------------------------------- a launch


@dataclass
class WinGuiLaunch(GuiLaunch):
    """gui.GuiLaunch that names its display, so the run records the Windows desktop and not Xvfb."""

    display: str = DISPLAY_NOTE


def _win(launch: GuiLaunch) -> WinGuiLaunch:
    return WinGuiLaunch(**{k: getattr(launch, k) for k in GuiLaunch.__dataclass_fields__})


def start_script(command: str, tag: str | int) -> str:
    """PowerShell 7 as the box user: the command in a PowerShell of its own, detached, its output in the box user's
    .pickfit-gui folder; prints the pid."""
    from pickfit.verify.vbox_box import encode_ps

    log = f"{APP_LOG_DIR}\\{tag}.log"
    return (f"New-Item -ItemType Directory -Force {APP_LOG_DIR} | Out-Null; "
            f"$p = Start-Process -FilePath (Get-Process -Id $PID).Path -ArgumentList '-NoLogo','-NoProfile',"
            f"'-NonInteractive','-EncodedCommand','{encode_ps(command)}' -RedirectStandardOutput \"{log}\" "
            f"-RedirectStandardError \"{log}.err\" -WindowStyle Hidden -PassThru; \"started $($p.Id)\"")


def _visible(w: dict[str, Any]) -> tuple[int, int]:
    """How much of a window is on the screen: (width, height)."""
    x, y, wd, ht = (int(w.get(k) or 0) for k in ("x", "y", "width", "height"))
    return max(0, min(x + wd, SCREEN_W) - max(x, 0)), max(0, min(y + ht, SCREEN_H) - max(y, 0))


def look(box: WindowsBox, before: dict[str, list[str]]) -> tuple[dict[str, list[str]], list[GuiWindow],
                                                                     list[GuiWindow], str | None, str | None]:
    """(the box user's new processes that are not Windows' own, the app's windows, other windows, why pickfit
    could not look, a note on what the screenshot cannot show)."""
    data = desk(box, "look")
    if "error" in data:
        return {}, [], [], f"pickfit could not list the windows on screen: {data['error']}", None
    now = _theirs(box, data.get("procs") or [])
    mine = {pid: v for pid, v in now.items()
            if before.get(pid, [None])[0] != v[0] and not v[1].lower().startswith(WINDOWS_OWN)}
    exes = {str(r["pid"]): str(r.get("exe", "")) for r in data.get("procs") or [] if r.get("pid")}
    own: list[GuiWindow] = []
    other: list[GuiWindow] = []
    hidden: set[str] = set()
    for w in data.get("windows") or []:
        if w.get("cloaked") or w.get("class") in SHELL_CLASSES:
            continue
        vw, vh = _visible(w)
        if not (vw and vh):
            continue
        pid = str(w.get("pid"))
        info = GuiWindow(id=str(w.get("hwnd", "")), title=str(w.get("title") or "")[:200], width=int(w["width"]),
                         height=int(w["height"]), x=int(w["x"]), y=int(w["y"]), pid=int(w["pid"]),
                         client=(exes.get(pid, "").rsplit("\\", 1)[-1] or None))
        ok = pid in mine and not w.get("iconic") and vw >= gui.MIN_WIDTH and vh >= gui.MIN_HEIGHT
        (own if ok else other).append(info)
        if ok and int(w.get("affinity") or 0) in HIDDEN_FROM_CAPTURE:
            hidden.add(HIDDEN_FROM_CAPTURE[int(w["affinity"])])
    note = (f"the app asks Windows to keep its window out of screenshots ({', '.join(sorted(hidden))}): pickfit's "
            "screenshot and the operator cannot see it; if the app has an option to allow screen capture, launch "
            "it with that" if hidden else None)
    return mine, own, other, None, note


def watch(box: WindowsBox, before: dict[str, list[str]], wait_s: int, settle_s: float | None = None, *,
          sleep: Any = None) -> GuiLaunch:
    """Look about once a second until a window of the app's own has stayed settle_s, the app has gone, or the
    wait runs out."""
    settle_s = gui.SETTLE_S if settle_s is None else settle_s
    sleep = sleep or _sleep
    began, first = time.monotonic(), None
    problem = note = None
    while True:
        mine, own, other, problem, note = look(box, before)
        if problem:
            break
        elapsed = time.monotonic() - began
        if own and first is None:
            first = elapsed
        if first is not None and elapsed >= first + settle_s:
            break
        if (not mine and elapsed >= EARLY_EXIT_S) or elapsed >= wait_s + (settle_s if first is not None else 0):
            break
        sleep(POLL_S)
    if problem:
        return GuiLaunch(tier="none", error=problem)
    tier = "window" if own else "process_alive" if mine else "none"
    return GuiLaunch(tier=tier, windows=own, other_windows=other[:5],
                     processes=sorted({v[1].rsplit("\\", 1)[-1] for v in mine.values()})[:12], alive=bool(mine),
                     seconds_to_window=None if first is None else round(first, 1), error=note)


@dataclass
class WinOpened:
    """An app started on the desktop and watched until its window showed (or the wait ran out); still running.
    What gui.Opened is to the Linux loop, with the screenshot pickfit already took over VNC."""

    shown: WinGuiLaunch
    png: bytes | None
    seconds: float
    timed_out: bool
    stopped: int = 0  # processes of the box user's an earlier start left, stopped before this one


def open_app(box: WindowsBox, command: str, tag: str | int, wait_s: int, *, timeout_s: int | None = None
             ) -> WinOpened:
    """Start the app as the box user at its desktop, watch for a window of its own and take the screenshot
    (whatever the tier, so a failed launch shows what was on screen). The app keeps running: close_app stops it."""
    wait_s = max(1, min(int(wait_s), gui.WAIT_MAX_S))
    if not box.display or box.session is None:
        raise ValueError("a Windows GUI launch needs a WindowsBox made with display=True")
    began = time.monotonic()
    ok, line = stop(box)  # a copy left running would take the launch
    stopped = int(m.group(1)) if ok and (m := re.search(r"found (\d+)", line)) else 0
    before = procs(box)
    started = box.exec(start_script(command, tag), 60)
    if before is None or started.exit_code != 0 or "started" not in started.stdout:
        why = "no process snapshot" if before is None else (started.stderr or started.stdout).strip()[-300:]
        shown: GuiLaunch = GuiLaunch(tier="none", error=f"the launch could not start: {why}")
        timed_out = started.timed_out
    else:
        shown = watch(box, before, wait_s)
        timed_out = False
    shot: bytes | None = None
    try:
        shot = box.screen().screenshot()
    except Exception as err:  # gui_operate.DisplayError: the VNC session failed
        shown.error = "; ".join(filter(None, [shown.error, f"the VNC screenshot failed: {err}"]))
    if shot is not None:
        shown.shot_bytes, shown.shot_sha256 = len(shot), hashlib.sha256(shot).hexdigest()
    return WinOpened(shown=_win(shown), png=shot, seconds=round(time.monotonic() - began, 2), timed_out=timed_out,
                     stopped=stopped)


def close_app(box: WindowsBox, opened: WinOpened, tag: str | int) -> tuple[bytes | None, bool]:
    """Stop every process of the box user's outside its desktop session and read the app's log; (the launch's
    screenshot, whether something of the box user's survived the stop). Updates opened.shown in place."""
    shown = opened.shown
    ok, line = stop(box)
    if not ok:  # something the box user started outlived the launch: nothing about it counts
        shown.error = "; ".join(filter(None, [shown.error, f"box-user processes survived the stop: {line}"]))
    shown.log_tail = log_tail(box, tag)
    return (opened.png if ok else None), not ok


def log_tail(box: WindowsBox, tag: str | int) -> str:
    got = box.exec(f"Get-Content \"{APP_LOG_DIR}\\{tag}.log\",\"{APP_LOG_DIR}\\{tag}.log.err\" -Tail 60 "
                   "-ErrorAction SilentlyContinue | Out-String -Width 400", 30)
    return got.stdout[-3000:] if got.exit_code == 0 else ""


def observation(launch: GuiLaunch, *, kept: bool = False, stopped: int = 0) -> str:
    """pickfit's own lines (stdout): what the agent cites and the replay checks. Nothing the app chooses."""
    meaning = {"window": "a window of the app's own process is shown",
               "process_alive": "the app is still running but showed no window of its own",
               "none": "the app showed no window and is not running"}[launch.tier]
    lines = [f"gui tier: {launch.tier} ({meaning})"]
    if stopped:
        lines.append(f"pickfit first stopped {stopped} process(es) of the box user's an earlier start left running")
    for i, w in enumerate(launch.windows, start=1):
        lines.append(f"window {i}: {w.width}x{w.height} at {w.x},{w.y} (pid {w.pid})")
    if launch.other_windows:
        lines.append(f"{len(launch.other_windows)} other window(s) not counted (Windows' own, from before the launch, "
                     "or too small)")
    if launch.seconds_to_window is not None:
        lines.append(f"first window after {launch.seconds_to_window}s")
    if launch.error:
        lines.append(f"note: {launch.error}")
    lines.append("pickfit took a screenshot of the desktop over VNC" + (
        " and left the app running, to operate it." if kept else
        ", then stopped every process of the box user outside its desktop session."))
    return "\n".join(lines)


def app_facts(launch: GuiLaunch) -> str:
    """What the app set (stderr, as data): window titles and owners, process names, its output."""
    lines = [gui.app_facts(launch)]
    if launch.windows:
        lines.append("--- window owners, as the app names its program ---")
        lines += [f"window {i} owner: {w.client!r}" for i, w in enumerate(launch.windows, start=1)]
    return "\n".join(lines).rstrip()


def launch(box: WindowsBox, command: str, tag: str | int, wait_s: int, *, timeout_s: int | None = None,
           keep_running: bool = False) -> tuple[ExecResult, GuiLaunch, bytes | None]:
    """Launch on the box's desktop; (the record to keep, what it showed, the screenshot PNG). Only a launch at tier
    window passes (exit 0); a failed one still keeps its screenshot."""
    opened = open_app(box, command, tag, wait_s, timeout_s=timeout_s)
    shown, shot, survived = opened.shown, opened.png, False
    if not keep_running:
        shot, survived = close_app(box, opened, tag)
    else:
        shown.log_tail = log_tail(box, tag)
    code = 0 if shown.tier == "window" and shot is not None and not opened.timed_out and not survived else 1
    result = ExecResult(command=command, exit_code=code,
                        stdout=observation(shown, kept=keep_running, stopped=opened.stopped),
                        stderr=app_facts(shown), seconds=opened.seconds, timed_out=opened.timed_out)
    return result, shown, shot


# ---------------------------------------------------------------- the screen


class WinVncDisplay:
    """The box's screen as pickfit drives it from the host: the operating loop's Display (gui_operate.Display).

    One VNC connection through the administrator's ssh connection, kept open: screenshot -> PNG once the screen has
    settled, click(x, y, count), type_text, key, scroll, clipboard. Key names are X keysyms and `+` combinations with
    Windows' modifiers (ctrl, alt, shift, win). A VNC failure is the loop's DisplayError.
    """

    os = "windows"

    def __init__(self, box: WindowsBox) -> None:
        self._box = box
        self._client: VncClient | None = None
        self._port: int | None = None

    def _connected(self) -> VncClient:
        if self._client is not None and self._client.sock is not None:
            return self._client
        if self._port is None:
            self._port = self._box.machine.forward(VNC_PORT)
        client = VncClient("127.0.0.1", self._port, self._box.vnc_password or "", compress=True,
                           modifiers=WINDOWS_MODIFIERS).connect()
        # The server's first answer on a connection is the screen's size alone: its first frame is black.
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not any(client.frame_now()[2][::4097]):
            time.sleep(0.1)
        self._client = client
        return client

    def _do(self, what: str, fn: Any, *args: Any) -> Any:
        from pickfit.verify.gui_operate import DisplayError

        try:
            return fn(*args)
        except (VncError, OSError, ValueError, BoxError) as err:
            if self._client is not None:
                self._client.close()
            raise DisplayError(f"{what} over VNC failed: {err}") from err

    @property
    def size(self) -> tuple[int, int]:
        client = self._do("connecting", self._connected)
        return client.width, client.height

    @property
    def width(self) -> int:
        return self.size[0]

    @property
    def height(self) -> int:
        return self.size[1]

    def _settled(self) -> bytes:
        client = self._connected()
        w, h, frame = client.frame_now()
        deadline = time.monotonic() + SETTLE_MAX_S
        while time.monotonic() < deadline:
            time.sleep(SETTLE_GAP_S)
            w, h, later = client.frame_now()
            if later == frame:
                break
            frame = later
        return png(w, h, frame)

    def screenshot(self) -> bytes:
        """The whole screen as PNG once two frames SETTLE_GAP_S apart agree (at most SETTLE_MAX_S)."""
        return self._do("screenshot", self._settled)

    def click(self, x: int, y: int, count: int = 1) -> None:
        self._do("click", lambda: self._connected().click(x, y, count=max(1, min(int(count), 3))))

    def double_click(self, x: int, y: int) -> None:
        self.click(x, y, 2)

    def right_click(self, x: int, y: int) -> None:
        self._do("right-click", lambda: self._connected().click(x, y, button="right"))

    def type_text(self, text: str) -> None:
        self._do("typing", lambda: self._connected().type_text(text))

    def key(self, name: str) -> None:
        self._do(f"key {name}", lambda: self._connected().key(name))

    def scroll(self, x: int, y: int, direction: str) -> None:
        self._do("scroll", lambda: self._connected().scroll(x, y, direction, notches=3))

    def clipboard(self) -> bytes | None:
        """The box user's clipboard as text, read by the session helper (None when it holds no text)."""
        data = desk(self._box, "clipboard")
        text = data.get("clipboard") if "error" not in data else None
        return text.encode() if isinstance(text, str) and text else None

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
        if self._port is not None:
            try:
                self._box.machine.cancel_forward(self._port, VNC_PORT)
            except Exception:  # the connection is gone with the machine
                pass
            self._port = None
