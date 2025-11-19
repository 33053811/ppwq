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

# ---------------- 全局变量 ----------------
INSTALL_DIR = Path.home() / ".agsb"
CONFIG_FILE = INSTALL_DIR / "config.json"
SB_PID_FILE = INSTALL_DIR / "sbpid.log"
ARGO_PID_FILE = INSTALL_DIR / "sbargopid.log"
LIST_FILE = INSTALL_DIR / "list.txt"
LOG_FILE = INSTALL_DIR / "argo.log"
DEBUG_LOG = INSTALL_DIR / "python_debug.log"
CUSTOM_DOMAIN_FILE = INSTALL_DIR / "custom_domain.txt"

# ---------------- 命令行参数 ----------------
def parse_args():
    parser = argparse.ArgumentParser(description="ArgoSB Python3 一键脚本 (自定义域名 & Argo Token)")
    parser.add_argument("action", nargs="?", default="install",
                        choices=["install", "status", "update", "del", "uninstall", "cat"])
    parser.add_argument("--domain", "-d", dest="agn", help="自定义域名")
    parser.add_argument("--uuid", "-u", help="自定义UUID")
    parser.add_argument("--port", "-p", dest="vmpt", type=int, help="自定义Vmess端口")
    parser.add_argument("--agk", "--token", dest="agk", help="Argo Tunnel Token")
    return parser.parse_args()

# ---------------- 网络请求 ----------------
def http_get(url, timeout=10):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        headers = {'User-Agent':'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.read().decode()
    except Exception as e:
        write_debug_log(f"HTTP GET失败: {url}, {e}")
        return None

def download_file(url, target_path, mode='wb'):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        headers = {'User-Agent':'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx) as response, open(target_path, mode) as f:
            shutil.copyfileobj(response, f)
        return True
    except Exception as e:
        write_debug_log(f"下载失败: {url}, {e}")
        return False

# ---------------- 日志 ----------------
def write_debug_log(message):
    try:
        if not INSTALL_DIR.exists():
            INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now()}] {message}\n")
    except:
        pass

# ---------------- 生成 VMess 链接 ----------------
def generate_vmess_link(config):
    vmess_obj = {
        "v":"2","ps":config.get("ps","ArgoSB"),
        "add":config.get("add",""),
        "port":str(config.get("port","443")),
        "id":config.get("id",""),
        "aid":str(config.get("aid","0")),
        "net":config.get("net","ws"),
        "type":config.get("type","none"),
        "host":config.get("host",""),
        "path":config.get("path",""),
        "tls":config.get("tls","tls"),
        "sni":config.get("sni","")
    }
    return "vmess://" + base64.b64encode(json.dumps(vmess_obj).encode()).decode().rstrip("=")

# ---------------- 占位函数 ----------------
def create_sing_box_config(port, uuid_str):
    sb_json = {
        "inbounds":[{"type":"vmess","listen":"127.0.0.1","port":port,"users":[{"id":uuid_str,"alterId":0}]}],
        "outbounds":[{"type":"direct"}]
    }
    with open(INSTALL_DIR / "sb.json", 'w') as f:
        json.dump(sb_json, f, indent=2)

def create_startup_script():
    # 简化示例
    start_sb = f"#!/bin/bash\ncd {INSTALL_DIR} && ./sing-box run -c sb.json > sb.log 2>&1 & echo $! > {SB_PID_FILE}\n"
    start_cf = f"#!/bin/bash\ncd {INSTALL_DIR} && ./cloudflared tunnel --url http://127.0.0.1:9999 > argo.log 2>&1 & echo $! > {ARGO_PID_FILE}\n"
    with open(INSTALL_DIR / "start_sb.sh",'w') as f: f.write(start_sb)
    with open(INSTALL_DIR / "start_cf.sh",'w') as f: f.write(start_cf)
    os.chmod(INSTALL_DIR / "start_sb.sh",0o755)
    os.chmod(INSTALL_DIR / "start_cf.sh",0o755)

def start_services():
    os.system(f"{INSTALL_DIR}/start_sb.sh")
    os.system(f"{INSTALL_DIR}/start_cf.sh")
    print("服务已启动")

def get_tunnel_domain():
    # 简单尝试从 argo.log 获取 trycloudflare.com
    if LOG_FILE.exists():
        content = LOG_FILE.read_text()
        match = re.search(r'https://([a-zA-Z0-9.-]+\.trycloudflare\.com)', content)
        if match: return match.group(1)
    return None

# ---------------- 安装 ----------------
def install(args):
    if not INSTALL_DIR.exists(): INSTALL_DIR.mkdir(parents=True)
    uuid_str = args.uuid or os.environ.get("uuid") or str(uuid.uuid4())
    port_vm_ws = args.vmpt or int(os.environ.get("vmpt", random.randint(10000,65535)))
    argo_token = args.agk or os.environ.get("agk")
    custom_domain = args.agn or os.environ.get("agn")
    create_sing_box_config(port_vm_ws, uuid_str)
    create_startup_script()
    start_services()
    final_domain = custom_domain or get_tunnel_domain() or "example.trycloudflare.com"
    generate_links(final_domain, port_vm_ws, uuid_str)
    print(f"安装完成，域名: {final_domain}")

# ---------------- 入口 ----------------
def main():
    args = parse_args()
    if args.action in ["install"]:
        install(args)
    elif args.action in ["del","uninstall"]:
        uninstall()
    elif args.action=="update":
        upgrade()
    elif args.action=="status":
        check_status()
    elif args.action=="cat":
        if (INSTALL_DIR / "allnodes.txt").exists():
            print((INSTALL_DIR / "allnodes.txt").read_text())
        else:
            print("节点文件不存在")
    else:
        print("未知操作")

# ---------------- 其他占位 ----------------
def uninstall(): print("卸载功能暂未实现")
def upgrade(): print("升级功能暂未实现")
def check_status(): print("状态功能暂未实现")
def generate_links(domain, port_vm_ws, uuid_str): print(f"生成节点 {domain} {uuid_str} {port_vm_ws}")

if __name__=="__main__":
    main()

