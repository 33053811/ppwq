#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ArgoSB Python3 — Cloudflare IP 并发优选 + 内置订阅 HTTP 服务
功能：
- 从 https://www.cloudflare.com/ips-v4 拉取网段候选
- 并发探测候选 IP（TCP / TLS+HTTP），优选写回 config.json
- 基于优选结果生成 vmess 链接、轮询订阅和 Base64 订阅
- 在安装时生成并后台启动一个 tiny HTTP server（nohup），对外提供 subscription_base64.txt
- 支持 install/status/update/del/cat 等命令
"""

import os
import sys
import json
import random
import time
import shutil
import re
import base64
import socket
import subprocess
import platform
from datetime import datetime
import uuid
from pathlib import Path
import urllib.request
import ssl
import tempfile
import argparse
import concurrent.futures

# ------------------ 全局配置 ------------------
INSTALL_DIR = Path.home() / ".agsb"
CONFIG_FILE = INSTALL_DIR / "config.json"
SB_PID_FILE = INSTALL_DIR / "sbpid.log"
ARGO_PID_FILE = INSTALL_DIR / "sbargopid.log"
LIST_FILE = INSTALL_DIR / "list.txt"
LOG_FILE = INSTALL_DIR / "argo.log"
DEBUG_LOG = INSTALL_DIR / "python_debug.log"
CUSTOM_DOMAIN_FILE = INSTALL_DIR / "custom_domain.txt"
SUBS_PID_FILE = INSTALL_DIR / "subscription_server.pid"

CF_IPV4_URL = "https://www.cloudflare.com/ips-v4"

# 可调整参数
MAX_CANDIDATES_SAMPLE = 80   # 从 Cloudflare 网段抽样多少个候选 IP
PREFERRED_TLS_TOPN = 6
PREFERRED_HTTP_TOPN = 4
DEFAULT_SUBS_PORT = 8000     # 内置订阅服务器端口
MAX_WORKERS = 32             # 最大并发线程数（探测并发）
TCP_TIMEOUT = 2.0
TLS_TIMEOUT = 4.0

# ------------------ 帮助/参数 ------------------
def parse_args():
    parser = argparse.ArgumentParser(description="ArgoSB: Cloudflare IP 并发优选 + 内置订阅服务")
    parser.add_argument("action", nargs="?", default="install",
                        choices=["install", "status", "update", "del", "uninstall", "cat"],
                        help="操作类型")
    parser.add_argument("--domain", "-d", dest="agn", help="自定义域名")
    parser.add_argument("--uuid", "-u", help="自定义 UUID")
    parser.add_argument("--port", "-p", dest="vmpt", type=int, help="自定义本地 Vmess 端口")
    parser.add_argument("--agk", "--token", dest="agk", help="Argo Tunnel Token")
    parser.add_argument("--fast", action="store_true", help="快速模式，仅做 TCP 探测（更快）")
    parser.add_argument("--subs-port", type=int, dest="subs_port", help="订阅服务器端口（默认 8000）")
    return parser.parse_args()

def print_info():
    print("\033[36m╭───────────────────────────────────────────────────────────────╮\033[0m")
    print("\033[36m│             \033[33m✨ ArgoSB 并发优选 + 订阅服务 ✨             \033[36m│\033[0m")
    print("\033[36m│ \033[32m功能: 并发探测 Cloudflare IP，生成 vmess 订阅并提供 HTTP 订阅服务\033[36m│\033[0m")
    print("\033[36m╰───────────────────────────────────────────────────────────────╯\033[0m")

def write_debug_log(message):
    try:
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass

# ------------------ 网络工具 ------------------
def http_get(url, timeout=10):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={'User-Agent': 'ArgoSB/1.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.read().decode('utf-8')
    except Exception as e:
        write_debug_log(f"http_get error: {e} url: {url}")
        return None

def download_file(url, target_path, mode='wb'):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={'User-Agent': 'ArgoSB/1.0'})
        with urllib.request.urlopen(req, context=ctx) as response, open(target_path, mode) as out_file:
            shutil.copyfileobj(response, out_file)
        return True
    except Exception as e:
        write_debug_log(f"download_file error: {e} url: {url}")
        return False

# ------------------ VMess 生成 ------------------
def generate_vmess_link(config):
    vmess_obj = {
        "v": "2",
        "ps": config.get("ps", "ArgoSB"),
        "add": config.get("add", ""),
        "port": str(config.get("port", "443")),
        "id": config.get("id", ""),
        "aid": str(config.get("aid", "0")),
        "net": config.get("net", "ws"),
        "type": config.get("type", "none"),
        "host": config.get("host", ""),
        "path": config.get("path", ""),
        "tls": config.get("tls", "tls"),
        "sni": config.get("sni", "")
    }
    s = json.dumps(vmess_obj, sort_keys=True, separators=(',', ':'))
    b = base64.b64encode(s.encode('utf-8')).decode('utf-8').rstrip('=')
    return f"vmess://{b}"

# ------------------ 探测函数 ------------------
def _normalize_candidate(ip_base):
    try:
        parts = ip_base.strip().split('.')
        if len(parts) == 4:
            if parts[3] == '0':
                parts[3] = '1'
            else:
                parts[3] = '1'
            return ".".join(parts)
    except Exception:
        pass
    return ip_base

def probe_tcp_latency_once(ip, port, timeout=TCP_TIMEOUT):
    start = time.time()
    try:
        with socket.create_connection((ip, int(port)), timeout=timeout):
            return time.time() - start
    except Exception:
        return None

def probe_tls_http_once(ip, port, host, path='/', timeout=TLS_TIMEOUT):
    try:
        start = time.time()
        sock = socket.create_connection((ip, int(port)), timeout=timeout)
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        ss = context.wrap_socket(sock, server_hostname=host)
        req = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: ArgoSBProbe/1.0\r\nConnection: close\r\n\r\n"
        ss.sendall(req.encode('utf-8'))
        chunk = ss.recv(1024)
        ss.close()
        rtt = time.time() - start
        ok = False
        if chunk:
            s = chunk.decode('latin1', errors='ignore').lower()
            if 'http/1.' in s or 'http/2' in s or 'cloudflare' in s or '<html' in s or '200 ok' in s:
                ok = True
        return (rtt, ok, chunk.decode('latin1', errors='ignore'))
    except Exception:
        return (None, False, "")

# 并发优选函数：使用 ThreadPoolExecutor 并发探测每个候选 IP
def prefer_ips_concurrent(candidate_ips, port=443, host=None, path='/', top_n=3, mode='tcp', max_workers=MAX_WORKERS):
    write_debug_log(f"prefer_ips_concurrent start: {len(candidate_ips)} candidates, port={port}, mode={mode}")
    results = []

    def task_tcp(ip):
        ipn = _normalize_candidate(ip)
        rtt = probe_tcp_latency_once(ipn, port, timeout=TCP_TIMEOUT)
        return (ipn, rtt if rtt is not None else 9999, rtt is not None, 'tcp')

    def task_tls(ip):
        ipn = _normalize_candidate(ip)
        rtt, ok, chunk = probe_tls_http_once(ipn, port, host or ipn, path=path, timeout=TLS_TIMEOUT)
        if rtt is None:
            return (ipn, 9999, False, 'tlshttp')
        score = rtt if ok else rtt + 5.0
        return (ipn, score, ok, 'tlshttp')

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, max(4, len(candidate_ips)))) as executor:
        futures = []
        for ip in candidate_ips:
            if mode == 'tcp':
                futures.append(executor.submit(task_tcp, ip))
            else:
                futures.append(executor.submit(task_tls, ip))
        for fut in concurrent.futures.as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:
                write_debug_log(f"probe task exception: {e}")

    # 排序并返回 top_n ip list
    results_sorted = sorted(results, key=lambda x: (not x[2], x[1]))
    write_debug_log(f"prefer_ips_concurrent sample results: {results_sorted[:min(len(results_sorted),20)]}")
    return [r[0] for r in results_sorted[:top_n]]

# ------------------ Cloudflare 网段获取 ------------------
def fetch_cloudflare_ipv4_prefixes():
    content = http_get(CF_IPV4_URL, timeout=8)
    if not content:
        write_debug_log("fetch_cloudflare_ipv4_prefixes failed")
        return None
    lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith('#')]
    return lines

def prefix_to_probe_ip(prefix):
    try:
        net = prefix.split('/')[0].strip()
        parts = net.split('.')
        if len(parts) == 4:
            parts[3] = '1'
            return ".".join(parts)
    except Exception:
        pass
    return prefix

def build_cf_candidate_list(max_samples=MAX_CANDIDATES_SAMPLE):
    prefixes = fetch_cloudflare_ipv4_prefixes()
    if not prefixes:
        fallback = ["104.16.0.1","104.17.0.1","104.18.0.1","104.19.0.1","104.20.0.1",
                    "104.21.0.1","104.22.0.1","104.24.0.1"]
        return fallback[:max_samples]
    candidate_ips = [prefix_to_probe_ip(p) for p in prefixes]
    candidate_ips = list(dict.fromkeys(candidate_ips))
    random.shuffle(candidate_ips)
    return candidate_ips[:max_samples]

# ------------------ 生成链接与订阅 ------------------
def generate_links(domain, port_vm_ws, uuid_str, fast_mode=False, subs_port=DEFAULT_SUBS_PORT):
    write_debug_log(f"generate_links start domain={domain} fast_mode={fast_mode}")
    ws_path = f"/{uuid_str[:8]}-vm"
    ws_path_full = f"{ws_path}?ed=2048"
    hostname = socket.gethostname()[:10]

    # 获取候选并发优选
    candidates = build_cf_candidate_list()
    mode = 'tcp' if fast_mode or not domain else 'tlshttp'
    preferred_tls = prefer_ips_concurrent(candidates, port=443, host=domain, path=ws_path, top_n=PREFERRED_TLS_TOPN, mode=mode)
    preferred_http = prefer_ips_concurrent(candidates, port=80, host=domain, path=ws_path, top_n=PREFERRED_HTTP_TOPN, mode='tcp')

    # 写回 config.json
    try:
        cfg = json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
        cfg["preferred_ips_tls"] = preferred_tls
        cfg["preferred_ips_http"] = preferred_http
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        write_debug_log(f"write preferred ips failed: {e}")

    all_links = []
    link_names = []

    # TLS
    for ip in preferred_tls:
        cfg = {
            "ps": f"VMWS-TLS-{hostname}-{ip.replace('.', '-')}-443",
            "add": ip,
            "port": "443",
            "id": uuid_str,
            "aid": "0",
            "net": "ws",
            "type": "none",
            "host": domain if domain else ip,
            "path": ws_path_full,
            "tls": "tls",
            "sni": domain if domain else ""
        }
        all_links.append(generate_vmess_link(cfg))
        link_names.append(f"TLS-{ip}")

    # HTTP
    for ip in preferred_http:
        cfg = {
            "ps": f"VMWS-HTTP-{hostname}-{ip.replace('.', '-')}-80",
            "add": ip,
            "port": "80",
            "id": uuid_str,
            "aid": "0",
            "net": "ws",
            "type": "none",
            "host": domain if domain else ip,
            "path": ws_path_full,
            "tls": ""
        }
        all_links.append(generate_vmess_link(cfg))
        link_names.append(f"HTTP-{ip}")

    # Direct domain
    if domain:
        direct_tls = {
            "ps": f"VMWS-TLS-{hostname}-Direct-{domain[:15]}-443",
            "add": domain,
            "port": "443",
            "id": uuid_str,
            "aid": "0",
            "net": "ws",
            "type": "none",
            "host": domain,
            "path": ws_path_full,
            "tls": "tls",
            "sni": domain
        }
        all_links.append(generate_vmess_link(direct_tls))
        link_names.append("Direct-TLS")
        direct_http = {
            "ps": f"VMWS-HTTP-{hostname}-Direct-{domain[:15]}-80",
            "add": domain,
            "port": "80",
            "id": uuid_str,
            "aid": "0",
            "net": "ws",
            "type": "none",
            "host": domain,
            "path": ws_path_full,
            "tls": ""
        }
        all_links.append(generate_vmess_link(direct_http))
        link_names.append("Direct-HTTP")

    # 保存 files
    try:
        (INSTALL_DIR / "allnodes.txt").write_text("\n".join(all_links) + "\n")
        (INSTALL_DIR / "jh.txt").write_text("\n".join(all_links) + "\n")
    except Exception as e:
        write_debug_log(f"save allnodes failed: {e}")

    # vmess_round_robin
    try:
        (INSTALL_DIR / "vmess_round_robin.txt").write_text("\n".join(all_links) + "\n")
    except Exception as e:
        write_debug_log(f"write vmess_round_robin failed: {e}")

    # subscription base64
    try:
        data = "\n".join(all_links) + "\n"
        b64 = base64.b64encode(data.encode('utf-8')).decode('utf-8')
        (INSTALL_DIR / "subscription_base64.txt").write_text(b64)
    except Exception as e:
        write_debug_log(f"write subscription_base64 failed: {e}")

    # 保存 domain 文件
    if domain:
        try:
            CUSTOM_DOMAIN_FILE.write_text(domain)
        except Exception:
            pass

    # 更新 LIST_FILE（简要）
    try:
        lines = []
        lines.append("\033[36m╭───────────────────────────────────────────────────────────────╮\033[0m")
        lines.append("\033[36m│                \033[33m✨ ArgoSB 节点信息 ✨                   \033[36m│\033[0m")
        lines.append("\033[36m├───────────────────────────────────────────────────────────────┤\033[0m")
        lines.append(f"\033[36m│ \033[32m域名: \033[0m{domain}")
        lines.append(f"\033[36m│ \033[32mUUID: \033[0m{uuid_str}")
        lines.append(f"\033[36m│ \033[36m订阅 (Base64) 文件: \033[0m{INSTALL_DIR / 'subscription_base64.txt'}")
        lines.append("\033[36m╰───────────────────────────────────────────────────────────────╯\033[0m")
        LIST_FILE.write_text("\n".join(lines) + "\n")
    except Exception:
        pass

    print("\033[32m节点与订阅生成完成：\033[0m")
    print(f" - allnodes: {INSTALL_DIR / 'allnodes.txt'}")
    print(f" - round-robin: {INSTALL_DIR / 'vmess_round_robin.txt'}")
    print(f" - base64订阅: {INSTALL_DIR / 'subscription_base64.txt'}")
    print(f" - 订阅 URL: http://<your-server-ip>:{subs_port}/subscription_base64.txt")
    write_debug_log("generate_links finished")
    return True

# ------------------ 内置订阅服务（生成 serve_sub.py 并启动） ------------------
def create_subscription_server_script(port=DEFAULT_SUBS_PORT):
    """
    生成 serve_sub.py（简单的 http.server）和 start_sub.sh 脚本，
    并返回路径与启动脚本路径
    """
    serve_py = INSTALL_DIR / "serve_sub.py"
    start_sh = INSTALL_DIR / "start_sub.sh"

    serve_content = f"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import http.server, socketserver, os
PORT = {port}
os.chdir(r\"{INSTALL_DIR}\")
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin','*')
        http.server.SimpleHTTPRequestHandler.end_headers(self)
handler = QuietHandler
with socketserver.TCPServer(('', PORT), handler) as httpd:
    print('Serving subscription files on port', PORT)
    httpd.serve_forever()
"""
    serve_py.write_text(serve_content)
    os.chmod(serve_py, 0o755)

    start_content = f"""#!/bin/bash
cd {INSTALL_DIR}
nohup python3 {serve_py.name} > subscription_server.log 2>&1 &
echo $! > {SUBS_PID_FILE.name}
"""
    (start_sh).write_text(start_content)
    os.chmod(start_sh, 0o755)
    write_debug_log("create_subscription_server_script created")
    return serve_py, start_sh

def start_subscription_server(port=DEFAULT_SUBS_PORT):
    serve_py, start_sh = create_subscription_server_script(port=port)
    # 启动
    try:
        subprocess.run(str(start_sh), shell=True)
        time.sleep(0.5)
        if SUBS_PID_FILE.exists():
            pid = SUBS_PID_FILE.read_text().strip()
            write_debug_log(f"subscription server started pid={pid} port={port}")
            return True
    except Exception as e:
        write_debug_log(f"start_subscription_server failed: {e}")
    return False

# ------------------ create_startup_script（包含订阅服务） ------------------
def create_startup_script():
    if not CONFIG_FILE.exists():
        write_debug_log("config.json not found when creating startup script")
        return

    try:
        config = json.loads(CONFIG_FILE.read_text())
    except Exception as e:
        write_debug_log(f"read config failed: {e}")
        return

    port_vm_ws = config.get("port_vm_ws")
    uuid_str = config.get("uuid_str")
    argo_token = config.get("argo_token")
    domain = config.get("custom_domain_agn") or None
    subs_port = config.get("subscription_port", DEFAULT_SUBS_PORT)

    sb_start = INSTALL_DIR / "start_sb.sh"
    sb_start.write_text(f"""#!/bin/bash
cd {INSTALL_DIR}
./sing-box run -c sb.json > sb.log 2>&1 &
echo $! > {SB_PID_FILE.name}
""")
    os.chmod(sb_start, 0o755)

    ws_path_for_url = f"/{uuid_str[:8]}-vm?ed=2048"
    cf_base = "./cloudflared tunnel --no-autoupdate"
    if argo_token:
        cf_cmd = f"{cf_base} run --token {argo_token}"
    else:
        cf_cmd = f"{cf_base} --url http://localhost:{port_vm_ws}{ws_path_for_url} --edge-ip-version auto --protocol http2"

    cf_start = INSTALL_DIR / "start_cf.sh"
    cf_start.write_text(f"""#!/bin/bash
cd {INSTALL_DIR}
{cf_cmd} > {LOG_FILE.name} 2>&1 &
echo $! > {ARGO_PID_FILE.name}
""")
    os.chmod(cf_start, 0o755)

    # create subscription server script & start script
    create_subscription_server_script(port=subs_port)
    # create start_sub.sh already created by create_subscription_server_script
    write_debug_log("create_startup_script finished")

# ------------------ 安装流程 ------------------
def install(args):
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(INSTALL_DIR)
    write_debug_log("install start")

    uuid_str = args.uuid or os.environ.get("uuid") or str(uuid.uuid4())
    port_vm_ws = args.vmpt or int(os.environ.get("vmpt", 0) or 0)
    if not port_vm_ws:
        port_vm_ws = random.randint(10000, 65535)

    argo_token = args.agk or os.environ.get("agk")
    custom_domain = args.agn or os.environ.get("agn")

    if argo_token and not custom_domain:
        print("\033[31m使用 Argo Token 时必须提供自有域名 (--domain)\033[0m")
        sys.exit(1)

    subs_port = args.subs_port or DEFAULT_SUBS_PORT

    # 下载 sing-box & cloudflared（保持原脚本逻辑，简化少量）
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system != "linux":
        print("仅支持 Linux 系统（脚本当前限制）。")
        sys.exit(1)
    arch = "amd64"
    if "aarch64" in machine or "arm64" in machine:
        arch = "arm64"
    elif "armv7" in machine:
        arch = "arm"

    singbox_path = INSTALL_DIR / "sing-box"
    if not singbox_path.exists():
        try:
            info = http_get("https://api.github.com/repos/SagerNet/sing-box/releases/latest")
            sb_version = json.loads(info)["tag_name"].lstrip("v") if info else "1.9.0-beta.11"
        except Exception:
            sb_version = "1.9.0-beta.11"
        sb_name = f"sing-box-{sb_version}-linux-{arch}"
        if arch == "arm":
            sb_name_actual = f"sing-box-{sb_version}-linux-armv7"
        else:
            sb_name_actual = sb_name
        sb_url = f"https://github.com/SagerNet/sing-box/releases/download/v{sb_version}/{sb_name_actual}.tar.gz"
        tar_path = INSTALL_DIR / "sing-box.tar.gz"
        if not download_file(sb_url, tar_path):
            write_debug_log("sing-box download failed, try backup")
            sb_url_bk = f"https://github.91chi.fun/https://github.com/SagerNet/sing-box/releases/download/v{sb_version}/{sb_name_actual}.tar.gz"
            if not download_file(sb_url_bk, tar_path):
                print("sing-box 下载失败，退出")
                sys.exit(1)
        try:
            import tarfile
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(path=INSTALL_DIR)
            extracted = INSTALL_DIR / sb_name_actual
            if not extracted.exists():
                extracted = INSTALL_DIR / f"sing-box-{sb_version}-linux-{arch}"
            shutil.move(extracted / "sing-box", singbox_path)
            shutil.rmtree(extracted)
            tar_path.unlink()
            os.chmod(singbox_path, 0o755)
        except Exception as e:
            write_debug_log(f"sing-box extract error: {e}")
            sys.exit(1)

    cloudflared_path = INSTALL_DIR / "cloudflared"
    if not cloudflared_path.exists():
        cf_arch = arch if arch != "arm" else "arm"
        cf_url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{cf_arch}"
        if not download_file(cf_url, cloudflared_path):
            cf_url_bk = f"https://github.91chi.fun/https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{cf_arch}"
            if not download_file(cf_url_bk, cloudflared_path):
                print("cloudflared 下载失败，退出")
                sys.exit(1)
        os.chmod(cloudflared_path, 0o755)

    # 写入基础 config
    cfg = {
        "uuid_str": uuid_str,
        "port_vm_ws": port_vm_ws,
        "argo_token": argo_token,
        "custom_domain_agn": custom_domain,
        "install_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "subscription_port": subs_port
    }
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)

    # create sing-box config and startup scripts
    create_sing_box_config(port_vm_ws, uuid_str)
    create_startup_script()

    # set crontab autostart (includes start_sb.sh, start_cf.sh, start_sub.sh)
    setup_autostart()

    # start services
    start_services()
    # start subscription server (background via start_sub.sh)
    start_subscription_server(port=subs_port)

    # wait for quick tunnel domain if needed
    final_domain = custom_domain
    if not argo_token and not custom_domain:
        print("等待 Quick Tunnel 生成临时域名...")
        final_domain = get_tunnel_domain()
        if not final_domain:
            print("\033[31m无法获取临时域名，请指定 --domain 或检查 log。\033[0m")
            sys.exit(1)

    # generate links (may perform concurrent probe)
    generate_links(final_domain, port_vm_ws, uuid_str, fast_mode=args.fast, subs_port=subs_port)
    print("\033[32m安装完成。请检查订阅 URL 并在客户端中使用。\033[0m")

# ------------------ create_sing_box_config ------------------
def create_sing_box_config(port_vm_ws, uuid_str):
    ws_path = f"/{uuid_str[:8]}-vm"
    cfg = {
        "log": {"level": "info", "timestamp": True},
        "inbounds": [{
            "type": "vmess", "tag": "vmess-in", "listen": "127.0.0.1",
            "listen_port": port_vm_ws, "tcp_fast_open": True, "sniff": True,
            "sniff_override_destination": True, "proxy_protocol": False,
            "users": [{"uuid": uuid_str, "alterId": 0}],
            "transport": {"type": "ws", "path": ws_path, "max_early_data": 2048, "early_data_header_name": "Sec-WebSocket-Protocol"}
        }],
        "outbounds": [{"type": "direct", "tag": "direct"}]
    }
    with open(INSTALL_DIR / "sb.json", 'w') as f:
        json.dump(cfg, f, indent=2)
    write_debug_log("sing-box config written")

# ------------------ autostart (crontab) ------------------
def setup_autostart():
    try:
        current = subprocess.check_output("crontab -l 2>/dev/null || true", shell=True, text=True)
        lines = [l for l in current.splitlines() if l.strip()]
        sb = (INSTALL_DIR / "start_sb.sh").resolve()
        cf = (INSTALL_DIR / "start_cf.sh").resolve()
        sub = (INSTALL_DIR / "start_sub.sh").resolve()
        # remove existing entries referencing these scripts
        filtered = [l for l in lines if str(sb) not in l and str(cf) not in l and str(sub) not in l]
        filtered.append(f"@reboot {sb} >/dev/null 2>&1")
        filtered.append(f"@reboot {cf} >/dev/null 2>&1")
        filtered.append(f"@reboot {sub} >/dev/null 2>&1")
        tmp = tempfile.NamedTemporaryFile(mode='w', delete=False)
        tmp.write("\n".join(filtered) + "\n")
        tmp.close()
        subprocess.run(f"crontab {tmp.name}", shell=True, check=True)
        os.unlink(tmp.name)
        write_debug_log("crontab set")
    except Exception as e:
        write_debug_log(f"setup_autostart failed: {e}")

# ------------------ start / stop services ------------------
def start_services():
    try:
        subprocess.run(str(INSTALL_DIR / "start_sb.sh"), shell=True)
        subprocess.run(str(INSTALL_DIR / "start_cf.sh"), shell=True)
        write_debug_log("started sing-box and cloudflared")
    except Exception as e:
        write_debug_log(f"start_services error: {e}")

# ------------------ get Quick Tunnel domain ------------------
def get_tunnel_domain():
    for i in range(25):
        if LOG_FILE.exists():
            try:
                c = LOG_FILE.read_text()
                m = re.search(r'https://([a-zA-Z0-9.-]+\.trycloudflare\.com)', c)
                if m:
                    return m.group(1)
            except Exception:
                pass
        time.sleep(3)
    return None

# ------------------ uninstall / upgrade / status / cat ------------------
def uninstall():
    # stop pids
    for pidf in [SB_PID_FILE, ARGO_PID_FILE, SUBS_PID_FILE]:
        if pidf.exists():
            try:
                pid = pidf.read_text().strip()
                if pid:
                    os.system(f"kill {pid} 2>/dev/null || true")
            except Exception:
                pass
    # pkill
    os.system("pkill -9 -f 'sing-box run -c sb.json' 2>/dev/null || true")
    os.system("pkill -9 -f 'cloudflared tunnel' 2>/dev/null || true")
    os.system("pkill -9 -f 'serve_sub.py' 2>/dev/null || true")
    # remove crontab entries referencing our scripts
    try:
        cur = subprocess.check_output("crontab -l 2>/dev/null || true", shell=True, text=True)
        lines = [l for l in cur.splitlines() if l.strip()]
        sb = str((INSTALL_DIR / "start_sb.sh").resolve())
        cf = str((INSTALL_DIR / "start_cf.sh").resolve())
        sub = str((INSTALL_DIR / "start_sub.sh").resolve())
        filtered = [l for l in lines if sb not in l and cf not in l and sub not in l]
        if filtered:
            tmp = tempfile.NamedTemporaryFile(mode='w', delete=False)
            tmp.write("\n".join(filtered) + "\n")
            tmp.close()
            subprocess.run(f"crontab {tmp.name}", shell=True)
            os.unlink(tmp.name)
        else:
            subprocess.run("crontab -r", shell=True)
    except Exception:
        pass
    # remove install dir
    try:
        if INSTALL_DIR.exists():
            shutil.rmtree(INSTALL_DIR)
    except Exception:
        pass
    print("卸载完成。")

def upgrade():
    script_url = "https://raw.githubusercontent.com/yonggekkk/argosb/main/agsb_custom_domain.py"
    content = http_get(script_url)
    if not content:
        print("升级失败，无法下载脚本。")
        return
    p = Path(__file__).resolve()
    bak = p.with_suffix(p.suffix + ".bak")
    shutil.copyfile(p, bak)
    with open(p, 'w') as f:
        f.write(content)
    os.chmod(p, 0o755)
    print("升级完成，请重新运行脚本。")

def check_status():
    sb_ok = SB_PID_FILE.exists() and os.path.exists(f"/proc/{SB_PID_FILE.read_text().strip()}") if SB_PID_FILE.exists() else False
    cf_ok = ARGO_PID_FILE.exists() and os.path.exists(f"/proc/{ARGO_PID_FILE.read_text().strip()}") if ARGO_PID_FILE.exists() else False
    subs_ok = SUBS_PID_FILE.exists() and os.path.exists(f"/proc/{SUBS_PID_FILE.read_text().strip()}") if SUBS_PID_FILE.exists() else False
    print("sing-box:", "运行" if sb_ok else "未运行")
    print("cloudflared:", "运行" if cf_ok else "未运行")
    print("subscription server:", "运行" if subs_ok else "未运行")
    if LIST_FILE.exists():
        print("\n简要信息:")
        print(LIST_FILE.read_text())

def cat_nodes():
    p = INSTALL_DIR / "allnodes.txt"
    if p.exists():
        print(p.read_text().strip())
    else:
        print("allnodes.txt 不存在。")

# ------------------ main ------------------
def main():
    args = parse_args()
    print_info()
    if args.action == "install":
        install(args)
    elif args.action in ("del", "uninstall"):
        uninstall()
    elif args.action == "update":
        upgrade()
    elif args.action == "status":
        check_status()
    elif args.action == "cat":
        cat_nodes()
    else:
        print("未知命令")

if __name__ == "__main__":
    main()
