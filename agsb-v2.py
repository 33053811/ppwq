#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import base64
import socket
import random
import time
import ipaddress
from pathlib import Path
from datetime import datetime
import urllib.request
import ssl
import uuid

# 全局路径
INSTALL_DIR = Path.home() / ".cf_vmess"
CONFIG_FILE = INSTALL_DIR / "config.json"
ALLNODES_FILE = INSTALL_DIR / "allnodes.txt"

# ---------- HTTP GET ----------
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
        print(f"HTTP 请求失败 {url}: {e}")
        return None

# ---------- VMess 链接生成 ----------
def generate_vmess_link(cfg):
    """
    cfg: dict
    """
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

# ---------- 拉取 Cloudflare IPv4 段 ----------
def fetch_cf_ipv4_cidrs():
    url = "https://www.cloudflare.com/ips-v4"
    txt = http_get(url)
    if not txt:
        return []
    lines = txt.splitlines()
    cidrs = [l.strip() for l in lines if '/' in l]
    return cidrs

# ---------- 展开 CIDR 段为 IP 列表 ----------
def expand_cidrs_to_ips(cidrs, max_ips_per_cidr=3):
    ips = []
    for cidr in cidrs:
        try:
            net = ipaddress.IPv4Network(cidr, strict=False)
            count = min(max_ips_per_cidr, net.num_addresses)
            for i, ip in enumerate(net.hosts()):
                if i >= count:
                    break
                ips.append(str(ip))
        except Exception as e:
            print(f"CIDR 展开失败 {cidr}: {e}")
    return ips

# ---------- TCP 探测延迟 ----------
def probe_tcp_latency(ip, port, timeout=2.0):
    start = time.time()
    try:
        with socket.create_connection((ip, int(port)), timeout=timeout):
            return time.time() - start
    except:
        return None

# ---------- 优选 IP ----------
def prefer_ips(candidate_ips, port=443, top_n=3):
    results = []
    for ip in candidate_ips:
        rtt = probe_tcp_latency(ip, port)
        ok = rtt is not None
        score = rtt if ok else 9999
        results.append((ip, score, ok))
    results.sort(key=lambda x: (not x[2], x[1]))
    return [r[0] for r in results[:top_n]]

# ---------- 生成 VMess 节点 ----------
def generate_links(domain, uuid_str):
    INSTALL_DIR.mkdir(exist_ok=True, parents=True)
    ws_path = f"/{uuid_str[:8]}-vm"
    ws_path_full = f"{ws_path}?ed=2048"
    hostname = socket.gethostname()[:10]

    # 获取 Cloudflare IP
    cidrs = fetch_cf_ipv4_cidrs()
    ips = expand_cidrs_to_ips(cidrs, max_ips_per_cidr=5)

    # 优选 IP
    tls_ips = prefer_ips(ips, port=443, top_n=4)
    http_ips = prefer_ips(ips, port=80, top_n=2)

    all_links = []
    link_names = []

    # TLS 节点
    for ip in tls_ips:
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
    for ip in http_ips:
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

    # 域名直连节点
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

    # 保存 config.json
    cfg_json = {
        "uuid_str": uuid_str,
        "domain": domain,
        "preferred_ips_tls": tls_ips,
        "preferred_ips_http": http_ips,
        "ws_path": ws_path_full,
        "generated_at": datetime.now().isoformat()
    }
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg_json, f, indent=2)

    # 保存所有 vmess 链接
    with open(ALLNODES_FILE, 'w') as f:
        for link in all_links:
            f.write(link + "\n")

    print("生成的节点链接:")
    for i, link in enumerate(all_links):
        print(f"{i+1}. {link_names[i]} → {link}")

    return all_links

# ---------- 主程序 ----------
def main():
    INSTALL_DIR.mkdir(exist_ok=True, parents=True)
    # 可以传参数 domain 和 uuid
    domain = sys.argv[1] if len(sys.argv) > 1 else None
    uuid_str = sys.argv[2] if len(sys.argv) > 2 else str(uuid.uuid4())
    generate_links(domain, uuid_str)

if __name__ == "__main__":
    main()
