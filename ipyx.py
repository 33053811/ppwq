#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import subprocess
import sys
import random
import socket
import requests

# ----------------------------
# 参数解析
# ----------------------------
parser = argparse.ArgumentParser(description="ArgoSB 自动部署脚本（纯净IP优先）")
parser.add_argument("--uuid", help="节点UUID")
parser.add_argument("--vmpt", type=int, help="旧端口参数")
parser.add_argument("--agn", help="旧域名参数")
parser.add_argument("--agk", help="Argo Token")
parser.add_argument("--port", type=int, help="新端口参数")
parser.add_argument("--domain", help="新域名参数")
parser.add_argument("action", choices=["install", "uninstall"], help="操作类型")

args = parser.parse_args()

# ----------------------------
# 参数映射：优先使用新参数
# ----------------------------
NODE_PORT = args.port if args.port else args.vmpt if args.vmpt else 22335
NODE_DOMAIN = args.domain if args.domain else args.agn if args.agn else "example.com"
NODE_UUID = args.uuid if args.uuid else None
ARGO_TOKEN = args.agk if args.agk else None

# ----------------------------
# 纯净 IP 检测函数
# ----------------------------
def is_clean_ip(ip):
    """
    判断 IP 是否纯净
    可用简单的公共 IP 检测服务或黑名单检测
    """
    try:
        # 示例：检测 IP 是否在 Cloudflare CDN 外部（简单判断）
        resp = requests.get(f"https://ipinfo.io/{ip}/json", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            # 简单规则：如果 org 包含 Cloudflare 或 Hosting Provider，则可能非纯净
            org = data.get("org", "").lower()
            if "cloudflare" in org or "digitalocean" in org or "vultr" in org:
                return False
            return True
    except Exception:
        return False
    return False

def get_public_ip():
    """获取本机公网 IP"""
    try:
        resp = requests.get("https://api.ipify.org", timeout=3)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        return None
    return None

# ----------------------------
# 安装 / 卸载逻辑
# ----------------------------
def install():
    print(f"开始安装节点：{NODE_DOMAIN}:{NODE_PORT}")

    # 检测纯净 IP
    ip = get_public_ip()
    if ip:
        if is_clean_ip(ip):
            print(f"[√] 当前公网 IP {ip} 为纯净 IP")
        else:
            print(f"[!] 当前公网 IP {ip} 可能不纯净，建议更换节点")
    else:
        print("[!] 无法获取公网 IP")

    # 安装逻辑示例
    print(f"使用 UUID={NODE_UUID} Token={ARGO_TOKEN}")
    print("执行安装流程...")
    # 这里可以放你的实际安装命令，例如 docker、sing-box、xray 等

def uninstall():
    print("执行卸载流程...")
    # 实际卸载命令，例如停止服务、删除文件
    # os.system("systemctl stop argo.service")
    # os.system("rm -rf /etc/argo")
    print("卸载完成")

# ----------------------------
# 主流程
# ----------------------------
if args.action == "install":
    install()
elif args.action == "uninstall":
    uninstall()
