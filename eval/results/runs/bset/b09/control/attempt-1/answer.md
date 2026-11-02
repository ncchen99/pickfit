I didn't find one open-source MCP server that does everything on your list. My recommendation is a small stack built on fastlane-format metadata:

1. **Core: [`app-publisher-mcp`](https://github.com/seungmanchoi/app-publisher-mcp)** (MIT, npm). It comes closest to what you asked for:
   - **Icons:** generates them with Gemini and exports every Android size plus the 512×512 Play icon.
   - **Screenshots:** captures them from a running emulator using Maestro, then adds device frames and headlines.
   - **Privacy policy:** drafts one with `generate_store_listing`.
   - **Content rating:** auto-detects what the app does and gives you an Android content-rating guide.
   - **Ads and data collection:** finds them from your dependencies (for example AdMob).
   - **Metadata:** writes and validates it in the fastlane format.
   - **Publishing:** uploads to Google Play through fastlane `supply` and the Play API.
2. **Samsung Galaxy Store (and Huawei): [`app-store-publisher-mcp`](https://glama.ai/mcp/servers/qalvinahmad/app-store-publisher-mcp)** (MIT). You need a Samsung Seller Portal service account, and that requires **commercial seller status**.
3. **F-Droid: you don't need an MCP server.** F-Droid doesn't accept uploaded APKs. It builds your app from source after you open a merge request to `fdroiddata`. It reads `fastlane/metadata/android/` straight from your repo, so the same metadata covers it.
4. **Optional, for more Play API coverage: [`app-publish-mcp`](https://github.com/maksym-kyryliuk/app-publish-mcp)** (MIT, 91 tools). It includes a Data safety tool, release tracks and review management. Its docs don't mention fastlane.

**Don't use for publishing:** `roadhero/google-play-mcp` is read-only for now, and `play-console-mcp` has publishing turned off.

## What still needs you (no tool gets around these)
- **First-time Play setup:** You have to create the app in Play Console yourself, and `supply` needs at least one build uploaded manually first.
- **Play Console forms:** The content-rating (IARC) questionnaire and the ads and target-audience declarations aren't fully available through the API. The MCP can work out the answers, but you click them in once, which takes about 10 minutes. After that, updates run automatically.
- **New personal developer accounts:** Google requires a closed test with 12 testers for 14 days before production.
- **Privacy policy hosting:** It needs a public URL. GitHub Pages works and is free.
- **"Free" caveat:** Image generation uses a Gemini API key. There's a free tier, but image models may need billing turned on.
- **"Auto-fix on failure":** No server does this. The agent does it: Claude Code reads the `supply` or API error, fixes the metadata or image, and runs it again. Use `supply --validate_only` for dry runs.

## Install
Assumptions: you're on macOS with Claude Code as the MCP client, and the app is a Gradle Android project.

```bash
# Prerequisites
brew install node fastlane openjdk@17      # plus Android SDK/adb (Android Studio)
curl -Ls "https://get.maestro.mobile.dev" | bash

# Core server
claude mcp add app-publisher \
  -e GEMINI_API_KEY=YOUR_KEY -e GEMINI_MODEL=gemini-2.5-flash-image \
  -- npx @seungmanchoi/app-publisher-mcp

# Samsung/Huawei (optional)
git clone https://github.com/qalvinahmad/app-store-publisher-mcp.git
cd app-store-publisher-mcp && npm install && cp .env.example .env   # set SAMSUNG_SERVICE_ACCOUNT_ID, SAMSUNG_PRIVATE_KEY
claude mcp add app-store-publisher -- node "$PWD/index.js"
```

For Google Play:
1. In Google Cloud, create a service account and download its JSON key.
2. In Play Console, go to Users & permissions and invite that account.
3. Set `json_key_file` in `fastlane/Appfile`.

## First run
1. Create the app in Play Console. Upload a signed AAB to the internal testing track by hand once.
2. Start an emulator with the app installed, open Claude Code in the project folder, and ask:
   > "Set up fastlane for this project, generate a missing icon and feature graphic, capture store screenshots with Maestro, write the listing and a privacy policy based on the app's actual network calls, SDKs and permissions, tell me the content-rating and Data safety answers, then validate the metadata."
3. Check the privacy policy and rating answers, publish the policy on GitHub Pages, and fill in the Play Console forms once.
4. Ask the agent to "publish to the internal track," then promote the release to production when it looks right.
5. For F-Droid, commit `fastlane/metadata/android/` to your repo and open an MR to `gitlab.com/fdroid/fdroiddata`. You can check the recipe locally first with `fdroid lint` and `fdroid build`.

Note that some of these projects are young, so read each one's README before giving it your Play credentials.

Sources:
- [seungmanchoi/app-publisher-mcp](https://github.com/seungmanchoi/app-publisher-mcp)
- [App Store Publisher MCP (Glama)](https://glama.ai/mcp/servers/qalvinahmad/app-store-publisher-mcp)
- [maksym-kyryliuk/app-publish-mcp](https://github.com/maksym-kyryliuk/app-publish-mcp)
- [roadhero/google-play-mcp](https://github.com/roadhero/google-play-mcp)
- [play-console-mcp](https://github.com/taimweromita505-source/play-console-mcp)
- [fastlane-mcp (PyPI)](https://pypi.org/project/fastlane-mcp/)
- [fastlane upload_to_play_store docs](https://docs.fastlane.tools/actions/upload_to_play_store/)
- [F-Droid forum: submitting an app](https://forum.f-droid.org/t/i-want-to-upload-my-android-app-on-this-store/16908)
- [F-Droid forum: how to publish](https://forum.f-droid.org/t/how-to-publish-my-app-on-f-droid/198)