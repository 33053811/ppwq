import streamlit as st
import subprocess
import os
import json
import threading
import time

st.title("AnyTLS Node via Streamlit + Cloudflare Tunnel")

# 配置参数输入
uuid = st.text_input("UUID", "auto")
port = st.text_input("Local Port", "8443")
tunnel_token = st.text_area("Cloudflare Tunnel Token", placeholder="输入你的 Cloudflare Tunnel token")

start_button = st.button("启动 AnyTLS 节点")

if start_button:
    st.write("⚙️ 正在配置 AnyTLS...")

    # 自动生成 UUID
    if uuid == "auto":
        uuid = subprocess.getoutput("uuidgen")
        st.write("生成的 UUID:", uuid)

    # 写入 AnyTLS 配置文件
    config = {
        "listen": f"0.0.0.0:{port}",
        "users": [
            {"uuid": uuid}
        ],
        "tls": {
            "enabled": False
        },
        "transport": {
            "type": "ws",
            "path": "/any"
        }
    }

    os.makedirs("anytls", exist_ok=True)
    with open("anytls/config.json", "w") as f:
        json.dump(config, f, indent=2)

    # 下载 AnyTLS 二进制
    if not os.path.exists("anytls/anytls"):
        st.write("⬇️ 下载 AnyTLS...")
        subprocess.run("curl -L -o anytls/anytls https://github.com/anytls/anytls/releases/latest/download/anytls-linux-amd64", shell=True)
        subprocess.run("chmod +x anytls/anytls", shell=True)

    # 写入并启动 Cloudflare Tunnel
    with open("anytls/tunnel.json", "w") as f:
        json.dump({"tunnel": "auto", "credentials-file": "/tmp/cred.json"}, f)

    st.write("🚀 启动 AnyTLS 进程中...")

    def run_anytls():
        subprocess.run("./anytls/anytls server -c anytls/config.json", shell=True)

    def run_tunnel():
        if tunnel_token.strip():
            subprocess.run(f"cloudflared tunnel --no-autoupdate run --token {tunnel_token}", shell=True)
        else:
            subprocess.run("cloudflared tunnel --url http://localhost:8443", shell=True)

    # 启动线程
    threading.Thread(target=run_anytls, daemon=True).start()
    threading.Thread(target=run_tunnel, daemon=True).start()

    time.sleep(3)
    st.success("✅ AnyTLS 已启动，请查看 Cloudflare Tunnel 控制台获取外部访问地址。")
    st.write(f"本地端口：{port}")
    st.code(f"uuid: {uuid}", language="bash")
