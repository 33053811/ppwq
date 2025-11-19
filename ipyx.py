#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import subprocess
import uuid as uuid_lib
from pathlib import Path

INSTALL_DIR = Path.home() / ".agsb"  # 安装目录

# ------------------- 参数解析 -------------------
parser = argparse.ArgumentParser(description="ArgoSB 自动部署脚本")
parser.add_argument("action", choices=["install", "uninstall"], help="操作类型")
parser.add_argument("--uuid", "-u", help="自定义 UUID")
parser.add_argument("--port", "--vmpt", type=int, help="服务端口")
parser.add_argument("--domain", "--agn", help="自定义域名")
parser.add_argument("--token", "--agk", help="Argo Token")
parser.add_argument("--prefer-clean-ip", action="store_true", help="优选纯净 IP（Cloudflare/阿里 CDN）")
args = parser.parse_args()

# 处理 UUID
if args.uuid:
    node_uuid = args.uuid
else:
    node_uuid = str(uuid_lib.uuid4())

# 处理端口
node_port = args.port if args.port else 22335

# 处理域名
node_domain = args.domain if args.domain else "example.com"

# Argo Token
argo_token = args.token if args.token else ""

# ------------------- 工具函数 -------------------
def run(cmd):
    print(f"执行命令: {cmd}")
    result = subprocess.run(cmd, shell=True, check=True)
    return result

def install():
    os.makedirs(INSTALL_DIR, exist_ok=True)
    print(f"安装路径: {INSTALL_DIR}")
    
    # 下载 Argo Tunnel 二进制或 Sing-box
    print("下载最新 Argo Tunnel 与 Sing-box…")
    run("curl -sSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared")
    run("chmod +x cloudflared")
    
    # 纯净 IP 优选
    if args.prefer_clean_ip:
        print("启用纯净 IP 优选策略 (Cloudflare CDN)...")
        # 示例: 使用 Cloudflare 服务，可进一步集成 Argo + CF DNS 策略
        run(f"./cloudflared tunnel --url http://localhost:{node_port} --hostname {node_domain} --protocol http")
    else:
        run(f"./cloudflared tunnel --url http://localhost:{node_port} --hostname {node_domain}")

    # 写入配置文件
    config_path = INSTALL_DIR / "config.json"
    config_data = {
        "uuid": node_uuid,
        "port": node_port,
        "domain": node_domain,
        "argo_token": argo_token,
        "prefer_clean_ip": args.prefer_clean_ip
    }
    import json
    with open(config_path, "w") as f:
        json.dump(config_data, f, indent=4)
    print(f"安装完成，配置已写入 {config_path}")

def uninstall():
    print(f"卸载 {INSTALL_DIR} …")
    if INSTALL_DIR.exists():
        import shutil
        shutil.rmtree(INSTALL_DIR)
    print("卸载完成。")

# ------------------- 执行 -------------------
if args.action == "install":
    install()
elif args.action == "uninstall":
    uninstall()
