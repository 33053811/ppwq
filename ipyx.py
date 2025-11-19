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
import tarfile

# -----------------------------
# 全局变量
# -----------------------------
INSTALL_DIR = Path.home() / ".agsb"
CONFIG_FILE = INSTALL_DIR / "config.json"
SB_PID_FILE = INSTALL_DIR / "sbpid.log"
ARGO_PID_FILE = INSTALL_DIR / "sbargopid.log"
LIST_FILE = INSTALL_DIR / "list.txt"
LOG_FILE = INSTALL_DIR / "argo.log"
DEBUG_LOG = INSTALL_DIR / "python_debug.log"
CUSTOM_DOMAIN_FILE = INSTALL_DIR / "custom_domain.txt"

# 纯净IP列表 (可手动维护或通过网络抓取)
PURE_IP_TLS = {
    "104.16.0.0": "443",
    "104.17.0.0": "443",
    "104.18.0.0": "443",
    "104.19.0.0": "443",
    "104.20.0.0": "443",
}
PURE_IP_HTTP = {
    "104.21.0.0": "80",
    "104.22.0.0": "8080",
    "104.24.0.0": "8880",
}

# -----------------------------
# 工具函数
# -----------------------------
def write_debug_log(message):
    try:
        if not INSTALL_DIR.exists():
            INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        print(f"写入日志失败: {e}")

def http_get(url, timeout=10):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        headers = {
            'User-Agent': 'Mozilla/5.0'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        write_debug_log(f"HTTP GET Error: {url}, {e}")
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
        write_debug_log(f"Download Error: {url}, {e}")
        return False

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
    vmess_str = json.dumps(vmess_obj, sort_keys=True)
    vmess_b64 = base64.b64encode(vmess_str.encode('utf-8')).decode('utf-8').rstrip("=")
    return f"vmess://{vmess_b64}"

# -----------------------------
# 链接生成（带纯净IP优选）
# -----------------------------
def generate_links(domain, port_vm_ws, uuid_str):
    ws_path = f"/{uuid_str[:8]}-vm?ed=2048"
    hostname = socket.gethostname()[:10]
    all_links = []
    link_names = []

    # TLS节点
    for ip, port_cf in PURE_IP_TLS.items():
        ps_name = f"VMWS-TLS-{hostname}-{ip.split('.')[2]}-{port_cf}"
        config = {
            "ps": ps_name, "add": ip, "port": port_cf, "id": uuid_str, "aid": "0",
            "net": "ws", "type": "none", "host": domain, "path": ws_path,
            "tls": "tls", "sni": domain
        }
        all_links.append(generate_vmess_link(config))
        link_names.append(f"TLS-{port_cf}-{ip}")

    # HTTP节点
    for ip, port_cf in PURE_IP_HTTP.items():
        ps_name = f"VMWS-HTTP-{hostname}-{ip.split('.')[2]}-{port_cf}"
        config = {
            "ps": ps_name, "add": ip, "port": port_cf, "id": uuid_str, "aid": "0",
            "net": "ws", "type": "none", "host": domain, "path": ws_path,
            "tls": ""
        }
        all_links.append(generate_vmess_link(config))
        link_names.append(f"HTTP-{port_cf}-{ip}")

    # Direct域名节点
    direct_tls = {
        "ps": f"VMWS-TLS-{hostname}-Direct-{domain[:15]}-443",
        "add": domain, "port": "443", "id": uuid_str, "aid": "0",
        "net": "ws", "type": "none", "host": domain, "path": ws_path,
        "tls": "tls", "sni": domain
    }
    direct_http = {
        "ps": f"VMWS-HTTP-{hostname}-Direct-{domain[:15]}-80",
        "add": domain, "port": "80", "id": uuid_str, "aid": "0",
        "net": "ws", "type": "none", "host": domain, "path": ws_path,
        "tls": ""
    }
    all_links.append(generate_vmess_link(direct_tls))
    all_links.append(generate_vmess_link(direct_http))
    link_names.append(f"TLS-Direct-{domain}-443")
    link_names.append(f"HTTP-Direct-{domain}-80")

    # 保存文件
    (INSTALL_DIR / "allnodes.txt").write_text("\n".join(all_links))
    CUSTOM_DOMAIN_FILE.write_text(domain)

    # 打印节点信息
    print(f"生成完成，共 {len(all_links)} 个节点，域名: {domain}\n")
    for i, link in enumerate(all_links):
        print(f"{link_names[i]}: {link}")

# -----------------------------
# 安装流程
# -----------------------------
def install(args):
    if not INSTALL_DIR.exists():
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    uuid_str = args.uuid or str(uuid.uuid4())
    port_vm_ws = args.vmpt or random.randint(10000, 65535)
    custom_domain = args.agn or None
    argo_token = args.agk or None

    # 保存配置
    config_data = {
        "uuid": uuid_str,
        "port": port_vm_ws,
        "domain": custom_domain,
        "argo_token": argo_token,
        "install_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=2)

    # 下载 sing-box & cloudflared
    print("请确保 sing-box 与 cloudflared 已下载到安装目录")

    # 启动服务（占位）
    print("启动服务逻辑略，需根据实际 sing-box 配置实现")

    # 生成 VMess 节点
    final_domain = custom_domain or "your-auto-domain.trycloudflare.com"
    generate_links(final_domain, port_vm_ws, uuid_str)

# -----------------------------
# 卸载
# -----------------------------
def uninstall():
    if INSTALL_DIR.exists():
        shutil.rmtree(INSTALL_DIR)
        print(f"已删除安装目录 {INSTALL_DIR}")
    print("卸载完成。")

# -----------------------------
# 参数解析
# -----------------------------
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", nargs="?", default="install", choices=["install", "uninstall"])
    parser.add_argument("--uuid", "-u")
    parser.add_argument("--vmpt", type=int)
    parser.add_argument("--agn", "-d")
    parser.add_argument("--agk", "--token")
    return parser.parse_args()

# -----------------------------
# 主函数
# -----------------------------
if __name__ == "__main__":
    args = parse_args()
    if args.action == "install":
        install(args)
    elif args.action == "uninstall":
        uninstall()
    else:
        print("未知操作")
