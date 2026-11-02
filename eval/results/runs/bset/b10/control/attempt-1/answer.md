I recommend **adb-mcp** ([iksnerd/adb-mcp](https://github.com/iksnerd/adb-mcp)). It's MIT-licensed, free, and a standard stdio MCP server written in Go. One caveat applies to every option: no MCP server finds bugs or judges quality on its own. The server gives the LLM tools to build, install, tap, type, take screenshots, record the screen, read logcat and run tests. Your MCP client's LLM (Claude Code, Codex, Cursor, etc.) does the exploring and decides what counts as a bug. That's enough to automate your loop.

## Why adb-mcp fits best

From its README, which I read but haven't tested:

- **Build and test:** Gradle `assembleDebug`, a one-step `build_and_run`, unit tests, instrumented tests, JaCoCo coverage reports, and builds that run in the background.
- **Install and run:** install and uninstall apps, launch them, read logcat.
- **Test like a person:** screenshots, the UI element tree, tap/swipe/type, and **screen recording**.
- **Sensors:** `set_sensor` (accelerometer, light, etc.) and `rotate_screen`, plus lock-screen and biometric helpers. **These only work on emulators.** On a physical phone, adb can't fake sensor readings, so tilting still has to be done by hand or with a test-only hook in your app.
- **Devices:** works with real phones over USB or Wi-Fi and with emulators. Every tool accepts an optional device `serial`. **It doesn't promise true parallel runs.** To get them, I'm assuming you'd start one agent or session per device, each tied to its own serial, or ask one agent to switch between serials.
- **Maturity:** about 115 commits, versioned releases (v0.24.x), CI. It's young but actively maintained.

## Install and first run (macOS)

1. Prerequisites: install the Android SDK with `platform-tools` (adb) and `emulator`, set `ANDROID_HOME`, and create at least one AVD. Building your app also needs a JDK, usually 17 or later.
2. Install the server. Pick one:
   - From source (needs Go 1.26+): `go install github.com/iksnerd/adb-mcp/cmd/adb-mcp@latest`
   - The installer: `curl -fsSL https://raw.githubusercontent.com/iksnerd/adb-mcp/main/install.sh | sh`. Read the script before piping it to `sh`.
3. Register it with your client:
   - Claude Code: `claude mcp add adb -- adb-mcp`
   - Other clients: `{"mcpServers": {"adb": {"command": "adb-mcp"}}}`
4. Plug in your phone with USB debugging on, run `adb devices`, and accept the authorization prompt on the phone.
5. First prompt, from your project folder:
   > "List devices. Build the debug APK and install/launch it on device `<serial>`. Start a screen recording, then explore the new <feature>: tap every control, enter valid/invalid/empty text, rotate, background and resume the app. Check logcat for crashes/ANRs after each step. Stop the recording, then write a bug list with steps to reproduce, and fix each bug, rebuild and re-verify."
6. For parallel testing, open a second session, assign it another serial (for example an emulator for the sensor tests), and give it a different area of the app to test.

## Alternatives

- **[AndroidBuildMCP](https://github.com/dev-jackson/androidbuild-mcp)** (MIT): build_app/build_run with compiler errors as file:line, tests, coverage, recording (3-minute cap), and AVD management. It has no sensor tools, and it's very new (8 commits, 0 stars). Install with `claude mcp add androidbuild -- npx -y @asjackson/androidbuild-mcp`, then ask it to run `doctor`.
- **[mobile-mcp](https://github.com/mobile-next/mobile-mcp)** (Apache-2.0): the most widely used device-control server. It supports Android and iOS, real devices and emulators, screen recording and crash logs. It **doesn't build**, so you'd pair it with Gradle in your client's shell. Install with `claude mcp add mobile-mcp -- npx -y @mobilenext/mobile-mcp@latest`.
- I also found [mcp-android-emulator](https://github.com/Anjos2/mcp-android-emulator) and [android-mcp-server](https://github.com/jaye773/android-mcp-server), which both have recording but no builds. I didn't check them in detail.

## Tips

- Have the agent save each bug it finds as a repeatable test (an Espresso test or a scripted flow). Then every later round re-checks the earlier fixes, and the coverage reports give you a real "how well is it going" number.
- On a real phone, Android's built-in recorder (`adb screenrecord`) stops after about 3 minutes. Ask the agent to record in short pieces.
- You still need your manual code review at the end. These tools can confirm the app behaves correctly, not that the code is good.

Sources: [adb-mcp](https://github.com/iksnerd/adb-mcp), [androidbuild-mcp](https://github.com/dev-jackson/androidbuild-mcp), [mobile-mcp](https://github.com/mobile-next/mobile-mcp), [mcp-android-emulator](https://github.com/Anjos2/mcp-android-emulator), [android-mcp-server](https://github.com/jaye773/android-mcp-server), [android-phone-mcp](https://github.com/liush2yuxjtu/android-phone-mcp)