I couldn't find one open-source MCP server that does everything you listed. Below is the closest free setup, built from small open-source MCP servers, with the coding agent covering the gaps. I haven't installed or tested any of these. pickfit's tested catalogue had nothing that matched, and everything here comes from the projects' READMEs. Read each repo before you trust it with your Play credentials.

## Main recommendation: App Publisher MCP plus two helpers

| Job | Tool | Status |
|---|---|---|
| Screenshots, icon, artwork, listing text, privacy-policy draft, Play listing and image upload, `publish_android` | **[App Publisher MCP](https://github.com/seungmanchoi/app-publisher-mcp)** (MIT, npm) | Main tool |
| Tracks, promote to production, staged rollout, halt a rollout, release status | **[mcp-upload-app](https://github.com/brunosemfio/mcp-upload-app)** (Apache-2.0, macOS only) | Optional, better release control |
| Samsung Galaxy Store (and Huawei AppGallery) | **[app-store-publisher-mcp](https://github.com/qalvinahmad/app-store-publisher-mcp)** (MIT) | Optional. Glama marks it inactive and its tools are thin API wrappers |
| F-Droid | No API exists. You submit a merge request to `fdroiddata` | Agent-assisted, done by hand |

**Why App Publisher MCP comes first:** it covers the most of your list:
- It captures screenshots from a running emulator with Maestro and adds device frames and headlines.
- It generates an icon and the 512×512 Play icon.
- It generates artwork with Gemini. Upload a 1024×500 feature graphic with `playstore_upload_image`, since there's no dedicated feature-graphic tool.
- `generate_store_listing` drafts listing text and a privacy policy and gives a guide to the content rating.
- It writes metadata into the `fastlane/metadata/` folder and checks it with `validate_metadata`.
- It publishes through fastlane supply.

### Gaps and how to fill them (my assessment)

1. **Privacy policy inferred from the code, ads detection, Data safety answers.** No MCP server I found analyses the code for this. The agent (Claude Code) can do it well by reading `AndroidManifest.xml` (INTERNET permission, AD_ID permission), the Gradle dependencies (AdMob, Firebase, Crashlytics, Facebook SDK and so on) and the network calls. You then feed what it finds into `generate_store_listing`. You still have to host the policy at a public URL.
2. **Age rating.** Google has no API for the IARC questionnaire, so it's always a human step in Play Console. The best you can get is the agent pre-filling a checklist of answers so the clicking takes about two minutes.
3. **Creating a new app.** Google's API can't create an app. You create it in Play Console and upload the first build by hand. fastlane supply needs that first build before it can connect.
4. **Metadata layout.** The README lists fields like `subtitle` and `keywords`, which are iOS names. Android fastlane uses `title.txt`, `short_description.txt`, `full_description.txt`, `changelogs/<versionCode>.txt` and `images/{featureGraphic.png,phoneScreenshots/}` under `fastlane/metadata/android/<locale>/`. Check what it writes. If it's the iOS layout, have the agent convert it. This matters because **F-Droid reads that same Android fastlane layout straight from your repo**, so one copy of the metadata serves both stores.
5. **Fixing problems automatically.** Nothing does this as a feature. In practice it's the agent loop: read the supply or Play API error, fix it (version code, a text field too long, image size), then retry.
6. **Cost and privacy.** The tools are free. Image generation needs a Gemini API key, and Google offers a free tier. Your app's descriptions are sent to Google when it generates images.

## Install (macOS)

I'm assuming you use Claude Code on macOS (your system reports Darwin) with the Android SDK and an emulator already installed.

**1. Prerequisites**
```bash
brew install node fastlane
# Maestro (screenshots): its official installer pipes a script into bash. Read it first:
curl -fsSL "https://get.maestro.mobile.dev" | bash
```

**2. Google Play service account** (done in the browser)
- In Google Cloud, enable the Google Play Android Developer API and create a service account with a JSON key.
- In Play Console, go to Users & permissions, invite that account and give it release permissions.
- Store the key somewhere safe, e.g. `~/.config/google-play-console/play.json`, and run `chmod 600` on it.

**3. Add the MCP servers**
```bash
claude mcp add app-publisher -e GEMINI_API_KEY=YOUR_KEY -- npx @seungmanchoi/app-publisher-mcp

# optional: release/rollout control
claude mcp add --scope user upload-app \
  --env GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/google-play-console/play.json \
  -- uvx --from git+https://github.com/brunosemfio/mcp-upload-app.git upload-app-mcp   # needs `brew install uv`

# optional: Galaxy Store (needs Samsung commercial seller status)
git clone https://github.com/qalvinahmad/app-store-publisher-mcp.git
cd app-store-publisher-mcp && npm install && cp .env.example .env   # set SAMSUNG_SERVICE_ACCOUNT_ID / SAMSUNG_PRIVATE_KEY
claude mcp add app-store-publisher -- node "$PWD/index.js"
```

## First run

Open your app's project in Claude Code and work through these in order:

1. **Set up:** "Run `get_status`, then `configure_playstore` with my key at `~/.config/google-play-console/play.json`, then `setup_fastlane` for this Android project."
2. **Audit:** "Read the manifest, Gradle dependencies and network code. Tell me whether the app shows ads, which third-party SDKs receive user data, and give me draft answers for Data safety and the IARC questionnaire."
3. **Assets:** "Start the emulator and take store screenshots with `maestro_store_screenshot`. Generate an icon if none exists. Create a 1024×500 feature graphic. Run `generate_store_listing` using the audit results, and write everything under `fastlane/metadata/android/en-US/` in the Android fastlane layout."
4. **By hand, one time only:** create the app in Play Console, upload the first AAB, and fill in content rating, Data safety, the ads declaration and the privacy-policy URL from the drafts.
5. **Release:** "Build the release AAB, upload it to the internal track, push the listing and images, then promote to production at a 20% rollout." If anything fails, have the agent read the error, fix it and retry.
6. **F-Droid (optional):** "Draft a `metadata/<applicationId>.yml` for fdroiddata, check that the build has no proprietary dependencies, and prepare the merge request." Your app needs a FOSS licence and must build from source with no proprietary SDKs. That usually means no AdMob or Firebase, or a separate FOSS build flavour.

## Alternatives
- **[fastlane-mcp (pampas93)](https://github.com/pampas93/fastlane-mcp):** wraps Gradle and fastlane with a per-app `fastlane-mcp.yaml`. It's narrower (build and publish only), has 0 stars and no clear licence.
- **[google-play-mcp (roadhero)](https://github.com/roadhero/google-play-mcp):** calls the Play API directly with no fastlane. It's read-only for now and publishing is on its roadmap.
- **Plain fastlane** (`supply`, `screengrab`) without MCP: the most mature option, but it fills in nothing for you, as you said.

Sources:
- [App Publisher MCP](https://github.com/seungmanchoi/app-publisher-mcp)
- [mcp-upload-app](https://github.com/brunosemfio/mcp-upload-app)
- [App Store Publisher MCP (Glama)](https://glama.ai/mcp/servers/qalvinahmad/app-store-publisher-mcp)
- [fastlane-mcp (LobeHub)](https://lobehub.com/mcp/pampas93-fastlane-mcp)
- [google-play-mcp](https://github.com/roadhero/google-play-mcp)
- [vibe-coder-server: Publishing To Stores](https://github.com/siamakerlab/vibe-coder-server/wiki/Publishing-To-Stores)
- [fastlane upload_to_play_store docs](https://docs.fastlane.tools/actions/upload_to_play_store/)
- [Play Console Help: Content ratings](https://support.google.com/googleplay/android-developer/answer/9898843?hl=en)
- [Filling out App Content declarations](https://webtoapp.design/blog/configure-app-content-in-play-console)
- [Google Play Store listing requirements (PlayAudit)](https://playaudit.app/blog/google-play-listing-requirements)
- [F-Droid forum: how to publish](https://forum.f-droid.org/t/how-to-publish-my-app-on-f-droid/198)
- [How to publish an Android app on F-Droid (DEV)](https://dev.to/gargpadmakar/how-to-publish-an-android-app-on-f-droid-complete-step-by-step-guide-3j2p)
- [Best Fastlane MCP servers (Glama)](https://glama.ai/mcp/servers/integrations/fastlane)