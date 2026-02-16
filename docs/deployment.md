# Deployment Guide

## macOS Service Deployment (launchd)

The Slack Codex Bridge can run as a background service on macOS using launchd.

> **Note:** The deployment files (`*.plist`, `deploy.sh`, `undeploy.sh`) are machine-specific and not committed to the repository. You'll need to create them locally using the templates below.

### Prerequisites

- macOS system with homebrew and `uv` installed
- Slack app credentials configured in `.envrc`
- Project directory (e.g., `/Users/brian/src/messaging`)

### Setup

1. **Create the launchd plist file** (see template below)
2. **Create deployment scripts** (see templates below)
3. **Update paths and credentials** to match your environment

### Quick Start

Once you've created the deployment files locally:

1. **Deploy the service:**
   ```bash
   ./deploy.sh
   ```

2. **Check the logs:**
   ```bash
   tail -f logs/slack-codex-bridge.log
   tail -f logs/slack-codex-bridge.error.log
   ```

3. **Undeploy/stop the service:**
   ```bash
   ./undeploy.sh
   ```

### How It Works

The deployment creates a **launchd user agent** that:
- Runs `uv run slack-codex-bridge` in the background
- Automatically restarts if the process crashes (with 30-second throttle)
- Starts on login/boot
- Loads all environment variables from `.envrc`
- Logs to `logs/slack-codex-bridge.log` and `logs/slack-codex-bridge.error.log`

### Manual Commands

**Restart the service:**
```bash
launchctl kickstart -k gui/$(id -u)/com.yourname.slack-codex-bridge
```

**Check service status:**
```bash
launchctl list | grep slack-codex-bridge
```

**View live logs:**
```bash
tail -f logs/slack-codex-bridge.log
```

**Stop without undeploying:**
```bash
launchctl unload ~/Library/LaunchAgents/com.yourname.slack-codex-bridge.plist
```

**Start again:**
```bash
launchctl load ~/Library/LaunchAgents/com.yourname.slack-codex-bridge.plist
```

### File Templates

#### launchd plist (e.g., `com.yourname.slack-codex-bridge.plist`)

Create a plist file with your specific configuration:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yourname.slack-codex-bridge</string>

    <key>ProgramArguments</key>
    <array>
        <string>/path/to/uv</string>
        <string>run</string>
        <string>slack-codex-bridge</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/path/to/messaging</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>SLACK_APP_TOKEN</key>
        <string>your-app-token</string>
        <key>SLACK_BOT_TOKEN</key>
        <string>your-bot-token</string>
        <key>SLACK_SIGNING_SECRET</key>
        <string>your-signing-secret</string>
        <!-- Add other env vars from .envrc -->
    </dict>

    <key>StandardOutPath</key>
    <string>/path/to/messaging/logs/slack-codex-bridge.log</string>

    <key>StandardErrorPath</key>
    <string>/path/to/messaging/logs/slack-codex-bridge.error.log</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>ThrottleInterval</key>
    <integer>30</integer>
</dict>
</plist>
```

**Important:**
- Find your `uv` path with `which uv`
- Copy all environment variables from your `.envrc`
- Update all paths to match your system

#### deploy.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

PLIST_FILE="com.yourname.slack-codex-bridge.plist"
PLIST_SOURCE="$(pwd)/${PLIST_FILE}"
PLIST_DEST="${HOME}/Library/LaunchAgents/${PLIST_FILE}"
LOGS_DIR="$(pwd)/logs"

echo "🚀 Deploying Slack Codex Bridge service..."

mkdir -p "$LOGS_DIR"
mkdir -p "${HOME}/Library/LaunchAgents"

if launchctl list | grep -q "com.yourname.slack-codex-bridge"; then
    echo "⚠️  Service already loaded. Unloading first..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    sleep 1
fi

cp "$PLIST_SOURCE" "$PLIST_DEST"
launchctl load "$PLIST_DEST"

echo "✅ Service deployed successfully!"
```

Make it executable: `chmod +x deploy.sh`

#### undeploy.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

PLIST_FILE="com.yourname.slack-codex-bridge.plist"
PLIST_DEST="${HOME}/Library/LaunchAgents/${PLIST_FILE}"

echo "🛑 Undeploying Slack Codex Bridge service..."

if [ ! -f "$PLIST_DEST" ]; then
    echo "❌ Service plist not found"
    exit 1
fi

launchctl unload "$PLIST_DEST" 2>/dev/null || true
rm "$PLIST_DEST"

echo "✅ Service undeployed successfully!"
```

Make it executable: `chmod +x undeploy.sh`

### Configuration

The service configuration is in your plist file:

- **Label:** Unique reverse-domain identifier (e.g., `com.yourname.slack-codex-bridge`)
- **Program:** Path to `uv` + `run slack-codex-bridge`
- **Working Directory:** Your project directory
- **Logs:** `logs/` directory in the project root
- **Restart Policy:** KeepAlive with 30-second throttle

### Updating the Service

After making code changes:

1. Code is automatically reloaded on next command (or restart):
   ```bash
   launchctl kickstart -k gui/$(id -u)/com.yourname.slack-codex-bridge
   ```

After changing environment variables:

1. Edit your plist file
2. Redeploy:
   ```bash
   ./deploy.sh
   ```

### Troubleshooting

**Service won't start:**
- Check logs in `logs/slack-codex-bridge.error.log`
- Verify `uv` path in plist matches `which uv` output
- Ensure all Slack tokens are valid in the plist

**Service keeps restarting:**
- Check error logs for Python exceptions
- Verify network connectivity
- Check Slack API token validity

**Can't find service:**
```bash
launchctl print gui/$(id -u)/com.yourname.slack-codex-bridge
```

**Remove all traces:**
```bash
./undeploy.sh
rm -rf logs/
```
