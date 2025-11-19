# app.py
import streamlit as st
import os
import sys
import platform
import tempfile
import shutil
import subprocess
import os
import json
import threading
import time
import json
import base64
import requests
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="Proxy Auto Deploy (Streamlit)", layout="wide")

# ----------------------
# Helper utilities
# ----------------------
def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

def safe_mkdir(p):
    try:
        os.makedirs(p, exist_ok=True)
    except Exception as e:
        st.error(f"mkdir error: {e}")

def write_text_file(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def read_text_file(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def download_file(url, dest_path, timeout=30):
    try:
        with requests.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return True, None
    except Exception as e:
        return False, str(e)

def make_executable(path):
    try:
        if platform.system() != "Windows":
            os.chmod(path, 0o775)
        return True, None
    except Exception as e:
        return False, str(e)

# ----------------------
# Persistent workspace
# ----------------------
WORK_DIR = st.sidebar.text_input("工作目录 (FILE_PATH)", value=os.environ.get("FILE_PATH","./tmp"))
safe_mkdir(WORK_DIR)
WORK_DIR = os.path.abspath(WORK_DIR)

# File paths (simulate original variable names)
SUB_PATH = os.path.join(WORK_DIR, "sub.txt")
LIST_PATH = os.path.join(WORK_DIR, "list.txt")
BOOT_LOG = os.path.join(WORK_DIR, "boot.log")
CONFIG_JSON = os.path.join(WORK_DIR, "config.json")
TUNNEL_YML = os.path.join(WORK_DIR, "tunnel.yml")
TUNNEL_JSON = os.path.join(WORK_DIR, "tunnel.json")

st.sidebar.markdown("## 环境变量（可覆盖）")
UPLOAD_URL = st.sidebar.text_input("UPLOAD_URL", value=os.environ.get("UPLOAD_URL",""))
PROJECT_URL = st.sidebar.text_input("PROJECT_URL", value=os.environ.get("PROJECT_URL",""))
AUTO_ACCESS = st.sidebar.checkbox("AUTO_ACCESS", value=(os.environ.get("AUTO_ACCESS","false").lower() in ("1","true","yes")))
UUID = st.sidebar.text_input("UUID", value=os.environ.get("UUID","c9502d2f-983e-437e-bf61-223200aa2dee"))
NEZHA_SERVER = st.sidebar.text_input("NEZHA_SERVER", value=os.environ.get("NEZHA_SERVER",""))
NEZHA_PORT = st.sidebar.text_input("NEZHA_PORT", value=os.environ.get("NEZHA_PORT",""))
NEZHA_KEY = st.sidebar.text_input("NEZHA_KEY", value=os.environ.get("NEZHA_KEY",""))
ARGO_DOMAIN = st.sidebar.text_input("ARGO_DOMAIN", value=os.environ.get("ARGO_DOMAIN","nodejs-argo7262.ppwq.us.kg"))
ARGO_AUTH = st.sidebar.text_area("ARGO_AUTH (token/json)", value=os.environ.get("ARGO_AUTH","eyJhIjoiMTcxNjEzYjZkNTdjZTY2YzdhMWQ2OGQzMGEyMDBlYTYiLCJ0IjoiYzU5MGQ2ZDMtYzNhNy00OThjLTgwYjYtOTIyMTJmNTg1MDYwIiwicyI6Ik5EUXhNV1JsT1dNdFpERmtNUzAwWmpabUxXSTVZelV0WWpFNE1qVXdOMll3T1RWaCJ9"), height=80)
ARGO_PORT = st.sidebar.number_input("ARGO_PORT", min_value=1, max_value=65535, value=int(os.environ.get("ARGO_PORT",8001)))
CFIP = st.sidebar.text_input("CFIP", value=os.environ.get("CFIP","cdns.doon.eu.org"))
CFPORT = st.sidebar.number_input("CFPORT", min_value=1, max_value=65535, value=int(os.environ.get("CFPORT",443)))
NAME = st.sidebar.text_input("NAME", value=os.environ.get("NAME","nodejs-argo7262"))

# Download URLs (for demo/test you can set placeholders)
st.sidebar.markdown("## 二进制下载 URL（请替换为可信来源）")
WEB_URL = st.sidebar.text_input("web (xray) URL", value=os.environ.get("WEB_URL","https://example.com/web-binary"))
BOT_URL = st.sidebar.text_input("bot (cloudflared) URL", value=os.environ.get("BOT_URL","https://example.com/cloudflared"))
NPM_URL = st.sidebar.text_input("ne-zha agent (npm) URL", value=os.environ.get("NPM_URL","https://example.com/nezha-agent"))
PHP_URL = st.sidebar.text_input("ne-zha v1 (php) URL", value=os.environ.get("PHP_URL","https://example.com/nezha-v1"))

# runtime file names (randomized like original)
def randname(prefix="a"):
    import random, string
    return prefix + ''.join(random.choice(string.ascii_lowercase) for _ in range(6))

npmName = randname("npm")
webName = randname("web")
botName = randname("bot")
phpName = randname("php")

npmPath = os.path.join(WORK_DIR, npmName)
webPath = os.path.join(WORK_DIR, webName)
botPath = os.path.join(WORK_DIR, botName)
phpPath = os.path.join(WORK_DIR, phpName)

# process management
_processes = {}
_log_buffers = {}

def start_process(key, cmd, cwd=None, env=None):
    """Start process and stream logs into _log_buffers[key]"""
    if key in _processes and _processes[key].poll() is None:
        return False, f"{key} already running"

    try:
        # Use shell=False for safety: cmd should be list
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd, env=env, bufsize=1, text=True)
        _processes[key] = p
        _log_buffers[key] = []
    except Exception as e:
        return False, str(e)

    # start a thread to read stdout
    def reader(proc, key):
        try:
            for line in proc.stdout:
                _log_buffers[key].append(f"{now()} {line.rstrip()}")
        except Exception as e:
            _log_buffers[key].append(f"{now()} reader error: {e}")
    t = threading.Thread(target=reader, args=(p, key), daemon=True)
    t.start()
    return True, None

def stop_process(key):
    p = _processes.get(key)
    if not p:
        return False, f"{key} not found"
    try:
        p.terminate()
        time.sleep(1)
        if p.poll() is None:
            p.kill()
        return True, None
    except Exception as e:
        return False, str(e)

# ----------------------
# UI: main controls
# ----------------------
st.title("Proxy Auto Deploy — Streamlit 版")
st.caption("注意：运行未知二进制有风险。Streamlit 平台可能限制长期后台进程或开放端口。")

col1, col2 = st.columns([2,3])

with col1:
    st.subheader("操作面板")
    if st.button("生成 xray config.json"):
        # generate config.json similar to original
        config = {
            "log": {"access": "/dev/null", "error": "/dev/null", "loglevel": "none"},
            "inbounds": [
                {"port": ARGO_PORT, "protocol": "vless", "settings": {"clients": [{"id": UUID, "flow": "xtls-rprx-vision"}], "decryption": "none", "fallbacks": [{"dest": 3001}, {"path": "/vless-argo", "dest": 3002}, {"path": "/vmess-argo", "dest": 3003}, {"path": "/trojan-argo", "dest": 3004}]}, "streamSettings": {"network": "tcp"}},
                {"port": 3001, "listen": "127.0.0.1", "protocol": "vless", "settings": {"clients": [{"id": UUID}], "decryption": "none"}, "streamSettings": {"network": "tcp", "security": "none"}},
                {"port": 3002, "listen": "127.0.0.1", "protocol": "vless", "settings": {"clients": [{"id": UUID, "level": 0}], "decryption": "none"}, "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/vless-argo"}}},
                {"port": 3003, "listen": "127.0.0.1", "protocol": "vmess", "settings": {"clients": [{"id": UUID, "alterId": 0}]}, "streamSettings": {"network": "ws", "wsSettings": {"path": "/vmess-argo"}}},
                {"port": 3004, "listen": "127.0.0.1", "protocol": "trojan", "settings": {"clients": [{"password": UUID}]}, "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/trojan-argo"}}}
            ],
            "dns": {"servers": ["https+local://8.8.8.8/dns-query"]},
            "outbounds": [{"protocol": "freedom", "tag": "direct"}, {"protocol": "blackhole", "tag": "block"}]
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
        write_text_file(CONFIG_JSON, json.dumps(config, indent=2))
        st.success(f"config.json 已写入：{CONFIG_JSON}")
        st.code(json.dumps(config, indent=2), language="json")

    st.markdown("---")
    st.subheader("下载与启动二进制")
    st.write("提示：在 share.streamlit.io 环境中下载并在后台运行二进制可能被限制。请确保 URL 来自可信来源。")
    download_mode = st.radio("下载模式", ["模拟（只创建占位文件）", "真实下载（从 URL 获取）"], index=0)

    col_btns = st.columns(3)
    if col_btns[0].button("下载 web (xray)"):
        if download_mode == "模拟（只创建占位文件）":
            write_text_file(webPath, "# placeholder web binary\n")
            st.success(f"占位文件创建：{webPath}")
        else:
            ok, err = download_file(WEB_URL, webPath)
            if ok:
                make_executable(webPath)
                st.success(f"下载成功：{webPath}")
            else:
                st.error(f"下载失败：{err}")

    if col_btns[1].button("下载 bot (cloudflared)"):
        if download_mode == "模拟（只创建占位文件）":
            write_text_file(botPath, "# placeholder bot binary\n")
            st.success(f"占位文件创建：{botPath}")
        else:
            ok, err = download_file(BOT_URL, botPath)
            if ok:
                make_executable(botPath)
                st.success(f"下载成功：{botPath}")
            else:
                st.error(f"下载失败：{err}")

    if col_btns[2].button("下载 ne-zha agent"):
        if download_mode == "模拟（只创建占位文件）":
            write_text_file(npmPath, "# placeholder npm binary\n")
            write_text_file(phpPath, "# placeholder php binary\n")
            st.success("占位哪吒文件已创建")
        else:
            # choose based on NEZHA_PORT presence to pick the right URL to download
            if NEZHA_PORT:
                ok, err = download_file(NPM_URL, npmPath)
                if ok:
                    make_executable(npmPath)
                    st.success(f"下载成功（v0 agent）：{npmPath}")
                else:
                    st.error(f"下载失败：{err}")
            else:
                ok, err = download_file(PHP_URL, phpPath)
                if ok:
                    make_executable(phpPath)
                    st.success(f"下载成功（v1 agent）：{phpPath}")
                else:
                    st.error(f"下载失败：{err}")
    }

    st.markdown("---")
    st.subheader("启动 / 停止 服务")
    start_cols = st.columns(3)
    if start_cols[0].button("启动 web (xray)"):
        if os.path.exists(CONFIG_JSON) and os.path.exists(webPath):
            cmd = [webPath, "-c", CONFIG_JSON]
            ok, err = start_process("web", cmd)
            if ok:
                st.success("web 已启动")
            else:
                st.error(f"启动 web 失败：{err}")
        else:
            st.warning("请先生成 config.json 并确保 web 二进制存在")

    if start_cols[1].button("启动 cloudflared"):
        if os.path.exists(botPath):
            # choose args based on ARGO_AUTH (very simple heuristic)
            if ARGO_AUTH and "TunnelSecret" in ARGO_AUTH:
                write_text_file(TUNNEL_JSON, ARGO_AUTH)
                # prepare tunnel yml
                yaml = f"""
tunnel: {json.loads(ARGO_AUTH).get('TunnelID','')}
credentials-file: {TUNNEL_JSON}
protocol: http2
ingress:
  - hostname: {ARGO_DOMAIN}
    service: http://localhost:{ARGO_PORT}
  - service: http_status:404
"""
                write_text_file(TUNNEL_YML, yaml)
                cmd = [botPath, "tunnel", "--config", TUNNEL_YML, "run"]
            elif ARGO_AUTH and len(ARGO_AUTH.strip()) > 20:
                cmd = [botPath, "tunnel", "run", "--token", ARGO_AUTH]
            else:
                cmd = [botPath, "tunnel", "--url", f"http://localhost:{ARGO_PORT}", "run"]
            ok, err = start_process("bot", cmd)
            if ok:
                st.success("cloudflared 已启动（注意：平台可能限制进程）")
            else:
                st.error(f"启动 cloudflared 失败：{err}")
        else:
            st.warning("请先下载 bot 二进制")
    os.makedirs("anytls", exist_ok=True)
    with open("anytls/config.json", "w") as f:
        json.dump(config, f, indent=2)

    if start_cols[2].button("启动 ne-zha"):
        if NEZHA_KEY and NEZHA_SERVER:
            if NEZHA_PORT:
                cmd = [npmPath, "-s", f"{NEZHA_SERVER}:{NEZHA_PORT}", "-p", NEZHA_KEY, "--disable-auto-update"]
            else:
                # v1 with config yaml
                cfg = f"client_secret: {NEZHA_KEY}\nserver: {NEZHA_SERVER}\nuuid: {UUID}\n"
                cfgpath = os.path.join(WORK_DIR, "config_nezha.yaml")
                write_text_file(cfgpath, cfg)
                cmd = [phpPath, "-c", cfgpath]
            ok, err = start_process("nezha", cmd)
            if ok:
                st.success("nezha 已启动")
            else:
                st.error(f"启动 nezha 失败：{err}")
        else:
            st.warning("请先填写 NEZHA_SERVER 与 NEZHA_KEY")

    stop_cols = st.columns(3)
    if stop_cols[0].button("停止 web"):
        ok, err = stop_process("web")
        if ok:
            st.success("web 已停止")
        else:
            st.error(f"停止 web 失败：{err}")

    if stop_cols[1].button("停止 bot"):
        ok, err = stop_process("bot")
        if ok:
            st.success("bot 已停止")
        else:
            st.error(f"停止 bot 失败：{err}")

    if stop_cols[2].button("停止 nezha"):
        ok, err = stop_process("nezha")
        if ok:
            st.success("nezha 已停止")
        else:
            st.error(f"停止 nezha 失败：{err}")

    st.markdown("---")
    if st.button("删除工作目录中的临时文件（手动）"):
        try:
            for p in [webPath, botPath, npmPath, phpPath, CONFIG_JSON, SUB_PATH, LIST_PATH, BOOT_LOG, TUNNEL_JSON, TUNNEL_YML]:
                if os.path.exists(p):
                    os.remove(p)
            st.success("已删除临时文件")
        except Exception as e:
            st.error(f"删除错误：{e}")

with col2:
    st.subheader("订阅 / 上传 / 日志")
    # generateLinks equivalent
    if st.button("生成订阅并展示（generateLinks）"):
        # determine argoDomain
        argo_domain = None
        if ARGO_DOMAIN:
            argo_domain = ARGO_DOMAIN
        else:
            # try parse boot log
            log = read_text_file(BOOT_LOG)
            import re
            m = re.search(r"https?://([^\\s]*trycloudflare\\.com)", log)
            if m:
                argo_domain = m.group(1)
        if not argo_domain:
            st.warning("未能找到 Argo 的域名（请先启动 cloudflared 并检查 boot.log，或填写 ARGO_DOMAIN）")
        else:
            # get ISP meta using Cloudflare speed meta endpoint (use requests)
            try:
                r = requests.get("https://speed.cloudflare.com/meta", timeout=5)
                meta = r.json()
                isp = f"{meta.get('region','')}-{meta.get('isp','')}".replace(" ","_")
            except Exception:
                isp = "unknown_isp"
            nodeName = f"{NAME}-{isp}" if NAME else isp
            vmess_obj = {"v":"2","ps":nodeName,"add":CFIP,"port":str(CFPORT),"id":UUID,"aid":"0","scy":"none","net":"ws","type":"none","host":argo_domain,"path":"/vmess-argo?ed=2560","tls":"tls","sni":argo_domain,"alpn":"","fp":"firefox"}
            vmess_b64 = base64.b64encode(json.dumps(vmess_obj).encode()).decode()
            subtxt = f"""
vless://{UUID}@{CFIP}:{CFPORT}?encryption=none&security=tls&sni={argo_domain}&fp=firefox&type=ws&host={argo_domain}&path=%2Fvless-argo%3Fed%3D2560#{nodeName}
    # 下载 AnyTLS 二进制
    if not os.path.exists("anytls/anytls"):
        st.write("⬇️ 下载 AnyTLS...")
        subprocess.run("curl -L -o anytls/anytls https://github.com/anytls/anytls/releases/latest/download/anytls-linux-amd64", shell=True)
        subprocess.run("chmod +x anytls/anytls", shell=True)

vmess://{vmess_b64}
    # 写入并启动 Cloudflare Tunnel
    with open("anytls/tunnel.json", "w") as f:
        json.dump({"tunnel": "auto", "credentials-file": "/tmp/cred.json"}, f)

trojan://{UUID}@{CFIP}:{CFPORT}?security=tls&sni={argo_domain}&fp=firefox&type=ws&host={argo_domain}&path=%2Ftrojan-argo%3Fed%3D2560#{nodeName}
"""
            write_text_file(SUB_PATH, base64.b64encode(subtxt.encode()).decode())
            st.success("订阅已生成并以 base64 写入 sub.txt")
            st.code(subtxt, language="text")
            # register "upload" attempt
            if UPLOAD_URL and PROJECT_URL:
                try:
                    sub_url = f"{PROJECT_URL}/sub"
                    response = requests.post(f"{UPLOAD_URL}/api/add-subscriptions", json={"subscription":[sub_url]}, timeout=10)
                    st.write("上传订阅结果：", response.status_code, response.text[:200])
                except Exception as e:
                    st.error(f"上传订阅失败：{e}")
            elif UPLOAD_URL:
                # upload nodes from list.txt if exists
                if os.path.exists(LIST_PATH):
                    content = read_text_file(LIST_PATH)
                    nodes = [line.strip() for line in content.splitlines() if line.strip() and any(proto in line for proto in ("vless://","vmess://","trojan://","hysteria2://","tuic://"))]
                    if nodes:
                        try:
                            resp = requests.post(f"{UPLOAD_URL}/api/add-nodes", json={"nodes": nodes}, timeout=10)
                            st.write("上传节点结果：", resp.status_code)
                        except Exception as e:
                            st.error(f"上传节点失败：{e}")
                    else:
                        st.info("list.txt 中未找到可上传的节点")
            else:
                st.info("未配置 UPLOAD_URL，跳过上传")
    st.write("🚀 启动 AnyTLS 进程中...")

    st.markdown("----")
    st.write("日志面板（来自子进程 stdout/stderr）")
    select_proc = st.selectbox("选择进程查看日志", options=["web","bot","nezha"])
    # display last N lines
    lines_to_show = st.slider("显示最近多少行日志", min_value=10, max_value=1000, value=200, step=10)
    buf = _log_buffers.get(select_proc, [])
    if buf:
        show = "\n".join(buf[-lines_to_show:])
        st.code(show, language="text")
    else:
        st.info("暂无日志（尚未启动对应进程或尚无输出）")
    def run_anytls():
        subprocess.run("./anytls/anytls server -c anytls/config.json", shell=True)

    st.markdown("----")
    st.subheader("保活 / 自动访问（AddVisitTask）")
    if st.button("添加自动访问任务（向 oooo.serv00.net）"):
        if AUTO_ACCESS and PROJECT_URL:
            try:
                resp = requests.post("https://oooo.serv00.net/add-url", json={"url": PROJECT_URL}, timeout=8)
                st.write("请求返回：", resp.status_code, resp.text[:400])
            except Exception as e:
                st.error(f"请求失败：{e}")
    def run_tunnel():
        if tunnel_token.strip():
            subprocess.run(f"cloudflared tunnel --no-autoupdate run --token {tunnel_token}", shell=True)
else:
            st.warning("请在侧边栏启用 AUTO_ACCESS 并填写 PROJECT_URL")
            subprocess.run("cloudflared tunnel --url http://localhost:8443", shell=True)

st.markdown("---")
st.caption("说明：本示例尽量保留了原脚本的核心流程（生成 config、下载二进制、启动进程、生成订阅、上传订阅），但在 Streamlit 平台上请谨慎执行真实二进制。")
    # 启动线程
    threading.Thread(target=run_anytls, daemon=True).start()
    threading.Thread(target=run_tunnel, daemon=True).start()

st.info("完成：如果需要，我可以把此脚本按需要进一步精简或增加更严格的安全校验（例如：下载后校验 sha256、签名验证、日志持久化、子进程健康检查）。")
    time.sleep(3)
    st.success("✅ AnyTLS 已启动，请查看 Cloudflare Tunnel 控制台获取外部访问地址。")
    st.write(f"本地端口：{port}")
    st.code(f"uuid: {uuid}", language="bash")
