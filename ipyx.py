#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
No-deps version of the server: uses Python standard library http.server instead of Flask.
Keep other logic (download, run binaries, generate sub, upload) same as previous version.
"""

import os
import sys
import json
import time
import base64
import shutil
import random
import string
import threading
import subprocess
from pathlib import Path
import requests  # still required for downloading/uploading; if you want zero-deps replace requests with urllib
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver

# Optional: psutil used for advanced process killing; if missing, fallback to pkill/taskkill
try:
    import psutil
except Exception:
    psutil = None

# --- ENV VARS ---
UPLOAD_URL = os.environ.get('UPLOAD_URL', '').strip()
PROJECT_URL = os.environ.get('PROJECT_URL', '').strip()
AUTO_ACCESS = os.environ.get('AUTO_ACCESS', 'false').lower() in ('1', 'true', 'yes')
FILE_PATH = os.environ.get('FILE_PATH', './tmp')
SUB_PATH = os.environ.get('SUB_PATH', 'sub')
PORT = int(os.environ.get('SERVER_PORT') or os.environ.get('PORT') or 3000)
UUID = os.environ.get('UUID', '9afd1229-b893-40c1-84dd-51e7ce204913')
ARGO_DOMAIN = os.environ.get('ARGO_DOMAIN', '').strip()
ARGO_AUTH = os.environ.get('ARGO_AUTH', '').strip()
ARGO_PORT = int(os.environ.get('ARGO_PORT', 8001))
CFIP = os.environ.get('CFIP', 'cdns.doon.eu.org').strip()
CFPORT = os.environ.get('CFPORT', '443').strip()
NAME = os.environ.get('NAME', '').strip()

# --- Setup ---
workdir = Path(FILE_PATH)
workdir.mkdir(parents=True, exist_ok=True)
print(f"Working dir: {workdir.resolve()}")

def generate_random_name(n=6):
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(n))

web_name = generate_random_name()
bot_name = generate_random_name()

web_path = str(workdir / web_name)
bot_path = str(workdir / bot_name)
sub_path = str(workdir / 'sub.txt')
list_path = str(workdir / 'list.txt')
boot_log_path = str(workdir / 'boot.log')
config_path = str(workdir / 'config.json')

def is_arm_arch():
    arch = os.uname().machine.lower() if hasattr(os, 'uname') else os.environ.get('PROCESSOR_ARCHITECTURE', '')
    return ('arm' in arch) or ('aarch64' in arch)

def run_shell(cmd, background=False):
    try:
        if background:
            if sys.platform == 'win32':
                p = subprocess.Popen(cmd, shell=True,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                p = subprocess.Popen(cmd, shell=True,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     preexec_fn=os.setpgrp)
            return p
        else:
            res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
            return res
    except Exception as e:
        print(f"run_shell error: {e}")
        return None

def try_kill_process_by_name(name):
    try:
        if psutil:
            for p in psutil.process_iter(attrs=['pid','name','cmdline']):
                if name in (p.info['name'] or '') or any(name in (c or '') for c in (p.info.get('cmdline') or [])):
                    try:
                        p.terminate()
                    except Exception:
                        pass
        else:
            if sys.platform == 'win32':
                run_shell(f'taskkill /f /im {name} > nul 2>&1', background=False)
            else:
                run_shell(f'pkill -f "{name}" > /dev/null 2>&1', background=False)
    except Exception:
        pass

def delete_nodes():
    if not UPLOAD_URL:
        return
    if not os.path.exists(sub_path):
        return
    try:
        with open(sub_path, 'r', encoding='utf-8') as f:
            encoded = f.read().strip()
        if not encoded:
            return
        decoded = base64.b64decode(encoded).decode('utf-8', errors='ignore')
        nodes = [line for line in decoded.splitlines() if any(proto in line for proto in ('vless://','vmess://','trojan://','hysteria2://','tuic://'))]
        if not nodes:
            return
        payload = { 'nodes': nodes }
        try:
            requests.post(f"{UPLOAD_URL.rstrip('/')}/api/delete-nodes", json=payload, timeout=6)
        except Exception:
            pass
    except Exception:
        pass

def cleanup_old_files():
    try:
        for p in workdir.iterdir():
            try:
                if p.is_file():
                    p.unlink()
            except Exception:
                pass
    except Exception:
        pass

def generate_config():
    config = {
        "log": {"access": "/dev/null", "error": "/dev/null", "loglevel": "none"},
        "inbounds": [
            {"port": ARGO_PORT, "protocol": "vless", "settings": {"clients": [{"id": UUID, "flow": "xtls-rprx-vision"}], "decryption": "none", "fallbacks": [{"dest": 3001}, {"path": "/vless-argo", "dest": 3002}, {"path": "/vmess-argo", "dest": 3003}, {"path": "/trojan-argo", "dest": 3004}]}, "streamSettings": {"network": "tcp"}},
            {"port": 3001, "listen": "127.0.0.1", "protocol": "vless", "settings": {"clients": [{"id": UUID}], "decryption": "none"}, "streamSettings": {"network": "tcp", "security": "none"}},
            {"port": 3002, "listen": "127.0.0.1", "protocol": "vless", "settings": {"clients": [{"id": UUID, "level": 0}], "decryption": "none"}, "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/vless-argo"}}, "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "metadataOnly": False}},
            {"port": 3003, "listen": "127.0.0.1", "protocol": "vmess", "settings": {"clients": [{"id": UUID, "alterId": 0}]}, "streamSettings": {"network": "ws", "wsSettings": {"path": "/vmess-argo"}}, "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "metadataOnly": False}},
            {"port": 3004, "listen": "127.0.0.1", "protocol": "trojan", "settings": {"clients": [{"password": UUID}]}, "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/trojan-argo"}}, "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "metadataOnly": False}}
        ],
        "dns": {"servers": ["https+local://8.8.8.8/dns-query"]},
        "outbounds": [{"protocol": "freedom", "tag": "direct"}, {"protocol": "blackhole", "tag": "block"}]
    }
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    print(f"wrote config.json -> {config_path}")

def download_file(dest_path, url, timeout=30):
    try:
        with requests.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            with open(dest_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        try:
            os.chmod(dest_path, 0o775)
        except Exception:
            pass
        print(f"Downloaded {os.path.basename(dest_path)} from {url}")
        return dest_path
    except Exception as e:
        print(f"Download failed for {url}: {e}")
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except Exception:
            pass
        return None

def get_files_for_architecture(is_arm):
    if is_arm:
        return [
            {"fileName": web_path, "fileUrl": "https://arm64.ssss.nyc.mn/web"},
            {"fileName": bot_path, "fileUrl": "https://arm64.ssss.nyc.mn/bot"}
        ]
    else:
        return [
            {"fileName": web_path, "fileUrl": "https://amd64.ssss.nyc.mn/web"},
            {"fileName": bot_path, "fileUrl": "https://amd64.ssss.nyc.mn/bot"}
        ]

def authorize_files(file_paths):
    for p in file_paths:
        try:
            if os.path.exists(p):
                os.chmod(p, 0o775)
                print(f"chmod 775 {p}")
        except Exception as e:
            print(f"chmod failed for {p}: {e}")

def run_xray_like():
    try:
        cmd = f'nohup "{web_path}" -c "{config_path}" >/dev/null 2>&1 &' if sys.platform != 'win32' else f'start /b "{web_path}" -c "{config_path}"'
        run_shell(cmd, background=True)
        print(f"{web_name} is running")
        time.sleep(1)
    except Exception as e:
        print(f"web running error: {e}")

def run_bot():
    if not os.path.exists(bot_path):
        print("bot binary not found, skip running bot")
        return

    args = None
    if ARGO_AUTH and ARGO_DOMAIN:
        if len(ARGO_AUTH) >= 120 and all(c.isalnum() or c in "=/" for c in ARGO_AUTH[:200]):
            args = f'tunnel --edge-ip-version auto --no-autoupdate --protocol http2 run --token {ARGO_AUTH}'
        elif 'TunnelSecret' in ARGO_AUTH:
            args = f'tunnel --edge-ip-version auto --config "{workdir}/tunnel.yml" run'
        else:
            args = f'tunnel --edge-ip-version auto --no-autoupdate --protocol http2 --logfile "{boot_log_path}" --loglevel info --url http://localhost:{ARGO_PORT}'
    else:
        args = f'tunnel --edge-ip-version auto --no-autoupdate --protocol http2 --logfile "{boot_log_path}" --loglevel info --url http://localhost:{ARGO_PORT}'

    cmd = f'nohup "{bot_path}" {args} >/dev/null 2>&1 &' if sys.platform != 'win32' else f'start /b "{bot_path}" {args}'
    try:
        run_shell(cmd, background=True)
        print(f"{bot_name} is running")
        time.sleep(2)
    except Exception as e:
        print(f"Error executing cloudflared bot: {e}")

def argo_type():
    if not (ARGO_AUTH and ARGO_DOMAIN):
        print("ARGO_DOMAIN or ARGO_AUTH variable is empty, use quick tunnels")
        return
    if 'TunnelSecret' in ARGO_AUTH:
        try:
            (workdir / 'tunnel.json').write_text(ARGO_AUTH, encoding='utf-8')
            try:
                auth_json = json.loads(ARGO_AUTH)
                tunnel_id = auth_json.get('tunnel', '')
            except Exception:
                parts = ARGO_AUTH.split('"')
                tunnel_id = parts[11] if len(parts) > 11 else ''
            tunnel_yaml = f"""
tunnel: {tunnel_id}
credentials-file: {workdir / 'tunnel.json'}
protocol: http2

ingress:
  - hostname: {ARGO_DOMAIN}
    service: http://localhost:{ARGO_PORT}
    originRequest:
      noTLSVerify: true
  - service: http_status:404
"""
            (workdir / 'tunnel.yml').write_text(tunnel_yaml, encoding='utf-8')
            print("wrote tunnel.yml")
        except Exception as e:
            print(f"argo_type error: {e}")
    else:
        print("ARGO_AUTH mismatch TunnelSecret,use token connect to tunnel")

def extract_domains_and_generate_links():
    argo_domain = None

    if ARGO_AUTH and ARGO_DOMAIN:
        argo_domain = ARGO_DOMAIN
        print("ARGO_DOMAIN:", argo_domain)
        return generate_links(argo_domain)

    if os.path.exists(boot_log_path):
        try:
            txt = open(boot_log_path, 'r', encoding='utf-8', errors='ignore').read()
            lines = txt.splitlines()
            domains = []
            for line in lines:
                if 'trycloudflare.com' in line:
                    import re
                    m = re.search(r'https?://([^/\s]+trycloudflare\.com)', line)
                    if m:
                        domains.append(m.group(1))
            if domains:
                argo_domain = domains[0]
                print("ArgoDomain:", argo_domain)
                return generate_links(argo_domain)
            else:
                print("ArgoDomain not found, re-running bot to obtain ArgoDomain")
                try:
                    os.remove(boot_log_path)
                except Exception:
                    pass
                try_kill_process_by_name(bot_name)
                time.sleep(3)
                run_bot()
                time.sleep(3)
                if os.path.exists(boot_log_path):
                    return extract_domains_and_generate_links()
                else:
                    print("boot.log still not produced, giving up for now")
        except Exception as e:
            print("Error reading boot.log:", e)
    else:
        print("boot.log not present yet; starting bot to create it")
        run_bot()
        time.sleep(3)
        if os.path.exists(boot_log_path):
            return extract_domains_and_generate_links()
    return None

_subscription_cache = {"subtxt": None}

def generate_links(argo_domain):
    ISP = ''
    try:
        r = requests.get('https://speed.cloudflare.com/meta', timeout=5)
        if r.ok:
            j = r.json()
            country = j.get('country', '')
            isp = j.get('isp', '')
            ISP = f"{isp}-{country}".replace(' ', '_') if isp or country else ''
    except Exception:
        ISP = ''
    node_name = f"{NAME}-{ISP}" if NAME else (ISP or 'node')

    VMESS = {
        "v": "2",
        "ps": node_name,
        "add": CFIP,
        "port": CFPORT,
        "id": UUID,
        "aid": "0",
        "scy": "none",
        "net": "ws",
        "type": "none",
        "host": argo_domain,
        "path": "/vmess-argo?ed=2560",
        "tls": "tls",
        "sni": argo_domain,
        "alpn": "",
        "fp": "firefox"
    }
    vmess_b64 = base64.b64encode(json.dumps(VMESS, separators=(',',':')).encode('utf-8')).decode('utf-8')

    subtxt = f"""
vless://{UUID}@{CFIP}:{CFPORT}?encryption=none&security=tls&sni={argo_domain}&fp=firefox&type=ws&host={argo_domain}&path=%2Fvless-argo%3Fed%3D2560#{node_name}

vmess://{vmess_b64}

trojan://{UUID}@{CFIP}:{CFPORT}?security=tls&sni={argo_domain}&fp=firefox&type=ws&host={argo_domain}&path=%2Ftrojan-argo%3Fed%3D2560#{node_name}
"""
    try:
        with open(sub_path, 'w', encoding='utf-8') as f:
            f.write(base64.b64encode(subtxt.encode('utf-8')).decode('utf-8'))
        print(f"saved {sub_path}")
        _subscription_cache['subtxt'] = subtxt
        upload_nodes_or_subscriptions()
    except Exception as e:
        print(f"generate_links write error: {e}")
    return subtxt

def upload_nodes_or_subscriptions():
    if UPLOAD_URL and PROJECT_URL:
        subscription_url = f"{PROJECT_URL.rstrip('/')}/{SUB_PATH}"
        json_payload = {"subscription": [subscription_url]}
        try:
            r = requests.post(f"{UPLOAD_URL.rstrip('/')}/api/add-subscriptions", json=json_payload, timeout=8)
            if r.ok:
                print("Subscription uploaded successfully")
                return r
            else:
                print("Upload subscription status:", r.status_code)
                return None
        except Exception as e:
            print("upload subscription error:", e)
            return None
    elif UPLOAD_URL:
        if not os.path.exists(list_path):
            return
        try:
            content = open(list_path, 'r', encoding='utf-8').read()
            nodes = [line for line in content.splitlines() if any(proto in line for proto in ('vless://','vmess://','trojan://','hysteria2://','tuic://'))]
            if not nodes:
                return
            payload = {"nodes": nodes}
            try:
                r = requests.post(f"{UPLOAD_URL.rstrip('/')}/api/add-nodes", json=payload, timeout=8)
                if r.ok:
                    print("Nodes uploaded successfully")
                    return r
                else:
                    print("Upload nodes status:", r.status_code)
                    return None
            except Exception:
                return None
        except Exception:
            return None
    else:
        return None

def clean_files_after_delay():
    def job():
        time.sleep(90)
        files_to_delete = [boot_log_path, config_path, web_path, bot_path]
        for p in files_to_delete:
            try:
                if os.path.exists(p):
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        os.remove(p)
            except Exception:
                pass
        print("App is running")
        print("Thank you for using this script, enjoy!")
    t = threading.Thread(target=job, daemon=True)
    t.start()

def add_visit_task():
    if not AUTO_ACCESS or not PROJECT_URL:
        print("Skipping adding automatic access task")
        return None
    try:
        r = requests.post('https://oooo.serv00.net/add-url', json={'url': PROJECT_URL}, timeout=8)
        if r.ok:
            print("automatic access task added successfully")
            return r
        else:
            print("AddVisitTask status:", r.status_code)
            return None
    except Exception as e:
        print("Add automatic access task failed:", e)
        return None

def download_files_and_run():
    is_arm = is_arm_arch()
    files = get_files_for_architecture(is_arm)
    if not files:
        print("Can't find a file for the current architecture")
        return

    downloaded = []
    for fi in files:
        dest = fi['fileName']
        url = fi['fileUrl']
        result = download_file(dest, url)
        if result:
            downloaded.append(result)
    authorize_files([p for p in (web_path, bot_path) if os.path.exists(p)])
    run_xray_like()
    run_bot()
    time.sleep(5)

def start_server_background():
    try:
        delete_nodes()
        cleanup_old_files()
        generate_config()
        download_files_and_run()
        extract_domains_and_generate_links()
        add_visit_task()
    except Exception as e:
        print("Error in start_server:", e)

threading.Thread(target=start_server_background, daemon=True).start()
clean_files_after_delay()

# --- Simple threaded HTTP server (no Flask) ---
class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True

class SimpleHandler(BaseHTTPRequestHandler):
    def _send_text(self, txt, code=200):
        b = txt.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split('?')[0].rstrip('/')
        if path == '' or path == '/':
            self._send_text("Hello world!")
            return
        # match /SUB_PATH exactly (with or without leading slash)
        expected = f"/{SUB_PATH}".rstrip('/')
        if self.path.startswith(f"/{SUB_PATH}") or self.path.rstrip('/') == expected:
            try:
                if os.path.exists(sub_path):
                    encoded = open(sub_path, 'r', encoding='utf-8').read().strip()
                    self._send_text(encoded)
                    return
                if _subscription_cache.get('subtxt'):
                    encoded = base64.b64encode(_subscription_cache['subtxt'].encode('utf-8')).decode('utf-8')
                    self._send_text(encoded)
                    return
                self._send_text('', 200)
                return
            except Exception:
                self._send_text('', 200)
                return
        # fallback 404
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        # suppress default logging or change as needed
        sys.stdout.write("%s - - [%s] %s\n" %
                         (self.client_address[0],
                          self.log_date_time_string(),
                          format%args))

if __name__ == '__main__':
    print("ENV summary:")
    print(f"UPLOAD_URL={UPLOAD_URL}, PROJECT_URL={PROJECT_URL}, AUTO_ACCESS={AUTO_ACCESS}, FILE_PATH={FILE_PATH}, SUB_PATH={SUB_PATH}, PORT={PORT}")
    server = ThreadingHTTPServer(('0.0.0.0', PORT), SimpleHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        print("Server stopped")
