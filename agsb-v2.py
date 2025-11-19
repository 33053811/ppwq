#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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

# 需要 netaddr 来处理 CIDR 段展开
try:
    from netaddr import IPNetwork, IPAddress
except ImportError:
    print("请先安装 netaddr 库：pip3 install netaddr")
    sys.exit(1)

# 全局变量
INSTALL_DIR = Path.home() / ".agsb"
CONFIG_FILE = INSTALL_DIR / "config.json"
SB_PID_FILE = INSTALL_DIR / "sbpid.log"
ARGO_PID_FILE = INSTALL_DIR / "sbargopid.log"
LIST_FILE = INSTALL_DIR / "list.txt"
LOG_FILE = INSTALL_DIR / "argo.log"
DEBUG_LOG = INSTALL_DIR / "python_debug.log"
CUSTOM_DOMAIN_FILE = INSTALL_DIR / "custom_domain.txt"

# ---------- 参数解析 ----------
def parse_args():
    parser = argparse.ArgumentParser(description="ArgoSB Python3 一键脚本 (支持动态 Cloudflare IP 段)")
    parser.add_argument("action", nargs="?", default="install",
                        choices=["install", "status", "update", "del", "uninstall", "cat"])
    parser.add_argument("--domain", "-d", dest="agn", help="自定义域名")
    parser.add_argument("--uuid", "-u", help="自定义 UUID")
    parser.add_argument("--port", "-p", dest="vmpt", type=int, help="自定义 Vmess 端口")
    parser.add_argument("--agk", "--token", dest="agk", help="Argo Tunnel Token")

    return parser.parse_args()

# ---------- 网络 / HTTP ----------
def http_get(url, timeout=10):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.read().decode('utf-8')
    except Exception as e:
        write_debug_log(f"HTTP 请求失败 {url}：{e}")
        return None

def download_file(url, target_path, mode='wb'):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx) as response, open(target_path, mode) as out_file:
            shutil.copyfileobj(response, out_file)
        return True
    except Exception as e:
        write_debug_log(f"下载失败 {url}：{e}")
        return False

# ---------- 日志 ----------
def write_debug_log(msg):
    try:
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, 'a', encoding='utf-8') as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {msg}\n")
    except:
        pass

# ---------- VMess 链接生成 ----------
def generate_vmess_link(cfg):
    obj = {
        "v": "2",
        "ps": cfg.get("ps", ""),
        "add": cfg.get("add", ""),
        "port": str(cfg.get("port", "")),
        "id": cfg.get("id", ""),
        "aid": str(cfg.get("aid", "0")),
        "net": cfg.get("net", "ws"),
        "type": cfg.get("type", "none"),
        "host": cfg.get("host", ""),
        "path": cfg.get("path", ""),
        "tls": cfg.get("tls", ""),
        "sni": cfg.get("sni", "")
    }
    s = json.dumps(obj, sort_keys=True)
    b = base64.b64encode(s.encode('utf-8')).decode('utf-8').rstrip("=")
    return f"vmess://{b}"

# ---------- IP 探测与优选 ----------
def probe_tcp_latency(ip, port, timeout=2.0):
    start = time.time()
    try:
        with socket.create_connection((ip, int(port)), timeout=timeout):
            return time.time() - start
    except:
        return None

def probe_tls_http_check(ip, port, host, path='/', timeout=3.0):
    try:
        start = time.time()
        sock = socket.create_connection((ip, int(port)), timeout=timeout)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ss = ctx.wrap_socket(sock, server_hostname=host)
        req = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\nUser-Agent: Probe/1.0\r\n\r\n"
        ss.sendall(req.encode('utf-8'))
        chunk = ss.recv(1024)
        ss.close()
        rtt = time.time() - start
        ok = False
        if chunk:
            s = chunk.decode('latin1', errors='ignore').lower()
            if 'http/1.' in s or 'cloudflare' in s or '<html' in s:
                ok = True
        return (rtt, ok, s)
    except Exception as e:
        return (None, False, "")

def prefer_ips(candidate_ips, port=443, host=None, path='/', top_n=3, mode='tcp'):
    results = []
    for ip in candidate_ips:
        try:
            if mode == 'tcp':
                rtt = probe_tcp_latency(ip, port)
                ok = rtt is not None
                score = rtt if ok else 9999
                results.append((ip, score, ok, 'tcp'))
            else:
                rtt, ok, _ = probe_tls_http_check(ip, port, host or ip, path=path)
                if rtt is None:
                    results.append((ip, 9999, False, 'tlshttp'))
                else:
                    score = rtt if ok else (rtt + 5.0)
                    results.append((ip, score, ok, 'tlshttp'))
        except Exception as e:
            results.append((ip, 9999, False, 'err'))
    results.sort(key=lambda x: (not x[2], x[1]))
    write_debug_log(f"探测结果 (top {top_n}): {results[:top_n]}")
    return [r[0] for r in results[:top_n]]

# ---------- 拉取 Cloudflare IPv4 段 ----------
def fetch_cf_ipv4_cidrs():
    url = "https://www.cloudflare.com/ips-v4"  # 官方 IPv4 段列表 :contentReference[oaicite:0]{index=0}
    txt = http_get(url)
    if not txt:
        write_debug_log("拉取 Cloudflare IPv4 段失败，使用默认小段")
        return []
    lines = txt.splitlines()
    cidrs = [l.strip() for l in lines if l.strip() and '/' in l]
    write_debug_log(f"获得 Cloudflare IPv4 段: {cidrs}")
    return cidrs

def expand_cidrs_to_ips(cidrs, max_ips_per_cidr=3):
    """
    将每个 CIDR 展开成几条 IP 候选，默认每个段取前几个（例如 /20 取头几个 IP）
    """
    ips = []
    for cidr in cidrs:
        try:
            net = IPNetwork(cidr)
            # 从这个网段里选择几个 IP：起始、第二、最后几个，避免选择广播 / 网络地址
            cnt = min(max_ips_per_cidr, net.size)
            # pick spaced inside
            for i in range(cnt):
                ip = str(IPAddress(net.first + i))
                ips.append(ip)
        except Exception as e:
            write_debug_log(f"展开 CIDR {cidr} 出错: {e}")
    write_debug_log(f"展开后的 IP 候选数: {len(ips)}")
    return ips

# ---------- 生成链接（使用动态 IP 段） ----------
def generate_links(domain, port_vm_ws, uuid_str):
    write_debug_log(f"generate_links: domain={domain}, port={port_vm_ws}, uuid={uuid_str}")
    ws_path = f"/{uuid_str[:8]}-vm"
    ws_path_full = f"{ws_path}?ed=2048"
    hostname = socket.gethostname()[:10]

    # 拉取 Cloudflare 段 + 展开 IP
    cidrs = fetch_cf_ipv4_cidrs()
    expanded_ips = expand_cidrs_to_ips(cidrs, max_ips_per_cidr=5)

    # 优选 IP
    if domain:
        tls_candidates = prefer_ips(expanded_ips, port=443, host=domain, path=ws_path, top_n=4, mode='tlshttp')
        http_candidates = prefer_ips(expanded_ips, port=80, host=domain, path=ws_path, top_n=2, mode='tcp')
    else:
        tls_candidates = prefer_ips(expanded_ips, port=443, host=None, path=ws_path, top_n=4, mode='tcp')
        http_candidates = prefer_ips(expanded_ips, port=80, host=None, path=ws_path, top_n=2, mode='tcp')

    write_debug_log(f"优选 TLS IP: {tls_candidates}")
    write_debug_log(f"优选 HTTP IP: {http_candidates}")

    # 写入 config
    try:
        cfg = json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
    except:
        cfg = {}
    cfg["preferred_ips_tls"] = tls_candidates
    cfg["preferred_ips_http"] = http_candidates
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)

    all_links = []
    link_names = []

    # TLS 节点
    for ip in tls_candidates:
        cfg_node = {
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
        all_links.append(generate_vmess_link(cfg_node))
        link_names.append(cfg_node["ps"])

    # HTTP 节点
    for ip in http_candidates:
        cfg_node = {
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
        all_links.append(generate_vmess_link(cfg_node))
        link_names.append(cfg_node["ps"])

    # 直接域名
    if domain:
        cfg_tls_direct = {
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
        all_links.append(generate_vmess_link(cfg_tls_direct))
        link_names.append(cfg_tls_direct["ps"])

        cfg_http_direct = {
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
        all_links.append(generate_vmess_link(cfg_http_direct))
        link_names.append(cfg_http_direct["ps"])

    # 写文件
    (INSTALL_DIR / "allnodes.txt").write_text("\n".join(all_links) + "\n")
    (INSTALL_DIR / "vmess_round_robin.txt").write_text("\n".join(all_links) + "\n")
    if domain:
        CUSTOM_DOMAIN_FILE.write_text(domain)

    # 写 LIST_FILE（状态用）
    list_lines = []
    list_lines.append(f"域名: {domain}")
    list_lines.append(f"UUID: {uuid_str}")
    list_lines.append(f"WS 路径: {ws_path_full}")
    for i, l in enumerate(all_links):
        list_lines.append(f"{i+1}. {link_names[i]} -> {l}")
    LIST_FILE.write_text("\n".join(list_lines))

    # 打印
    print("生成以下节点链接：")
    for i, l in enumerate(all_links):
        print(f"{i+1}. {link_names[i]} → {l}")

    return True

# ---------- 创建 sing-box config ----------
def create_sing_box_config(port_vm_ws, uuid_str):
    ws_path = f"/{uuid_str[:8]}-vm"
    cfg = {
        "log": {"level":"info","timestamp": True},
        "inbounds": [
            {
                "type": "vmess",
                "tag": "vmess-in",
                "listen": "127.0.0.1",
                "listen_port": port_vm_ws,
                "users": [{"uuid": uuid_str, "alterId": 0}],
                "transport": {
                    "type": "ws",
                    "path": ws_path,
                    "max_early_data": 2048,
                    "early_data_header_name": "Sec‑WebSocket‑Protocol"
                }
            }
        ],
        "outbounds": [{"type":"direct", "tag":"direct"}]
    }
    sbf = INSTALL_DIR / "sb.json"
    with open(sbf, "w") as f:
        json.dump(cfg, f, indent=2)
    write_debug_log("sing-box 配置已写好")

# ---------- 启动脚本 (简化) ----------
def create_startup_script():
    config = json.loads(CONFIG_FILE.read_text())
    port_vm_ws = config["port_vm_ws"]
    uuid_str = config["uuid_str"]
    argo_token = config.get("argo_token")
    domain = config.get("custom_domain_agn")

    sb_script = INSTALL_DIR / "start_sb.sh"
    sb_script.write_text(f"""#!/bin/bash
cd {INSTALL_DIR}
./sing-box run -c sb.json > sb.log 2>&1 &
echo $! > {SB_PID_FILE.name}
""")
    os.chmod(sb_script, 0o755)

    cf_script = INSTALL_DIR / "start_cf.sh"
    ws_path_for = f"/{uuid_str[:8]}-vm?ed=2048"
    if argo_token:
        cf_cmd = f"./cloudflared tunnel --no-autoupdate run --token {argo_token}"
    else:
        cf_cmd = f"./cloudflared tunnel --no-autoupdate --url http://localhost:{port_vm_ws}{ws_path_for} --edge-ip-version auto --protocol http2"
    cf_script.write_text(f"""#!/bin/bash
cd {INSTALL_DIR}
{cf_cmd} > {LOG_FILE.name} 2>&1 &
echo $! > {ARGO_PID_FILE.name}
""")
    os.chmod(cf_script, 0o755)
    write_debug_log("启动脚本已写")

# ---------- 启动服务 ----------
def start_services():
    subprocess.run(str(INSTALL_DIR / "start_sb.sh"), shell=True)
    subprocess.run(str(INSTALL_DIR / "start_cf.sh"), shell=True)
    time.sleep(5)

# ---------- 卸载 ----------
def uninstall():
    # 同你之前逻辑
    for pf in [SB_PID_FILE, ARGO_PID_FILE]:
        if pf.exists():
            pid = pf.read_text().strip()
            os.system(f"kill {pid} 2>/dev/null || true")
    time.sleep(1)
    os.system("pkill -9 -f 'sing-box' || true")
    os.system("pkill -9 -f 'cloudflared' || true")

    try:
        cr = subprocess.check_output("crontab -l 2>/dev/null || echo ''", shell=True, text=True).splitlines()
        new = [l for l in cr if str((INSTALL_DIR/"start_sb.sh").resolve()) not in l and str((INSTALL_DIR/"start_cf.sh").resolve()) not in l]
        tmp = tempfile.NamedTemporaryFile(mode='w', delete=False)
        tmp.write("\n".join(new) + "\n")
        tmp.close()
        subprocess.run(f"crontab {tmp.name}", shell=True)
        os.unlink(tmp.name)
    except Exception as e:
        write_debug_log(f"卸载 crontab 出错: {e}")

    try:
        shutil.rmtree(INSTALL_DIR)
    except Exception as e:
        print("删除安装目录失败: ", e)
    print("卸载完成")
    sys.exit(0)

# ---------- 升级 (略，可复用你之前) ----------
def upgrade():
    # …略，在这里插入你原来的升级逻辑
    pass

# ---------- 检查状态 (略) ----------
def check_status():
    # …略，你可以复用原来 status 逻辑
    pass

# ---------- 安装流程 ----------
def install(args):
    if not INSTALL_DIR.exists():
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    uuid_str = args.uuid or os.environ.get("uuid") or str(uuid.uuid4())
    port_vm_ws = args.vmpt or int(os.environ.get("vmpt", 0)) or random.randint(10000, 60000)
    argo_token = args.agk or os.environ.get("agk")
    custom_domain = args.agn or os.environ.get("agn")

    config = {
        "uuid_str": uuid_str,
        "port_vm_ws": port_vm_ws,
        "argo_token": argo_token,
        "custom_domain_agn": custom_domain,
        "install_date": datetime.now().isoformat()
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

    # 你还需要下载 sing-box/cloudflared，这里复用你之前逻辑（略）
    # …（下载 sing-box & cloudflared）

    create_sing_box_config(port_vm_ws, uuid_str)
    create_startup_script()
    start_services()

    final_domain = custom_domain
    if not final_domain:
        final_domain = get_tunnel_domain()
    generate_links(final_domain, port_vm_ws, uuid_str)

# ---------- 获取 tunnel 域名 (Quick Tunnel) ----------
def get_tunnel_domain():
    # 复用你之前逻辑
    count = 0
    while count < 15:
        if LOG_FILE.exists():
            content = LOG_FILE.read_text()
            m = re.search(r'https://([a-zA-Z0-9.-]+\.trycloudflare\.com)', content)
            if m:
                return m.group(1)
        time.sleep(3)
        count += 1
    return None

# ---------- 主函数 ----------
def main():
    args = parse_args()
    if args.action in ("install",):
        install(args)
    elif args.action in ("del","uninstall"):
        uninstall()
    elif args.action == "status":
        check_status()
    elif args.action == "update":
        upgrade()
    elif args.action == "cat":
        if (INSTALL_DIR / "allnodes.txt").exists():
            print((INSTALL_DIR / "allnodes.txt").read_text())
        else:
            print("节点还没生成")

if __name__ == "__main__":
    main()
