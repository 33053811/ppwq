import streamlit as st
import subprocess
import tempfile
import os
import time
import re
import json
from pathlib import Path
import uuid  # 添加了uuid模块的导入

# 设置页面配置
st.set_page_config(
    page_title="ArgoSB 自动安装工具",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 应用标题
st.title("✨ ArgoSB 自动安装工具")
st.markdown("基于Cloudflare Argo Tunnel和sing-box的一键代理部署工具")

# 侧边栏说明
with st.sidebar:
    st.header("使用说明")
    st.markdown("""
    1. 填写下方必要参数
    2. 点击"开始安装"按钮
    3. 等待安装完成(约1-2分钟)
    4. 获取并复制生成的节点链接
    
    **注意事项**:
    - 安装需要网络连接
    - 建议使用自定义UUID和域名
    - 安装过程中请勿刷新页面
    """)

# 输入表单
with st.form(key='install_form'):
    col1, col2 = st.columns(2)
    
    with col1:
        uuid_str = st.text_input("自定义UUID", value=str(os.environ.get("uuid", "")))
        port_vm_ws = st.number_input("Vmess端口", min_value=10000, max_value=65535, value=int(os.environ.get("vmpt", 49999)))
        custom_domain = st.text_input("自定义域名 (例如: example.com)", value=os.environ.get("agn", ""))
    
    with col2:
        argo_token = st.text_input("Argo Tunnel Token", value=os.environ.get("agk", ""), type="password")
        st.markdown("""
        **关于Argo Token**:
        - 留空将使用临时隧道(域名会变化)
        - 获取方法: 登录Cloudflare Zero Trust创建隧道
        """)
    
    submit_button = st.form_submit_button(label='🚀 开始安装')

# 安装目录和配置文件路径
INSTALL_DIR = Path.home() / ".agsb"
CONFIG_FILE = INSTALL_DIR / "config.json"
LIST_FILE = INSTALL_DIR / "list.txt"
ALL_NODES_FILE = INSTALL_DIR / "allnodes.txt"
LOG_FILE = INSTALL_DIR / "argo.log"
DEBUG_LOG = INSTALL_DIR / "python_debug.log"

# 执行安装过程
if submit_button:
    # 检查必要参数
    if not uuid_str:
        uuid_str = str(os.environ.get("uuid", str(uuid.uuid4())))  # 修正了uuid生成方式
    
    if not port_vm_ws:
        port_vm_ws = int(os.environ.get("vmpt", random.randint(10000, 65535)))
    
    # 如果使用Argo Token但未提供域名，提示错误
    if argo_token and not custom_domain:
        st.error("使用Argo Tunnel Token时必须提供自定义域名!")
        st.stop()
    
    # 显示安装进度
    with st.spinner("正在安装... 这可能需要1-2分钟，请耐心等待"):
        # 创建临时脚本文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # 写入修改后的安装脚本内容(移除交互式输入)
            script_content = """
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

# 全局变量
INSTALL_DIR = Path.home() / ".agsb"
CONFIG_FILE = INSTALL_DIR / "config.json"
SB_PID_FILE = INSTALL_DIR / "sbpid.log"
ARGO_PID_FILE = INSTALL_DIR / "sbargopid.log"
LIST_FILE = INSTALL_DIR / "list.txt"
LOG_FILE = INSTALL_DIR / "argo.log"
DEBUG_LOG = INSTALL_DIR / "python_debug.log"
CUSTOM_DOMAIN_FILE = INSTALL_DIR / "custom_domain.txt"

# 网络请求函数
def http_get(url, timeout=10):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        print(f"HTTP请求失败: {url}, 错误: {e}")
        write_debug_log(f"HTTP GET Error: {url}, {e}")
        return None

def download_file(url, target_path, mode='wb'):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx) as response, open(target_path, mode) as out_file:
            shutil.copyfileobj(response, out_file)
        return True
    except Exception as e:
        print(f"下载文件失败: {url}, 错误: {e}")
        write_debug_log(f"Download Error: {url}, {e}")
        return False

# 写入日志函数
def write_debug_log(message):
    try:
        if not INSTALL_DIR.exists():
            INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        print(f"写入日志失败: {e}")

# 下载二进制文件
def download_binary(name, download_url, target_path):
    print(f"正在下载 {name}...")
    success = download_file(download_url, target_path)
    if success:
        print(f"{name} 下载成功!")
        os.chmod(target_path, 0o755)
        return True
    else:
        print(f"{name} 下载失败!")
        return False

# 生成VMess链接
def generate_vmess_link(config):
    vmess_obj = {{
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
    }}
    vmess_str = json.dumps(vmess_obj, sort_keys=True)
    vmess_b64 = base64.b64encode(vmess_str.encode('utf-8')).decode('utf-8').rstrip("=")
    return f"vmess://{{vmess_b64}}"

# 生成链接
def generate_links(domain, port_vm_ws, uuid_str):
    write_debug_log(f"生成链接: domain={{domain}}, port_vm_ws={{port_vm_ws}}, uuid_str={{uuid_str}}")

    ws_path = f"/{{uuid_str[:8]}}-vm"
    ws_path_full = f"{{ws_path}}?ed=2048"
    write_debug_log(f"WebSocket路径: {{ws_path_full}}")

    hostname = socket.gethostname()[:10]
    all_links = []
    link_names = []
    link_configs_for_json_output = []

    # Cloudflare优选IP和端口
    cf_ips_tls = {{
        "104.16.0.0": "443", "104.17.0.0": "8443", "104.18.0.0": "2053",
        "104.19.0.0": "2083", "104.20.0.0": "2087"
    }}
    cf_ips_http = {{
        "104.21.0.0": "80", "104.22.0.0": "8080", "104.24.0.0": "8880"
    }}

    # === TLS节点 ===
    for ip, port_cf in cf_ips_tls.items():
        ps_name = f"VMWS-TLS-{{hostname}}-{{ip.split('.')[2]}}-{{port_cf}}"
        config = {{
            "ps": ps_name, "add": ip, "port": port_cf, "id": uuid_str, "aid": "0",
            "net": "ws", "type": "none", "host": domain, "path": ws_path_full,
            "tls": "tls", "sni": domain
        }}
        all_links.append(generate_vmess_link(config))
        link_names.append(f"TLS-{{port_cf}}-{{ip}}")
        link_configs_for_json_output.append(config)

    # === 非TLS节点 ===
    for ip, port_cf in cf_ips_http.items():
        ps_name = f"VMWS-HTTP-{{hostname}}-{{ip.split('.')[2]}}-{{port_cf}}"
        config = {{
            "ps": ps_name, "add": ip, "port": port_cf, "id": uuid_str, "aid": "0",
            "net": "ws", "type": "none", "host": domain, "path": ws_path_full,
            "tls": ""
        }}
        all_links.append(generate_vmess_link(config))
        link_names.append(f"HTTP-{{port_cf}}-{{ip}}")
        link_configs_for_json_output.append(config)
    
    # === 直接使用域名和标准端口的节点 ===
    # TLS Direct
    direct_tls_config = {{
        "ps": f"VMWS-TLS-{{hostname}}-Direct-{{domain[:15]}}-443", 
        "add": domain, "port": "443", "id": uuid_str, "aid": "0",
        "net": "ws", "type": "none", "host": domain, "path": ws_path_full,
        "tls": "tls", "sni": domain
    }}
    all_links.append(generate_vmess_link(direct_tls_config))
    link_names.append(f"TLS-Direct-{{domain}}-443")
    link_configs_for_json_output.append(direct_tls_config)

    # HTTP Direct
    direct_http_config = {{
        "ps": f"VMWS-HTTP-{{hostname}}-Direct-{{domain[:15]}}-80",
        "add": domain, "port": "80", "id": uuid_str, "aid": "0",
        "net": "ws", "type": "none", "host": domain, "path": ws_path_full,
        "tls": ""
    }}
    all_links.append(generate_vmess_link(direct_http_config))
    link_names.append(f"HTTP-Direct-{{domain}}-80")
    link_configs_for_json_output.append(direct_http_config)

    # 保存所有链接到文件
    (INSTALL_DIR / "allnodes.txt").write_text("\n".join(all_links) + "\n")
    (INSTALL_DIR / "jh.txt").write_text("\n".join(all_links) + "\n") 

    # 保存域名到文件
    CUSTOM_DOMAIN_FILE.write_text(domain)

    return all_links, link_names

# 安装过程
def install(uuid_str, port_vm_ws, argo_token, custom_domain):
    if not INSTALL_DIR.exists():
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(INSTALL_DIR)
    write_debug_log("开始安装过程")

    print(f"使用 UUID: {{uuid_str}}")
    write_debug_log(f"UUID: {{uuid_str}}")

    print(f"使用 Vmess 本地端口: {{port_vm_ws}}")
    write_debug_log(f"Vmess Port: {{port_vm_ws}}")

    if argo_token:
        print(f"使用 Argo Tunnel Token: ******{{argo_token[-6:]}}")
        write_debug_log(f"Argo Token: Present (not logged for security)")
    else:
        print("未提供 Argo Tunnel Token，将使用临时隧道 (Quick Tunnel)。")
        write_debug_log("Argo Token: Not provided, using Quick Tunnel.")

    if custom_domain:
        print(f"使用自定义域名: {{custom_domain}}")
        write_debug_log(f"Custom Domain (agn): {{custom_domain}}")
    elif argo_token:
        print("\033[31m错误: 使用 Argo Tunnel Token 时必须提供自定义域名 (agn/--domain)。\033[0m")
        sys.exit(1)
    else:
        print("未提供自定义域名，将尝试在隧道启动后自动获取。")
        write_debug_log("Custom Domain (agn): Not provided, will attempt auto-detection.")

    # --- 下载依赖 ---
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = ""
    if system == "linux":
        if "x86_64" in machine or "amd64" in machine: arch = "amd64"
        elif "aarch64" in machine or "arm64" in machine: arch = "arm64"
        elif "armv7" in machine: arch = "arm"
        else: arch = "amd64"
    else:
        print(f"不支持的系统类型: {{system}}")
        sys.exit(1)
    write_debug_log(f"检测到系统: {{system}}, 架构: {{machine}}, 使用架构标识: {{arch}}")

    # sing-box
    singbox_path = INSTALL_DIR / "sing-box"
    if not singbox_path.exists():
        try:
            print("获取sing-box最新版本号...")
            version_info = http_get("https://api.github.com/repos/SagerNet/sing-box/releases/latest")
            sb_version = json.loads(version_info)["tag_name"].lstrip("v") if version_info else "1.9.0-beta.11"
            print(f"sing-box 最新版本: {{sb_version}}")
        except Exception as e:
            sb_version = "1.9.0-beta.11"
            print(f"获取最新版本失败，使用默认版本: {{sb_version}}，错误: {{e}}")
        
        sb_name = f"sing-box-{{sb_version}}-linux-{{arch}}"
        if arch == "arm": sb_name_actual = f"sing-box-{{sb_version}}-linux-armv7"
        else: sb_name_actual = sb_name

        sb_url = f"https://github.com/SagerNet/sing-box/releases/download/v{{sb_version}}/{{sb_name_actual}}.tar.gz"
        tar_path = INSTALL_DIR / "sing-box.tar.gz"
        
        if not download_file(sb_url, tar_path):
            print("sing-box 下载失败，尝试使用备用地址")
            sb_url_backup = f"https://github.91chi.fun/https://github.com/SagerNet/sing-box/releases/download/v{{sb_version}}/{{sb_name_actual}}.tar.gz"
            if not download_file(sb_url_backup, tar_path):
                print("sing-box 备用下载也失败，退出安装")
                sys.exit(1)
        try:
            print("正在解压sing-box...")
            import tarfile
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(path=INSTALL_DIR)
            
            extracted_folder_path = INSTALL_DIR / sb_name_actual 
            if not extracted_folder_path.exists():
                 extracted_folder_path = INSTALL_DIR / f"sing-box-{{sb_version}}-linux-{{arch}}"

            shutil.move(extracted_folder_path / "sing-box", singbox_path)
            shutil.rmtree(extracted_folder_path)
            tar_path.unlink()
            os.chmod(singbox_path, 0o755)
        except Exception as e:
            print(f"解压或移动sing-box失败: {{e}}")
            if tar_path.exists(): tar_path.unlink()
            sys.exit(1)

    # cloudflared
    cloudflared_path = INSTALL_DIR / "cloudflared"
    if not cloudflared_path.exists():
        cf_arch = arch
        if arch == "armv7": cf_arch = "arm"
        
        cf_url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{{cf_arch}}"
        if not download_binary("cloudflared", cf_url, cloudflared_path):
            print("cloudflared 下载失败，尝试使用备用地址")
            cf_url_backup = f"https://github.91chi.fun/https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{{cf_arch}}"
            if not download_binary("cloudflared", cf_url_backup, cloudflared_path):
                print("cloudflared 备用下载也失败，退出安装")
                sys.exit(1)

    # --- 配置和启动 ---
    config_data = {{
        "uuid_str": uuid_str,
        "port_vm_ws": port_vm_ws,
        "argo_token": argo_token,
        "custom_domain_agn": custom_domain,
        "install_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=2)
    write_debug_log(f"生成配置文件: {{CONFIG_FILE}} with data: {{config_data}}")

    create_sing_box_config(port_vm_ws, uuid_str)
    create_startup_script(argo_token, port_vm_ws, uuid_str)
    setup_autostart()
    start_services()

    final_domain = custom_domain
    if not argo_token and not custom_domain:
        print("正在等待临时隧道域名生成...")
        final_domain = get_tunnel_domain()
        if not final_domain:
            print("\033[31m无法获取tunnel域名。请检查argo.log或尝试手动指定域名。\033[0m")
            print("  方法1: python3 " + os.path.basename(__file__) + " --agn your-domain.com")
            print("  方法2: export agn=your-domain.com && python3 " + os.path.basename(__file__))
            sys.exit(1)
    elif argo_token and not custom_domain:
        print("\033[31m错误: 使用Argo Token时，自定义域名是必需的但未提供。\033[0m")
        sys.exit(1)
    
    if final_domain:
        all_links, link_names = generate_links(final_domain, port_vm_ws, uuid_str)
        return all_links, link_names, final_domain
    else:
        print("\033[31m最终域名未能确定，无法生成链接。\033[0m")
        sys.exit(1)

# 创建sing-box配置
def create_sing_box_config(port_vm_ws, uuid_str):
    write_debug_log(f"创建sing-box配置，端口: {{port_vm_ws}}, UUID: {{uuid_str}}")
    ws_path = f"/{{uuid_str[:8]}}-vm"

    config_dict = {{
        "log": {{"level": "info", "timestamp": True}},
        "inbounds": [{{
            "type": "vmess", "tag": "vmess-in", "listen": "127.0.0.1",
            "listen_port": port_vm_ws, "tcp_fast_open": True, "sniff": True,
            "sniff_override_destination": True, "proxy_protocol": False,
            "users": [{{"uuid": uuid_str, "alterId": 0}}],
            "transport": {{
                "type": "ws", "path": ws_path,
                "max_early_data": 2048, "early_data_header_name": "Sec-WebSocket-Protocol"
            }}
        }}],
        "outbounds": [{{"type": "direct", "tag": "direct"}}]
    }}
    sb_config_file = INSTALL_DIR / "sb.json"
    with open(sb_config_file, 'w') as f:
        json.dump(config_dict, f, indent=2)
    write_debug_log(f"sing-box配置已写入文件: {{sb_config_file}}")
    return True

# 创建启动脚本
def create_startup_script(argo_token, port_vm_ws, uuid_str):
    # sing-box启动脚本
    sb_start_script_path = INSTALL_DIR / "start_sb.sh"
    sb_start_content = f'''#!/bin/bash
cd {{INSTALL_DIR.resolve()}}
./sing-box run -c sb.json > sb.log 2>&1 &
echo $! > {{SB_PID_FILE.name}}
'''
    sb_start_script_path.write_text(sb_start_content)
    os.chmod(sb_start_script_path, 0o755)

    # cloudflared启动脚本
    cf_start_script_path = INSTALL_DIR / "start_cf.sh"
    cf_cmd_base = f"./cloudflared tunnel --no-autoupdate"
    ws_path_for_url = f"/{{uuid_str[:8]}}-vm?ed=2048" 

    if argo_token:
        cf_cmd = f"{{cf_cmd_base}} run --token {{argo_token}}"
    else:
        cf_cmd = f"{{cf_cmd_base}} --url http://localhost:{{port_vm_ws}}{{ws_path_for_url}} --edge-ip-version auto --protocol http2"
    
    cf_start_content = f'''#!/bin/bash
cd {{INSTALL_DIR.resolve()}}
{{cf_cmd}} > {{LOG_FILE.name}} 2>&1 &
echo $! > {{ARGO_PID_FILE.name}}
'''
    cf_start_script_path.write_text(cf_start_content)
    os.chmod(cf_start_script_path, 0o755)
    
    write_debug_log("启动脚本已创建/更新。")

# 设置开机自启动
def setup_autostart():
    try:
        crontab_list = subprocess.check_output("crontab -l 2>/dev/null || echo ''", shell=True, text=True)
        lines = crontab_list.splitlines()
        
        script_name_sb = (INSTALL_DIR / "start_sb.sh").resolve()
        script_name_cf = (INSTALL_DIR / "start_cf.sh").resolve()

        filtered_lines = [
            line for line in lines 
            if str(script_name_sb) not in line and str(script_name_cf) not in line and line.strip()
        ]
        
        filtered_lines.append(f"@reboot {{script_name_sb}} >/dev/null 2>&1")
        filtered_lines.append(f"@reboot {{script_name_cf}} >/dev/null 2>&1")
        
        new_crontab = "\n".join(filtered_lines).strip() + "\n"
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_crontab_file:
            tmp_crontab_file.write(new_crontab)
            crontab_file_path = tmp_crontab_file.name
        
        subprocess.run(f"crontab {{crontab_file_path}}", shell=True, check=True)
        os.unlink(crontab_file_path)
            
        write_debug_log("已设置开机自启动")
        print("开机自启动设置成功。")
    except Exception as e:
        write_debug_log(f"设置开机自启动失败: {{e}}")
        print(f"设置开机自启动失败: {{e}}。但不影响正常使用。")

# 启动服务
def start_services():
    print("正在启动sing-box服务...")
    subprocess.run(str(INSTALL_DIR / "start_sb.sh"), shell=True)
    
    print("正在启动cloudflared服务...")
    subprocess.run(str(INSTALL_DIR / "start_cf.sh"), shell=True)
    
    print("等待服务启动 (约5秒)...")
    time.sleep(5)
    write_debug_log("服务启动命令已执行。")

# 获取tunnel域名
def get_tunnel_domain():
    retry_count = 0
    max_retries = 15
    while retry_count < max_retries:
        if LOG_FILE.exists():
            try:
                log_content = LOG_FILE.read_text()
                match = re.search(r'https://([a-zA-Z0-9.-]+\.trycloudflare\.com)', log_content)
                if match:
                    domain = match.group(1)
                    write_debug_log(f"从日志中提取到临时域名: {{domain}}")
                    print(f"获取到临时域名: {{domain}}")
                    return domain
            except Exception as e:
                write_debug_log(f"读取或解析日志文件 {{LOG_FILE}} 出错: {{e}}")
        
        retry_count += 1
        print(f"等待tunnel域名生成... (尝试 {{retry_count}}/{{max_retries}}, 检查 {{LOG_FILE}})")
        time.sleep(3)
    
    write_debug_log("获取tunnel域名超时。")
    return None

# 主函数
def main(uuid_str, port_vm_ws, argo_token, custom_domain):
    return install(uuid_str, port_vm_ws, argo_token, custom_domain)

if __name__ == "__main__":
    # 直接调用安装函数，传入参数
    all_links, link_names, domain = main("{uuid_str}", {port_vm_ws}, "{argo_token}", "{custom_domain}")
    # 输出结果，让Streamlit捕获
    print("===== 安装完成 =====")
    print(f"域名: {{domain}}")
    print(f"UUID: {{uuid_str}}")
    print(f"端口: {{port_vm_ws}}")
    print("节点链接:")
    for i, (link, name) in enumerate(zip(all_links, link_names)):
        print(f"{{i+1}}. {{name}}:")
        print(link)
        print("")
    print("===== 安装完成 =====")
            """.format(
                uuid_str=uuid_str,
                port_vm_ws=port_vm_ws,
                argo_token=argo_token if argo_token else 'None',
                custom_domain=custom_domain if custom_domain else 'None'
            )
            f.write(script_content)
            temp_script_path = f.name
        
        # 执行临时脚本
        process = subprocess.Popen(
            f"python3 {temp_script_path}",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # 实时捕获输出
        output = []
        for line in iter(process.stdout.readline, ''):
            output.append(line)
            st.code(line, language="plaintext")
            time.sleep(0.1)  # 控制输出速度
        
        process.wait()
        
        # 清理临时文件
        os.unlink(temp_script_path)
        
        # 检查安装结果
        if process.returncode == 0:
            st.success("🎉 安装成功!")
            
            # 尝试读取生成的节点文件
            if ALL_NODES_FILE.exists():
                with open(ALL_NODES_FILE, 'r') as f:
                    node_links = f.read().splitlines()
                
                if node_links:
                    st.subheader("所有节点链接")
                    
                    # 按类型分组节点
                    tls_links = [link for link in node_links if "tls" in link.lower()]
                    http_links = [link for link in node_links if "tls" not in link.lower()]
                    
                    # 显示分组链接
                    if tls_links:
                        st.markdown("### TLS 节点")
                        for i, link in enumerate(tls_links):
                            st.text_area(f"TLS 节点 {i+1}", link, height=100)
                    
                    if http_links:
                        st.markdown("### HTTP 节点")
                        for i, link in enumerate(http_links):
                            st.text_area(f"HTTP 节点 {i+1}", link, height=100)
                    
                    # 复制所有按钮
                    all_links_text = "\n\n".join(node_links)
                    st.button("复制所有链接", on_click=lambda: st.code(all_links_text))
                else:
                    st.warning("未找到生成的节点链接，请检查安装日志。")
            else:
                st.warning("节点文件未生成，请检查安装日志。")
        else:
            st.error(f"安装失败，返回代码: {process.returncode}")
            st.warning("请查看上面的安装日志，找出问题所在。")
