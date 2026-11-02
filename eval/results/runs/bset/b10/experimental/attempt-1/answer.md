## Recommendation: adb-mcp (iksnerd/adb-mcp)

**[adb-mcp](https://github.com/iksnerd/adb-mcp)** comes closest to what you asked for. It's MIT-licensed, a standard stdio MCP server, and a single Go binary. One server covers your whole loop:

| Your step | What adb-mcp provides (per its README) |
|---|---|
| Build | Gradle `assembleDebug`, plus a one-call `build_and_run` (build → install → launch) |
| Install | Install, uninstall, launch, stop and clear data |
| Test by touch | `describe_ui` (UI hierarchy), screenshots, tap/swipe/type, `run_sequence`, `verify_change` |
| Sensors / tilt | `set_sensor` (accelerometer, light, etc.) and `rotate_screen` |
| Record the screen | Screen recording, listed under "Logs & capture" |
| See how it's going | Unit and instrumented test runs with pass/fail, JaCoCo coverage reports, and logcat for crashes |
| Several devices | `list_devices`, an optional `serial` on every device tool, and `session_set_defaults` to pin a device |
| Real devices and emulators | Both. It also has emulator boot/shutdown and AVD snapshots |

**Caveats:**
- **Finding bugs is still the LLM's job.** No MCP server judges on its own whether a feature works. The server gives the agent eyes and hands (UI tree, screenshots, logcat, test results, video). The model decides what counts as a bug. You'll get better results if you tell it what "correct" looks like.
- **Sensor injection probably only works on emulators.** Faking sensor values over adb normally goes through the emulator console. On a physical phone you can usually only rotate the screen, so actual tilting may still need your hands. That's my reading of how adb works; the README doesn't say.
- **Parallel runs aren't automatic.** Each call targets a device by `serial`, so you can run tests in parallel by giving each agent or sub-agent its own device. Instrumented tests (`connectedAndroidTest`) run on every connected device anyway. I found no "run on all devices at once" orchestrator.
- **It's a small project:** about 15 stars and roughly 115 commits, with v0.24.x mentioned in its docs. Check that it's actively maintained.
- **Not verified:** pickfit has no tested entry for it, so I haven't run it. The tool names come from its README and website.

## Install (macOS, assuming Claude Code)

1. **Prerequisites:** the Android SDK with `platform-tools` (adb) and `emulator`, at least one AVD if you want emulators, and JDK 17+ for Gradle. If you already build with Android Studio, you have all of this. Make sure `adb` is on your `PATH`.
2. **Install the binary.** The README's method pipes a script into the shell:
   ```sh
   curl -fsSL https://raw.githubusercontent.com/iksnerd/adb-mcp/main/install.sh | sh
   ```
   The script checks a SHA-256 checksum and installs to `~/.local/bin`, so make sure that's on your `PATH`. If you'd rather not pipe a script into `sh`, read `install.sh` first or download the release archive from the GitHub Releases page yourself.
3. **Register it with Claude Code:**
   ```sh
   claude mcp add adb -- adb-mcp
   ```
   For other clients, use `{ "mcpServers": { "adb": { "command": "adb-mcp" } } }`.

## First run

1. On the phone, turn on Developer options → USB debugging. Plug it in and accept the RSA prompt.
2. Run `adb devices`. The phone, and any running emulator, should show up as `device`.
3. In Claude Code, try a prompt like:
   > "List devices. Pin serial `<your phone>` and project dir `<path>`. Use build_and_run for the debug build. Start a screen recording, then test the login feature: describe the UI, enter a wrong password, then a right one, and rotate the screen. After each action check logcat for crashes and exceptions. Stop recording and give me a numbered bug list with steps to reproduce."
4. For a regression safety net, ask the LLM to also write Espresso/Compose UI tests for each feature. Then the instrumented test and coverage tools can re-check old bugs on every loop, across all connected devices.

## Alternatives (all MIT, all unverified)

- **[androidbuild-mcp](https://github.com/dev-jackson/androidbuild-mcp)** (`claude mcp add androidbuild -- npx -y @asjackson/androidbuild-mcp`) has the build-to-test loop with compact `file:line` compiler errors, `build_run`, unit and instrumented tests, and video recording capped at 3 minutes. It doesn't mention sensors or multi-device support, and it's very new (8 commits).
- **[jaye773/android-mcp-server](https://github.com/jaye773/android-mcp-server)** (Python) handles multiple devices and parallel recording and log sessions well. It has no build or test tools, so you'd pair it with something else.

Sources:
- [iksnerd/adb-mcp](https://github.com/iksnerd/adb-mcp)
- [adb-mcp.com](https://adb-mcp.com/)
- [dev-jackson/androidbuild-mcp](https://github.com/dev-jackson/androidbuild-mcp)
- [jaye773/android-mcp-server](https://github.com/jaye773/android-mcp-server)
- [mcpservers.org – adb-mcp](https://mcpservers.org/servers/iksnerd/adb-mcp)