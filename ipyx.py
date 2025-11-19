#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server_no_deps.py
Zero-dependency version (only Python standard library).
Saves subscription to FILE_PATH/sub.txt (base64) and serves it at /<SUB_PATH>.
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
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver
import urllib.request
import urllib.parse
import ssl
import errno
import io
import traceback

# --------------------------
# Environment variables
# --------------------------
UPLOAD_URL = os.environ.get('UPLOAD_URL', '').strip()
PROJECT_URL = os.environ.get('PROJECT_URL', '').strip()
AUTO_ACCESS = os.environ.get('AUTO_ACCESS', 'false').lower() in ('1','true','yes')
FILE_PATH = os.environ.get('FILE_PATH', './tmp')
SUB_PATH = os.environ.get('SUB_PATH', 'ppwq')
PORT = int(os.environ.get('SERVER_PORT') or os.environ.get('PORT') or 3000)
UUID = os.environ.get('UUID', '9afd1229-b893-40c1-84dd-51e7ce204913')
ARGO_DOMAIN = os.environ.get('ARGO_DOMAIN', '').strip()
ARGO_AUTH = os.environ.get('ARGO_AUTH', '').strip()
ARGO_PORT = int(os.environ.get('ARGO_PORT', 8001))
CFIP = os.environ.get('CFIP', 'cdns.doon.eu.org').strip()
CFPORT = os.environ.get('CFPORT', '443').strip()
NAME = os.environ.get('NAME', 'ppwq').strip()

# --------------------------
# Setup working dir & names
# --------------------------
workdir = Path(FILE_PATH)
workdir.mkdir(parents=True, exist_ok=True)

def rnd(n=6):
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(n))

web_name = rnd()
bot_name = rnd()

web_path = str(workdir / web_name)
bot_path = str(workdir / bot_name)
sub_path = str(workdir / 'sub.txt')
list_path = str(workdir / 'list.txt')
boot_log_path = str(workdir / 'boot.log')
config_path = str(workdir / 'config.json')

_subscription_cache = {"subtxt": None}

print("Working dir:", workdir.resolve())
print("ENV summary:", {"UPLOAD_URL": bool(UPLOAD_URL), "PROJECT_URL": bool(PROJECT_URL),
                      "AUTO_ACCESS": AUTO_ACCESS, "FILE_PATH": FILE_PATH, "SUB_PATH": SUB_PATH, "PORT": PORT})

# --------------------------
# Utilities (urllib wrappers)
# --------------------------
DEFAULT_TIMEOUT = 15

def url_get(url, timeout=DEFAULT_TIMEOUT):
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, method='GET', headers={'User-Agent': 'python-urllib/3'})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read()
    except Exception as e:
        # print minimal error
        #print("url_get error:", e)
        return None

def url_get_stream(url, dest_path, timeout=DEFAULT_TIMEOUT):
    """Stream-download URL -> dest_path (binary). Returns True on success."""
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, method='GET', headers={'User-Agent': 'python-urllib/3'})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            with open(dest_path, 'wb') as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
        try:
            os.chmod(dest_path, 0o775)
        except Exception:
            pass
        return True
    except Exception as e:
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except Exception:
            pass
        return False

def url_post_json(url, data, timeout=DEFAULT_TIMEOUT):
    """POST JSON and return (status, body_bytes) or (None,None) on failure."""
    try:
        ctx = ssl.create_default_context()
        body = json.dumps(data).encode('utf-8')
        headers = {'Content-Type': 'application/json', 'User-Agent': 'python-urllib/3'}
        req = urllib.request.Request(url, data=body, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return (resp.getcode(), resp.read())
    except Exception as e:
        return (None, None)

# --------------------------
# File / process helpers
# --------------------------
def is_arm_arch():
    try:
        arch = os.uname().machine.lower()
        return ('arm' in arch) or ('aarch64' in arch)
    except Exception:
        # fallback to env
        return 'arm' in os.environ.get('PROCESSOR_ARCHITECTURE','').lower()

def run_bg(cmd_line):
    """Start a detached background process similar to nohup style."""
    try:
        if sys.platform == 'win32':
            # On Windows, use creationflags
            return subprocess.Popen(cmd_line, shell=True,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            # POSIX: use setsid to detach
            return subprocess.Popen(cmd_line, shell=True,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    preexec_fn=os.setsid)
    except Exception as e:
        return None

def try_kill_by_name(name):
    # best-effort: pkill on POSIX, taskkill on Windows
    try:
        if sys.platform == 'win32':
            subprocess.run(f'taskkill /f /im {name} > nul 2>&1', shell=True)
        else:
            subprocess.run(f'pkill -f "{name}" > /dev/null 2>&1', shell=True)
    except Exception:
        pass

# --------------------------
# Core logic (no Nezha)
# --------------------------
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
        try:
            decoded = base64.b64decode(encoded).decode('utf-8', errors='ignore')
        except Exception:
            return
        nodes = [line for line in decoded.splitlines() if any(proto in line for proto in ('vless://','vmess://','trojan://','hysteria2://','tuic://'))]
        if not nodes:
            return
        _ = url_post_json(UPLOAD_URL.rstrip('/') + '/api/delete-nodes', {"nodes": nodes})
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
    cfg = {
        "log": {"access": "/dev/null", "error": "/dev/null", "loglevel": "none"},
        "inbounds": [
            {"port": ARGO_PORT, "protocol": "vless", "settings": {"clients": [{"id": UUID, "flow": "xtls-rprx-vision"}], "decryption": "none",
             "fallbacks": [{"dest": 3001}, {"path": "/vless-argo", "dest": 3002}, {"path": "/vmess-argo", "dest": 3003}, {"path": "/trojan-argo", "dest": 3004}]},
             "streamSettings": {"network": "tcp"}},
            {"port": 3001, "listen": "127.0.0.1", "protocol": "vless", "settings": {"clients": [{"id": UUID}], "decryption": "none"},
             "streamSettings": {"network": "tcp", "security": "none"}},
            {"port": 3002, "listen": "127.0.0.1", "protocol": "vless", "settings": {"clients": [{"id": UUID, "level": 0}], "decryption": "none"},
             "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/vless-argo"}}, "sniffing": {"enabled": True, "destOverride": ["http","tls","quic"], "metadataOnly": False}},
            {"port": 3003, "listen": "127.0.0.1", "protocol": "vmess", "settings": {"clients": [{"id": UUID, "alterId": 0}]},
             "streamSettings": {"network": "ws", "wsSettings": {"path": "/vmess-argo"}}, "sniffing": {"enabled": True, "destOverride": ["http","tls","quic"], "metadataOnly": False}},
            {"port": 3004, "listen": "127.0.0.1", "protocol": "trojan", "settings": {"clients": [{"password": UUID}]},
             "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/trojan-argo"}}, "sniffing": {"enabled": True, "destOverride": ["http","tls","quic"], "metadataOnly": False}}
        ],
        "dns": {"servers": ["https+local://8.8.8.8/dns-query"]},
        "outbounds": [{"protocol": "freedom", "tag": "direct"}, {"protocol": "blackhole", "tag": "block"}]
    }
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        pass

def get_files_for_arch(is_arm):
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

def download_files_and_run():
    is_arm = is_arm_arch()
    files = get_files_for_arch(is_arm)
    if not files:
        print("No files to download for arch")
        return
    for fi in files:
        dest = fi['fileName']
        url = fi['fileUrl']
        ok = url_get_stream(url, dest, timeout=20)
        if ok:
            print("Downloaded:", dest)
    # chmod web & bot
    for p in (web_path, bot_path):
        try:
            if os.path.exists(p):
                os.chmod(p, 0o775)
        except Exception:
            pass
    # run web
    run_xray_like()
    # run bot
    run_bot()
    time.sleep(5)

def run_xray_like():
    if not os.path.exists(web_path):
        print("web binary missing, skip")
        return
    if sys.platform == 'win32':
        cmd = f'start /b "{web_path}" -c "{config_path}"'
    else:
        cmd = f'nohup "{web_path}" -c "{config_path}" >/dev/null 2>&1 &'
    run_bg(cmd)
    print("started web:", web_path)

def run_bot():
    if not os.path.exists(bot_path):
        print("bot binary missing, skip")
        return
    if ARGO_AUTH and ARGO_DOMAIN:
        if len(ARGO_AUTH) >= 120 and all(c.isalnum() or c in "=/+" for c in ARGO_AUTH[:200]):
            args = f'tunnel --edge-ip-version auto --no-autoupdate --protocol http2 run --token {ARGO_AUTH}'
        elif 'TunnelSecret' in ARGO_AUTH:
            args = f'tunnel --edge-ip-version auto --config "{workdir}/tunnel.yml" run'
        else:
            args = f'tunnel --edge-ip-version auto --no-autoupdate --protocol http2 --logfile "{boot_log_path}" --loglevel info --url http://localhost:{ARGO_PORT}'
    else:
        args = f'tunnel --edge-ip-version auto --no-autoupdate --protocol http2 --logfile "{boot_log_path}" --loglevel info --url http://localhost:{ARGO_PORT}'
    if sys.platform == 'win32':
        cmd = f'start /b "{bot_path}" {args}'
    else:
        cmd = f'nohup "{bot_path}" {args} >/dev/null 2>&1 &'
    run_bg(cmd)
    print("started bot:", bot_path)

def argo_type():
    if not (ARGO_AUTH and ARGO_DOMAIN):
        return
    if 'TunnelSecret' in ARGO_AUTH:
        try:
            (workdir / 'tunnel.json').write_text(ARGO_AUTH, encoding='utf-8')
            try:
                auth_json = json.loads(ARGO_AUTH)
                tunnel_id = auth_json.get('tunnel','')
            except Exception:
                parts = ARGO_AUTH.split('"')
                tunnel_id = parts[11] if len(parts) > 11 else ''
            y = f"""
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
            (workdir / 'tunnel.yml').write_text(y, encoding='utf-8')
        except Exception:
            pass

def generate_links(argo_domain):
    # try cloudflare meta
    ISP = ''
    try:
        meta = url_get('https://speed.cloudflare.com/meta', timeout=5)
        if meta:
            try:
                jm = json.loads(meta.decode('utf-8', errors='ignore'))
                isp = jm.get('isp','')
                country = jm.get('country','')
                ISP = f"{isp}-{country}".replace(' ', '_') if (isp or country) else ''
            except Exception:
                ISP = ''
    except Exception:
        ISP = ''
    node_name = f"{NAME}-{ISP}" if NAME else (ISP or 'node')

    VMESS = {
        "v": "2","ps": node_name,"add": CFIP,"port": CFPORT,"id": UUID,"aid": "0","scy": "none",
        "net": "ws","type": "none","host": argo_domain,"path": "/vmess-argo?ed=2560","tls": "tls","sni": argo_domain,"alpn": "","fp": "firefox"
    }
    vmess_b64 = base64.b64encode(json.dumps(VMESS, separators=(',',':')).encode('utf-8')).decode('utf-8')

    subtxt = (
f"vless://{UUID}@{CFIP}:{CFPORT}?encryption=none&security=tls&sni={argo_domain}&fp=firefox&type=ws&host={argo_domain}&path=%2Fvless-argo%3Fed%3D2560#{node_name}\n\n"
f"vmess://{vmess_b64}\n\n"
f"trojan://{UUID}@{CFIP}:{CFPORT}?security=tls&sni={argo_domain}&fp=firefox&type=ws&host={argo_domain}&path=%2Ftrojan-argo%3Fed%3D2560#{node_name}\n"
    )

    try:
        encoded = base64.b64encode(subtxt.encode('utf-8')).decode('utf-8')
        with open(sub_path, 'w', encoding='utf-8') as f:
            f.write(encoded)
        _subscription_cache['subtxt'] = subtxt
        print("saved sub.txt")
        upload_nodes_or_subscriptions()
    except Exception:
        pass
    return subtxt

def extract_domains_and_generate_links():
    argo_domain = None
    if ARGO_AUTH and ARGO_DOMAIN:
        return generate_links(ARGO_DOMAIN)
    # try parse boot_log
    if os.path.exists(boot_log_path):
        try:
            txt = open(boot_log_path, 'r', encoding='utf-8', errors='ignore').read()
            import re
            m = re.search(r'https?://([^/\s]*trycloudflare\.com)', txt)
            if m:
                argo_domain = m.group(1)
                return generate_links(argo_domain)
            else:
                # remove boot_log and restart bot to create new one
                try:
                    os.remove(boot_log_path)
                except Exception:
                    pass
                try_kill_by_name(bot_path)
                time.sleep(2)
                run_bot()
                time.sleep(3)
                if os.path.exists(boot_log_path):
                    return extract_domains_and_generate_links()
        except Exception:
            pass
    else:
        run_bot()
        time.sleep(3)
        if os.path.exists(boot_log_path):
            return extract_domains_and_generate_links()
    return None

def upload_nodes_or_subscriptions():
    if UPLOAD_URL and PROJECT_URL:
        subscription_url = f"{PROJECT_URL.rstrip('/')}/{SUB_PATH}"
        status, body = url_post_json(UPLOAD_URL.rstrip('/') + '/api/add-subscriptions', {"subscription": [subscription_url]}, timeout=8)
        if status == 200:
            print("Subscription uploaded")
        return
    if UPLOAD_URL:
        if not os.path.exists(list_path):
            return
        try:
            content = open(list_path, 'r', encoding='utf-8').read()
            nodes = [line for line in content.splitlines() if any(proto in line for proto in ('vless://','vmess://','trojan://','hysteria2://','tuic://'))]
            if not nodes:
                return
            status, _ = url_post_json(UPLOAD_URL.rstrip('/') + '/api/add-nodes', {"nodes": nodes}, timeout=8)
            if status == 200:
                print("Nodes uploaded")
        except Exception:
            pass

def add_visit_task():
    if not AUTO_ACCESS or not PROJECT_URL:
        print("Skipping automatic access task")
        return
    try:
        status, _ = url_post_json('https://oooo.serv00.net/add-url', {"url": PROJECT_URL}, timeout=8)
        if status == 200:
            print("automatic access task added")
    except Exception:
        pass

def clean_files_after_delay():
    def job():
        time.sleep(90)
        files = [boot_log_path, config_path, web_path, bot_path]
        for f in files:
            try:
                if os.path.exists(f):
                    if os.path.isdir(f):
                        shutil.rmtree(f, ignore_errors=True)
                    else:
                        os.remove(f)
            except Exception:
                pass
        print("App is running\nThank you for using this script, enjoy!")
    t = threading.Thread(target=job, daemon=True)
    t.start()

def start_server_background():
    try:
        delete_nodes()
        cleanup_old_files()
        generate_config()
        download_files_and_run()
        extract_domains_and_generate_links()
        add_visit_task()
    except Exception:
        traceback.print_exc()

# --------------------------
# HTTP server (no Flask)
# --------------------------
class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True

class Handler(BaseHTTPRequestHandler):
    def _text(self, s, status=200):
        b = s.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/' or path == '':
            self._text("Hello world!")
            return
        if path.rstrip('/') == '/' + SUB_PATH:
            try:
                if os.path.exists(sub_path):
                    data = open(sub_path, 'r', encoding='utf-8').read().strip()
                    self._text(data)
                    return
                if _subscription_cache.get('subtxt'):
                    en = base64.b64encode(_subscription_cache['subtxt'].encode('utf-8')).decode('utf-8')
                    self._text(en)
                    return
                self._text('', 200)
                return
            except Exception:
                self._text('', 200)
                return
        # 404
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        sys.stdout.write("%s - - [%s] %s\n" %
                         (self.client_address[0],
                          self.log_date_time_string(),
                          format%args))

# --------------------------
# Start background tasks & HTTP server
# --------------------------
if __name__ == '__main__':
    threading.Thread(target=start_server_background, daemon=True).start()
    clean_files_after_delay()
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    try:
        print(f"Listening on 0.0.0.0:{PORT} (no deps)")
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down")
        server.shutdown()
