#!/usr/bin/env python3
import os
import uuid
import json
import subprocess
import base64
import random
import string
from pathlib import Path

# ==== 配置变量 ====
SBOX_VER = "1.8.6"
PORT = 22335
DOMAIN = "jd.ppwq.us.kg"
SNI = "www.linux.org"
CFTOKEN = "eyJhIjoiMTcxNjEzYjZkNTdjZTY2YzdhMWQ2OGQzMGEyMDBlYTYiLCJ0IjoiMmE1ZTA0ZDQtZjMwMy00ZjAzLTgwM2ItNjc2NmRkYTc2MTU4IiwicyI6Ik4ySTROV00yTkRjdE5EVTBZaTAwWVdaakxXSTRPVEV0TkdGbE16WmhZVE5qT0dWaSJ9"

BASE_DIR = Path("/opt/singbox")
BIN_DIR = BASE_DIR / f"sing-box-{SBOX_VER}"
CONFIG_PATH = BIN_DIR / "config.json"
SUB_PATH = BIN_DIR / "sub.json"

# ==== 工具函数 ====
def run(cmd, capture=False):
    print(f"[RUN] {cmd}")
    if capture:
        return subprocess.check_output(cmd, shell=True).decode().strip()
    else:
        subprocess.run(cmd, shell=True, check=True)

def rand_short_id(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def ensure_dirs():
    os.makedirs(BASE_DIR, exist_ok=True)
    os.makedirs(BIN_DIR, exist_ok=True)

# ==== 下载与准备 ====
def download_binaries():
    os.chdir(BASE_DIR)
    if not Path(f"sing-box-{SBOX_VER}-linux-amd64.tar.gz").exists():
        run(f"curl -LO https://ghproxy.com/https://github.com/SagerNet/sing-box/releases/download/v{SBOX_VER}/sing-box-{SBOX_VER}-linux-amd64.tar.gz")
    run(f"tar -xvf sing-box-{SBOX_VER}-linux-amd64.tar.gz")

    # 下载 cloudflared
    if not Path("/usr/local/bin/cloudflared").exists():
        run("wget -O /usr/local/bin/cloudflared https://ghproxy.com/https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64")
        run("chmod +x /usr/local/bin/cloudflared")

# ==== 生成配置 ====
def generate_keys_and_config():
    singbox = BIN_DIR / "sing-box"
    uuid_str = str(uuid.uuid4())
    short_id = rand_short_id()
    result = run(f"{singbox} generate reality-keypair", capture=True)
    lines = result.splitlines()
    private_key = lines[0].split(":")[1].strip()
    public_key = lines[1].split(":")[1].strip()

    config = {
        "log": {"level": "info"},
        "inbounds": [{
            "type": "vless",
            "listen": "0.0.0.0",
            "listen_port": PORT,
            "users": [{"uuid": uuid_str, "flow": "xtls-rprx-vision"}],
            "tls": {
                "enabled": True,
                "reality": {
                    "enabled": True,
                    "handshake": {"server": SNI, "server_port": 443},
                    "private_key": private_key,
                    "short_id": [short_id]
                }
            }
        }]
    }
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

    sub = {
        "proxies": [{
            "name": "JD-VLESS-Reality",
            "type": "vless",
            "server": DOMAIN,
            "port": 443,
            "uuid": uuid_str,
            "tls": True,
            "flow": "xtls-rprx-vision",
            "reality-opts": {
                "public-key": public_key,
                "short-id": short_id,
                "server-name": SNI
            }
        }]
    }
    with open(SUB_PATH, "w") as f:
        json.dump(sub, f, indent=2)

    return uuid_str, public_key, private_key, short_id

# ==== CF 配置 ====
def setup_cloudflare():
    cred_file = Path("/root/.cloudflared/credentials.json")
    conf_file = Path("/root/.cloudflared/config.yml")
    cred_file.parent.mkdir(parents=True, exist_ok=True)

    # 写入 token 凭证
    decoded = base64.b64decode(CFTOKEN).decode()
    with open(cred_file, "w") as f:
        f.write(decoded)

    conf = f"""tunnel: jd
credentials-file: {cred_file}

ingress:
  - hostname: {DOMAIN}
    service: http://localhost:{PORT}
  - service: http_status:404
"""
    with open(conf_file, "w") as f:
        f.write(conf)

# ==== 主执行入口 ====
def main():
    ensure_dirs()
    download_binaries()
    uuid_str, pub, priv, sid = generate_keys_and_config()
    setup_cloudflare()

    print("\n✅ 部署完成！以下是关键信息：\n")
    print(f"🔗 域名：{DOMAIN}")
    print(f"🧬 UUID：{uuid_str}")
    print(f"🔐 公钥：{pub}")
    print(f"🔒 私钥：{priv}")
    print(f"🧿 short_id：{sid}")
    print("\n🚀 启动 Sing-box：")
    print(f"cd {BIN_DIR} && ./sing-box run -c config.json")
    print("\n🌐 启动 Cloudflare Tunnel：")
    print("cloudflared tunnel --config /root/.cloudflared/config.yml run")
    print("\n📥 Clash/Karing 订阅：")
    print(f"文件位置：{SUB_PATH}（内容为 JSON，可本地或挂载 Web 访问）")

if __name__ == "__main__":
    main()
