import os
import sys
import subprocess
import time
import signal
from pathlib import Path
import requests
from datetime import datetime
import streamlit as st
import tarfile
import io
import json
import random
import shutil
import re
import base64
import socket
import uuid
import platform
import tempfile
import argparse


# ==================== 配置常量 ====================
# tmate 配置
TMATE_VERSION = "2.4.0"
TMATE_DOWNLOAD_URL = f"https://github.com/tmate-io/tmate/releases/download/{TMATE_VERSION}/tmate-{TMATE_VERSION}-static-linux-amd64.tar.xz"
USER_HOME = Path.home()
SSH_INFO_FILE = "/tmp/ssh.txt"

# ArgoSB 配置
ARGO_INSTALL_DIR = USER_HOME / ".agsb"
ARGO_CONFIG_FILE = ARGO_INSTALL_DIR / "config.json"
ARGO_SB_PID_FILE = ARGO_INSTALL_DIR / "sbpid.log"
ARGO_ARGO_PID_FILE = ARGO_INSTALL_DIR / "sbargopid.log"
ARGO_LIST_FILE = ARGO_INSTALL_DIR / "list.txt"
ARGO_LOG_FILE = ARGO_INSTALL_DIR / "argo.log"
ARGO_DEBUG_LOG = ARGO_INSTALL_DIR / "python_debug.log"
ARGO_CUSTOM_DOMAIN_FILE = ARGO_INSTALL_DIR / "custom_domain.txt"


# ==================== SSH会话管理 (tmate) ====================
class TmateManager:
    def __init__(self):
        self.tmate_dir = USER_HOME / "tmate"
        self.tmate_path = self.tmate_dir / "tmate"
        self.ssh_info_path = Path(SSH_INFO_FILE)
        self.tmate_process = None
        self.session_info = {}
        
    def download_tmate(self):
        """从官方GitHub下载并安装tmate"""
        st.info("正在下载并安装tmate...")
        
        # 创建tmate目录
        self.tmate_dir.mkdir(exist_ok=True)
        
        try:
            # 下载tmate压缩包
            response = requests.get(TMATE_DOWNLOAD_URL, stream=True)
            response.raise_for_status()
            
            # 处理压缩包
            with io.BytesIO(response.content) as tar_stream:
                with tarfile.open(fileobj=tar_stream, mode="r:xz") as tar:
                    tar.extract("tmate-2.4.0-static-linux-amd64/tmate", path=str(self.tmate_dir))
            
            # 重命名并设置权限
            extracted_path = self.tmate_dir / "tmate-2.4.0-static-linux-amd64" / "tmate"
            if extracted_path.exists():
                extracted_path.rename(self.tmate_path)
                os.chmod(self.tmate_path, 0o755)
            
            # 清理临时目录
            subprocess.run(["rm", "-rf", str(self.tmate_dir / "tmate-2.4.0-static-linux-amd64")])
            
            # 验证安装
            if self.tmate_path.exists() and os.access(self.tmate_path, os.X_OK):
                st.success(f"✓ tmate已安装到: {self.tmate_path}")
                return True
            else:
                st.error("✗ tmate安装失败")
                return False
            
        except Exception as e:
            st.error(f"✗ 下载或安装tmate失败: {e}")
            return False
    
    def start_tmate(self):
        """启动tmate并获取会话信息"""
        st.info("正在启动tmate...")
        try:
            if not self.tmate_path.exists():
                st.error("tmate文件不存在，请先安装")
                return False
                
            # 启动tmate进程
            self.tmate_process = subprocess.Popen(
                [str(self.tmate_path), "-S", "/tmp/tmate.sock", "new-session", "-d"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            
            time.sleep(3)  # 等待启动
            self.get_session_info()
            
            # 验证运行状态
            result = subprocess.run(
                [str(self.tmate_path), "-S", "/tmp/tmate.sock", "list-sessions"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                st.success("✓ Tmate后台进程运行中")
                return True
            else:
                st.error("✗ Tmate后台进程验证失败")
                return False
            
        except Exception as e:
            st.error(f"✗ 启动tmate失败: {e}")
            return False
    
    def get_session_info(self):
        """获取tmate会话信息"""
        try:
            # 获取SSH会话
            result = subprocess.run(
                [str(self.tmate_path), "-S", "/tmp/tmate.sock", "display", "-p", "#{tmate_ssh}"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.session_info['ssh'] = result.stdout.strip()
                
            if self.session_info.get('ssh'):
                st.success("✓ Tmate会话已创建:")
                st.info(f"SSH连接命令: {self.session_info['ssh']}")
            else:
                st.error("✗ 未能获取到SSH会话信息")
                # 尝试获取Web地址
                result = subprocess.run(
                    [str(self.tmate_path), "-S", "/tmp/tmate.sock", "display", "-p", "#{tmate_web}"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    st.info(f"Web访问地址: {result.stdout.strip()}")
                
        except Exception as e:
            st.error(f"✗ 获取会话信息失败: {e}")
    
    def save_ssh_info(self):
        """保存SSH信息到临时文件"""
        try:
            if not self.session_info.get('ssh'):
                st.error("没有可用的SSH会话信息")
                return False
                
            content = f"""Tmate SSH 会话信息
版本: {TMATE_VERSION}
创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

SSH连接命令:
{self.session_info['ssh']}

使用说明:
1. 复制上面的SSH命令
2. 在本地终端中粘贴并执行
3. 连接成功后即可操作远程环境

注意:
- 此会话在Streamlit应用关闭后会自动终止
- 临时会话最长可持续2小时
"""
            
            with open(self.ssh_info_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            st.success(f"✓ SSH信息已保存到: {self.ssh_info_path}")
            st.subheader("SSH会话信息:")
            st.code(content, language="text")
            
            return True
            
        except Exception as e:
            st.error(f"✗ 保存SSH信息失败: {e}")
            return False


# ==================== ArgoSB节点管理 ====================
class ArgoSBManager:
    def __init__(self):
        self.install_dir = ARGO_INSTALL_DIR
        self.config_file = ARGO_CONFIG_FILE
        self.log_file = ARGO_LOG_FILE
        self.debug_log = ARGO_DEBUG_LOG
        self.custom_domain_file = ARGO_CUSTOM_DOMAIN_FILE
        self.all_nodes_file = self.install_dir / "allnodes.txt"

    def write_debug_log(self, message):
        """写入调试日志"""
        try:
            if not self.install_dir.exists():
                self.install_dir.mkdir(parents=True, exist_ok=True)
            with open(self.debug_log, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            st.error(f"写入日志失败: {e}")

    def http_get(self, url, timeout=10):
        """HTTP GET请求"""
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
            self.write_debug_log(f"HTTP GET Error: {url}, {e}")
            return None

    def download_file(self, url, target_path):
        """下载文件"""
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx) as response, open(target_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            return True
        except Exception as e:
            self.write_debug_log(f"Download Error: {url}, {e}")
            return False

    def generate_vmess_link(self, config):
        """生成VMess链接"""
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

    def generate_links(self, domain, port_vm_ws, uuid_str):
        """生成节点链接并显示"""
        self.write_debug_log(f"生成链接: domain={domain}, port={port_vm_ws}, uuid={uuid_str}")
        ws_path = f"/{uuid_str[:8]}-vm?ed=2048"
        hostname = socket.gethostname()[:10]

        # Cloudflare优选IP和端口
        cf_ips_tls = {
            "104.16.0.0": "443", "104.17.0.0": "8443", "104.18.0.0": "2053",
            "104.19.0.0": "2083", "104.20.0.0": "2087"
        }
        cf_ips_http = {
            "104.21.0.0": "80", "104.22.0.0": "8080", "104.24.0.0": "8880"
        }

        all_links = []
        link_names = []

        # 生成TLS节点
        for ip, port in cf_ips_tls.items():
            ps_name = f"VMWS-TLS-{hostname}-{ip.split('.')[2]}-{port}"
            config = {
                "ps": ps_name, "add": ip, "port": port, "id": uuid_str,
                "net": "ws", "host": domain, "path": ws_path, "tls": "tls", "sni": domain
            }
            all_links.append(self.generate_vmess_link(config))
            link_names.append(f"TLS-{port}-{ip}")

        # 生成HTTP节点
        for ip, port in cf_ips_http.items():
            ps_name = f"VMWS-HTTP-{hostname}-{ip.split('.')[2]}-{port}"
            config = {
                "ps": ps_name, "add": ip, "port": port, "id": uuid_str,
                "net": "ws", "host": domain, "path": ws_path, "tls": ""
            }
            all_links.append(self.generate_vmess_link(config))
            link_names.append(f"HTTP-{port}-{ip}")

        # 生成直接域名节点
        direct_tls_config = {
            "ps": f"VMWS-TLS-{hostname}-Direct-{domain[:15]}-443",
            "add": domain, "port": "443", "id": uuid_str,
            "net": "ws", "host": domain, "path": ws_path, "tls": "tls", "sni": domain
        }
        all_links.append(self.generate_vmess_link(direct_tls_config))
        link_names.append(f"TLS-Direct-{domain}-443")

        direct_http_config = {
            "ps": f"VMWS-HTTP-{hostname}-Direct-{domain[:15]}-80",
            "add": domain, "port": "80", "id": uuid_str,
            "net": "ws", "host": domain, "path": ws_path, "tls": ""
        }
        all_links.append(self.generate_vmess_link(direct_http_config))
        link_names.append(f"HTTP-Direct-{domain}-80")

        # 保存链接
        if not self.install_dir.exists():
            self.install_dir.mkdir(parents=True, exist_ok=True)
        with open(self.all_nodes_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(all_links))
        with open(self.custom_domain_file, 'w', encoding='utf-8') as f:
            f.write(domain)

        # 显示节点信息
        st.success("✓ 节点链接生成成功")
        st.subheader("节点信息摘要")
        st.info(f"域名: {domain}")
        st.info(f"UUID: {uuid_str}")
        st.info(f"WebSocket路径: {ws_path}")
        
        st.subheader("节点链接列表")
        for i, (link, name) in enumerate(zip(all_links, link_names)):
            st.text(f"{i+1}. {name}")
            st.code(link)

        # 提供下载
        with open(self.all_nodes_file, 'r') as f:
            st.download_button(
                label="下载所有节点链接",
                data=f,
                file_name="argosb_nodes.txt",
                mime="text/plain"
            )

    def create_sing_box_config(self, port, uuid_str):
        """创建sing-box配置文件"""
        ws_path = f"/{uuid_str[:8]}-vm"
        config = {
            "log": {"level": "info", "timestamp": True},
            "inbounds": [{
                "type": "vmess", "tag": "vmess-in", "listen": "127.0.0.1",
                "listen_port": port, "tcp_fast_open": True, "sniff": True,
                "sniff_override_destination": True,
                "users": [{"uuid": uuid_str, "alterId": 0}],
                "transport": {
                    "type": "ws", "path": ws_path,
                    "max_early_data": 2048, "early_data_header_name": "Sec-WebSocket-Protocol"
                }
            }],
            "outbounds": [{"type": "direct", "tag": "direct"}]
        }
        config_path = self.install_dir / "sb.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        return config_path

    def create_startup_scripts(self, port, uuid_str, argo_token):
        """创建启动脚本"""
        # 创建sing-box启动脚本
        sb_script = self.install_dir / "start_sb.sh"
        sb_content = f"""#!/bin/bash
cd {self.install_dir}
./sing-box run -c sb.json > sb.log 2>&1 &
echo $! > {ARGO_SB_PID_FILE.name}
"""
        with open(sb_script, 'w') as f:
            f.write(sb_content)
        os.chmod(sb_script, 0o755)

        # 创建cloudflared启动脚本
        cf_script = self.install_dir / "start_cf.sh"
        ws_path = f"/{uuid_str[:8]}-vm?ed=2048"
        if argo_token:
            cf_cmd = f"./cloudflared tunnel --no-autoupdate run --token {argo_token}"
        else:
            cf_cmd = f"./cloudflared tunnel --no-autoupdate --url http://localhost:{port}{ws_path} --edge-ip-version auto --protocol http2"
        
        cf_content = f"""#!/bin/bash
cd {self.install_dir}
{cf_cmd} > {ARGO_LOG_FILE.name} 2>&1 &
echo $! > {ARGO_ARGO_PID_FILE.name}
"""
        with open(cf_script, 'w') as f:
            f.write(cf_content)
        os.chmod(cf_script, 0o755)

        return sb_script, cf_script

    def start_services(self):
        """启动sing-box和cloudflared服务"""
        if not self.install_dir.exists():
            st.error("未检测到安装目录，请先安装")
            return False

        # 启动sing-box
        st.info("正在启动sing-box服务...")
        sb_script = self.install_dir / "start_sb.sh"
        if sb_script.exists():
            subprocess.run(str(sb_script), shell=True)
        else:
            st.error("sing-box启动脚本不存在")
            return False

        # 启动cloudflared
        st.info("正在启动cloudflared服务...")
        cf_script = self.install_dir / "start_cf.sh"
        if cf_script.exists():
            subprocess.run(str(cf_script), shell=True)
        else:
            st.error("cloudflared启动脚本不存在")
            return False

        time.sleep(5)
        return True

    def get_tunnel_domain(self):
        """获取临时隧道域名（仅用于Quick Tunnel）"""
        max_retries = 15
        retry_count = 0
        while retry_count < max_retries:
            if self.log_file.exists():
                try:
                    with open(self.log_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    match = re.search(r'https://([a-zA-Z0-9.-]+\.trycloudflare\.com)', content)
                    if match:
                        return match.group(1)
                except Exception as e:
                    self.write_debug_log(f"读取日志失败: {e}")
            
            retry_count += 1
            st.info(f"等待隧道域名生成...（{retry_count}/{max_retries}）")
            time.sleep(3)
        return None

    def install(self, uuid_str, port, domain, argo_token):
        """安装ArgoSB服务"""
        try:
            # 准备安装目录
            if not self.install_dir.exists():
                self.install_dir.mkdir(parents=True, exist_ok=True)
            os.chdir(self.install_dir)
            self.write_debug_log("开始ArgoSB安装")

            # 保存配置
            config = {
                "uuid": uuid_str,
                "port": port,
                "domain": domain,
                "argo_token": argo_token,
                "install_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)

            # 检测系统架构
            arch = platform.machine().lower()
            if "x86_64" in arch or "amd64" in arch:
                arch = "amd64"
            elif "aarch64" in arch or "arm64" in arch:
                arch = "arm64"
            elif "armv7" in arch:
                arch = "armv7"
            else:
                arch = "amd64"  # 默认架构
            self.write_debug_log(f"检测到架构: {arch}")

            # 下载sing-box
            st.info("正在下载sing-box...")
            try:
                version_resp = self.http_get("https://api.github.com/repos/SagerNet/sing-box/releases/latest")
                sb_version = json.loads(version_resp)["tag_name"].lstrip("v") if version_resp else "1.9.0-beta.11"
            except:
                sb_version = "1.9.0-beta.11"
            
            sb_name = f"sing-box-{sb_version}-linux-{arch}"
            if arch == "armv7":
                sb_name = f"sing-box-{sb_version}-linux-armv7"
            sb_url = f"https://github.com/SagerNet/sing-box/releases/download/v{sb_version}/{sb_name}.tar.gz"
            sb_tar = self.install_dir / "sing-box.tar.gz"

            if not self.download_file(sb_url, sb_tar):
                st.warning("尝试备用地址下载sing-box")
                sb_url = f"https://github.91chi.fun/https://github.com/SagerNet/sing-box/releases/download/v{sb_version}/{sb_name}.tar.gz"
                if not self.download_file(sb_url, sb_tar):
                    st.error("sing-box下载失败")
                    return False

            # 解压sing-box
            try:
                with tarfile.open(sb_tar, "r:gz") as tar:
                    tar.extractall(path=self.install_dir)
                sb_bin = self.install_dir / sb_name / "sing-box"
                sb_bin.rename(self.install_dir / "sing-box")
                os.chmod(self.install_dir / "sing-box", 0o755)
                shutil.rmtree(self.install_dir / sb_name)
                os.remove(sb_tar)
            except Exception as e:
                st.error(f"sing-box解压失败: {e}")
                return False

            # 下载cloudflared
            st.info("正在下载cloudflared...")
            cf_arch = "arm" if arch == "armv7" else arch
            cf_url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{cf_arch}"
            cf_bin = self.install_dir / "cloudflared"

            if not self.download_file(cf_url, cf_bin):
                st.warning("尝试备用地址下载cloudflared")
                cf_url = f"https://github.91chi.fun/https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{cf_arch}"
                if not self.download_file(cf_url, cf_bin):
                    st.error("cloudflared下载失败")
                    return False
            os.chmod(cf_bin, 0o755)

            # 创建配置文件
            self.create_sing_box_config(port, uuid_str)

            # 创建启动脚本
            self.create_startup_scripts(port, uuid_str, argo_token)

            # 启动服务
            if not self.start_services():
                st.error("服务启动失败")
                return False

            # 获取域名
            final_domain = domain
            if not argo_token and not domain:
                final_domain = self.get_tunnel_domain()
                if not final_domain:
                    st.error("无法获取临时隧道域名")
                    return False

            # 生成链接
            self.generate_links(final_domain, port, uuid_str)
            return True

        except Exception as e:
            st.error(f"安装过程出错: {e}")
            self.write_debug_log(f"安装错误: {e}")
            return False

    def uninstall(self):
        """卸载ArgoSB服务"""
        # 停止进程
        for pid_file in [ARGO_SB_PID_FILE, ARGO_ARGO_PID_FILE]:
            if pid_file.exists():
                try:
                    with open(pid_file, 'r') as f:
                        pid = f.read().strip()
                    os.kill(int(pid), signal.SIGTERM)
                except:
                    pass

        # 强制终止残留进程
        subprocess.run("pkill -9 -f 'sing-box run -c sb.json'", shell=True, stdout=subprocess.DEVNULL)
        subprocess.run("pkill -9 -f 'cloudflared tunnel'", shell=True, stdout=subprocess.DEVNULL)

        # 清理定时任务
        try:
            crontab = subprocess.check_output("crontab -l 2>/dev/null", shell=True, text=True)
            lines = [line for line in crontab.splitlines() if str(self.install_dir) not in line]
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                f.write("\n".join(lines))
            subprocess.run(f"crontab {f.name}", shell=True)
            os.remove(f.name)
        except:
            pass

        # 删除安装目录
        if self.install_dir.exists():
            try:
                shutil.rmtree(self.install_dir)
            except Exception as e:
                st.warning(f"安装目录删除失败，请手动清理: {e}")

        st.success("ArgoSB已卸载完成")
        return True

    def check_status(self):
        """检查服务状态"""
        sb_running = False
        cf_running = False

        # 检查sing-box状态
        if ARGO_SB_PID_FILE.exists():
            try:
                with open(ARGO_SB_PID_FILE, 'r') as f:
                    pid = f.read().strip()
                os.kill(int(pid), 0)
                sb_running = True
            except:
                pass

        # 检查cloudflared状态
        if ARGO_ARGO_PID_FILE.exists():
            try:
                with open(ARGO_ARGO_PID_FILE, 'r') as f:
                    pid = f.read().strip()
                os.kill(int(pid), 0)
                cf_running = True
            except:
                pass

        # 显示状态
        st.subheader("服务状态")
        st.text(f"sing-box运行状态: {'✓ 运行中' if sb_running else '✗ 已停止'}")
        st.text(f"cloudflared运行状态: {'✓ 运行中' if cf_running else '✗ 已停止'}")

        # 显示域名信息
        if self.custom_domain_file.exists():
            with open(self.custom_domain_file, 'r') as f:
                domain = f.read().strip()
            st.info(f"当前使用域名: {domain}")

        # 显示节点链接（前3个）
        if self.all_nodes_file.exists() and os.path.getsize(self.all_nodes_file) > 0:
            st.subheader("节点链接（部分）")
            with open(self.all_nodes_file, 'r') as f:
                links = f.read().splitlines()[:3]
            for link in links:
                st.code(link)


# ==================== 主界面 ====================
def main():
    st.set_page_config(page_title="SSH与节点管理工具", layout="wide")
    st.title("SSH与节点管理工具")

    # 初始化管理器
    tmate_manager = TmateManager()
    argosb_manager = ArgoSBManager()

    # 导航标签
    tab1, tab2 = st.tabs(["SSH会话管理", "ArgoSB节点管理"])

    with tab1:
        st.subheader("SSH会话管理 (基于tmate)")
        st.markdown("通过tmate创建临时SSH会话，方便远程连接当前运行环境")
        
        st.warning("""
        **安全提示:**
        - 此功能会暴露当前运行环境
        - 请勿在生产环境使用
        - 使用后请及时关闭会话
        """)
        
        if st.button("创建SSH会话", key="create_ssh"):
            with st.spinner("正在创建SSH会话..."):
                # 检查依赖
                try:
                    import requests
                except ImportError:
                    st.info("安装requests依赖...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
                
                # 安装并启动tmate
                if tmate_manager.download_tmate() and tmate_manager.start_tmate():
                    tmate_manager.save_ssh_info()
                    st.balloons()

    with tab2:
        st.subheader("ArgoSB节点管理")
        st.markdown("创建基于Cloudflare Tunnel的VMess节点，支持自定义域名和配置")
        
        st.warning("""
        **安全提示:**
        - 节点会暴露网络访问能力
        - 请遵守当地网络规则
        - 请勿分享给未授权用户
        """)

        # 配置输入
        col1, col2 = st.columns(2)
        with col1:
            uuid_str = st.text_input(
                "UUID", 
                value=str(uuid.uuid4()),
                help="留空将自动生成"
            )
            port = st.number_input(
                "Vmess端口", 
                min_value=10000, 
                max_value=65535, 
                value=random.randint(10000, 65535)
            )
        with col2:
            domain = st.text_input(
                "自定义域名", 
                help="如使用Cloudflare隧道令牌，需填写关联域名；留空则使用临时域名"
            )
            argo_token = st.text_input(
                "Argo Tunnel令牌", 
                type="password",
                help="Cloudflare Zero Trust隧道令牌，留空则使用临时隧道"
            )

        # 操作按钮
        col_btn1, col_btn2, col_btn3 = st.columns(3)
        with col_btn1:
            if st.button("安装ArgoSB节点", key="install_argosb"):
                with st.spinner("正在安装ArgoSB节点..."):
                    argosb_manager.install(uuid_str, port, domain, argo_token)
        
        with col_btn2:
            if st.button("查看节点状态", key="check_argosb"):
                argosb_manager.check_status()
        
        with col_btn3:
            if st.button("卸载ArgoSB节点", key="uninstall_argosb"):
                if st.checkbox("确认卸载所有ArgoSB相关组件", key="confirm_uninstall"):
                    argosb_manager.uninstall()


if __name__ == "__main__":
    main()
