#!/usr/bin/env python3
import os
import json
import subprocess
import sys
import time
import argparse
import platform
import requests
import tempfile
from pathlib import Path

class SetupAssistant:
    def __init__(self):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_dir = os.path.join(os.path.expanduser("~"), ".cloudflared")
        self.singbox_config_path = os.path.join(self.script_dir, "singbox_config.json")
        self.cloudflare_config_path = os.path.join(self.config_dir, "config.yml")
        self.tunnel_name = "singbox-tunnel"
        self.tunnel_uuid = None
        self.domain = None
        self.ss_password = self._generate_password()
        self.ss_port = 8080
        self.is_root = os.geteuid() == 0
        self.api_key = None
        self.user_home = os.path.expanduser("~")
        self.service_dir = os.path.join(self.user_home, ".config", "systemd", "user")
        
    def _generate_password(self, length=16):
        """生成随机密码"""
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits + string.punctuation
        return ''.join(secrets.choice(alphabet) for i in range(length))
        
    def _check_dependency(self, cmd):
        """检查命令是否存在"""
        try:
            subprocess.run([cmd, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
            
    def _run_command(self, cmd, shell=False, check=True, capture_output=False, **kwargs):
        """执行命令并处理输出"""
        print(f"执行命令: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
        result = subprocess.run(cmd, shell=shell, check=check, capture_output=capture_output, **kwargs)
        if capture_output:
            if result.stdout:
                print(f"标准输出:\n{result.stdout.decode('utf-8').strip()}")
            if result.stderr:
                print(f"错误输出:\n{result.stderr.decode('utf-8').strip()}")
        return result
        
    def install_cloudflared(self):
        """安装 Cloudflare 客户端"""
        print("开始安装 Cloudflare 客户端...")
        
        system = platform.system()
        machine = platform.machine()
        
        if system == "Linux":
            if machine == "x86_64":
                arch = "amd64"
            elif machine in ["aarch64", "arm64"]:
                arch = "arm64"
            else:
                print(f"不支持的架构: {machine}")
                return False
                
            try:
                # 使用包管理器安装
                if self.is_root and self._check_dependency("apt"):
                    self._run_command(["sudo", "apt", "update"])
                    self._run_command(["sudo", "apt", "install", "-y", "cloudflared"])
                elif self.is_root and self._check_dependency("yum"):
                    self._run_command(["sudo", "yum", "install", "-y", "cloudflared"])
                else:
                    # 非root用户手动安装到本地目录
                    install_dir = os.path.join(self.user_home, ".local", "bin")
                    os.makedirs(install_dir, exist_ok=True)
                    
                    url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
                        temp_path = f.name
                        print(f"下载 cloudflared 到 {temp_path}")
                        response = requests.get(url, stream=True)
                        response.raise_for_status()
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    os.chmod(temp_path, 0o755)
                    os.rename(temp_path, os.path.join(install_dir, "cloudflared"))
                    
                    # 确保本地bin目录在PATH中
                    if install_dir not in os.environ['PATH']:
                        print(f"警告: {install_dir} 不在PATH中，请将其添加到PATH中")
                        print(f"例如: export PATH=$PATH:{install_dir}")
                
                # 验证安装
                self._run_command(["cloudflared", "--version"])
                print("Cloudflare 客户端安装成功!")
                return True
                
            except Exception as e:
                print(f"安装 Cloudflare 客户端失败: {e}")
                return False
                
        elif system == "Darwin":  # macOS
            try:
                if self._check_dependency("brew"):
                    self._run_command(["brew", "install", "cloudflared"])
                else:
                    print("请先安装 Homebrew 或手动安装 cloudflared")
                    return False
                
                self._run_command(["cloudflared", "--version"])
                print("Cloudflare 客户端安装成功!")
                return True
                
            except Exception as e:
                print(f"安装 Cloudflare 客户端失败: {e}")
                return False
                
        else:
            print(f"不支持的操作系统: {system}")
            return False
    
    def authenticate_cloudflared(self):
        """认证 Cloudflare 客户端"""
        print("开始认证 Cloudflare 客户端...")
        
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)
            
        try:
            # 如果提供了API密钥，使用API密钥进行认证
            if self.api_key:
                print("使用API密钥进行认证...")
                # 解析API密钥
                try:
                    api_data = json.loads(self._decode_api_key(self.api_key))
                    cert_path = os.path.join(self.config_dir, "cert.pem")
                    
                    with open(cert_path, "w") as f:
                        f.write(f"apikey: {api_data['a']}\n")
                        f.write(f"tunnelID: {api_data['t']}\n")
                        f.write(f"secret: {api_data['s']}\n")
                    
                    print("API密钥认证配置完成")
                    return True
                except Exception as e:
                    print(f"API密钥解析失败: {e}")
                    return False
            else:
                # 传统方式认证
                self._run_command(["cloudflared", "tunnel", "login"])
                print("Cloudflare 客户端认证成功!")
                return True
        except Exception as e:
            print(f"Cloudflare 客户端认证失败: {e}")
            return False
            
    def _decode_api_key(self, api_key):
        """解码API密钥"""
        import base64
        # 确保密钥是标准Base64编码
        missing_padding = len(api_key) % 4
        if missing_padding:
            api_key += '=' * (4 - missing_padding)
        try:
            return base64.b64decode(api_key).decode('utf-8')
        except Exception as e:
            print(f"解码API密钥失败: {e}")
            return None
            
    def create_tunnel(self):
        """创建 Cloudflare 隧道"""
        print(f"开始创建 Cloudflare 隧道: {self.tunnel_name}...")
        
        try:
            # 如果提供了UUID，使用它而不是创建新隧道
            if self.tunnel_uuid:
                print(f"使用提供的隧道 UUID: {self.tunnel_uuid}")
                return True
                
            result = self._run_command(
                ["cloudflared", "tunnel", "create", self.tunnel_name],
                capture_output=True
            )
            output = result.stdout.decode('utf-8')
            
            # 提取隧道 UUID
            for line in output.splitlines():
                if "Created tunnel" in line and "with UUID" in line:
                    self.tunnel_uuid = line.split("with UUID ")[-1].strip()
                    break
            
            if not self.tunnel_uuid:
                print("无法获取隧道 UUID")
                return False
                
            print(f"Cloudflare 隧道创建成功! UUID: {self.tunnel_uuid}")
            return True
            
        except Exception as e:
            print(f"创建 Cloudflare 隧道失败: {e}")
            return False
            
    def configure_cloudflared(self):
        """配置 Cloudflare 隧道"""
        print("开始配置 Cloudflare 隧道...")
        
        if not self.tunnel_uuid:
            print("隧道 UUID 不存在，无法配置")
            return False
            
        config_content = f"""url: http://localhost:{self.ss_port}
tunnel: {self.tunnel_uuid}
credentials-file: {os.path.join(self.config_dir, f"{self.tunnel_uuid}.json")}
"""
        
        try:
            with open(self.cloudflare_config_path, "w") as f:
                f.write(config_content)
                
            print(f"Cloudflare 隧道配置文件已保存到: {self.cloudflare_config_path}")
            return True
            
        except Exception as e:
            print(f"配置 Cloudflare 隧道失败: {e}")
            return False
            
    def route_dns(self):
        """配置 DNS 路由"""
        if not self.domain:
            self.domain = input("请输入您的域名 (例如: example.com): ").strip()
            
        print(f"开始配置 DNS 路由: {self.domain}...")
        
        try:
            self._run_command([
                "cloudflared", "tunnel", "route", "dns", 
                self.tunnel_name, self.domain
            ])
            
            print(f"DNS 路由配置成功! 域名 {self.domain} 已指向隧道 {self.tunnel_name}")
            return True
            
        except Exception as e:
            print(f"配置 DNS 路由失败: {e}")
            return False
            
    def install_singbox(self):
        """安装 Singbox"""
        print("开始安装 Singbox...")
        
        system = platform.system()
        machine = platform.machine()
        
        if system != "Linux":
            print(f"目前仅支持 Linux 系统，您的系统是: {system}")
            return False
            
        try:
            # 获取最新版本
            releases_url = "https://api.github.com/repos/SagerNet/sing-box/releases/latest"
            response = requests.get(releases_url)
            response.raise_for_status()
            release = response.json()
            
            # 确定架构
            if machine == "x86_64":
                arch = "amd64"
            elif machine in ["aarch64", "arm64"]:
                arch = "arm64"
            elif machine.startswith("arm"):
                arch = "armv7"
            else:
                print(f"不支持的架构: {machine}")
                return False
                
            # 查找对应的资产
            asset_name = f"sing-box-{release['tag_name'][1:]}-linux-{arch}.tar.gz"
            asset = next((a for a in release["assets"] if a["name"] == asset_name), None)
            
            if not asset:
                print(f"找不到适合的 Singbox 版本: {asset_name}")
                return False
                
            # 下载并安装
            download_url = asset["browser_download_url"]
            with tempfile.TemporaryDirectory() as tmpdir:
                tar_path = os.path.join(tmpdir, "singbox.tar.gz")
                print(f"下载 Singbox 到 {tar_path}")
                
                response = requests.get(download_url, stream=True)
                response.raise_for_status()
                
                with open(tar_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # 解压
                print("解压 Singbox...")
                self._run_command(["tar", "-xzf", tar_path, "-C", tmpdir])
                
                # 移动可执行文件
                singbox_path = os.path.join(tmpdir, f"sing-box-{release['tag_name'][1:]}-linux-{arch}", "singbox")
                if not os.path.exists(singbox_path):
                    singbox_path = os.path.join(tmpdir, "singbox")  # 某些版本可能直接解压到根目录
                
                if not os.path.exists(singbox_path):
                    print("找不到 Singbox 可执行文件")
                    return False
                    
                # 非root用户安装到本地目录
                install_dir = os.path.join(self.user_home, ".local", "bin")
                os.makedirs(install_dir, exist_ok=True)
                os.rename(singbox_path, os.path.join(install_dir, "singbox"))
                os.chmod(os.path.join(install_dir, "singbox"), 0o755)
            
            # 验证安装
            self._run_command(["singbox", "version"])
            print("Singbox 安装成功!")
            return True
            
        except Exception as e:
            print(f"安装 Singbox 失败: {e}")
            return False
            
    def configure_singbox(self):
        """配置 Singbox"""
        print("开始配置 Singbox...")
        
        # 配置文件示例 - Shadowsocks 协议
        config = {
            "log": {
                "level": "info"
            },
            "inbounds": [
                {
                    "type": "shadowsocks",
                    "listen": "127.0.0.1",
                    "port": self.ss_port,
                    "settings": {
                        "method": "chacha20-ietf-poly1305",
                        "password": self.ss_password
                    }
                }
            ],
            "outbounds": [
                {
                    "type": "freedom"
                }
            ]
        }
        
        try:
            with open(self.singbox_config_path, "w") as f:
                json.dump(config, f, indent=2)
                
            print(f"Singbox 配置文件已保存到: {self.singbox_config_path}")
            print(f"Shadowsocks 配置信息:")
            print(f"  方法: chacha20-ietf-poly1305")
            print(f"  密码: {self.ss_password}")
            print(f"  端口: {self.ss_port}")
            
            return True
            
        except Exception as e:
            print(f"配置 Singbox 失败: {e}")
            return False
            
    def create_systemd_service(self, service_name, command, description):
        """创建 Systemd 服务"""
        print(f"创建 Systemd 服务: {service_name}...")
        
        service_content = f"""[Unit]
Description={description}
After=network.target

[Service]
ExecStart={command}
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
"""
        
        # 确定服务文件路径
        if self.is_root:
            service_path = f"/etc/systemd/system/{service_name}.service"
        else:
            os.makedirs(self.service_dir, exist_ok=True)
            service_path = os.path.join(self.service_dir, f"{service_name}.service")
        
        try:
            with open(service_path, "w") as f:
                f.write(service_content)
                
            # 重载systemd
            if self.is_root:
                self._run_command(["sudo", "systemctl", "daemon-reload"])
                self._run_command(["sudo", "systemctl", "enable", service_name])
            else:
                self._run_command(["systemctl", "--user", "daemon-reload"])
                self._run_command(["systemctl", "--user", "enable", service_name])
                # 确保用户服务在登录时自动启动
                self._run_command(["loginctl", "enable-linger", os.getlogin()], check=False)
            
            print(f"Systemd 服务 {service_name} 创建成功!")
            return True
            
        except Exception as e:
            print(f"创建 Systemd 服务失败: {e}")
            return False
            
    def start_services(self):
        """启动服务"""
        print("启动服务...")
        
        try:
            # 启动 Singbox
            if self.create_systemd_service(
                "singbox", 
                f"singbox run -c {self.singbox_config_path}", 
                "Singbox Proxy Service"
            ):
                if self.is_root:
                    self._run_command(["sudo", "systemctl", "start", "singbox"])
                else:
                    self._run_command(["systemctl", "--user", "start", "singbox"])
                print("Singbox 服务已启动")
                
                # 检查状态
                time.sleep(2)
                if self.is_root:
                    result = self._run_command(
                        ["systemctl", "is-active", "singbox"],
                        capture_output=True,
                        check=False
                    )
                else:
                    result = self._run_command(
                        ["systemctl", "--user", "is-active", "singbox"],
                        capture_output=True,
                        check=False
                    )
                    
                if result.stdout.decode('utf-8').strip() != "active":
                    print("警告: Singbox 服务未正常运行")
                    if self.is_root:
                        self._run_command(["systemctl", "status", "singbox"], capture_output=False, check=False)
                    else:
                        self._run_command(["systemctl", "--user", "status", "singbox"], capture_output=False, check=False)
            
            # 启动 Cloudflare 隧道
            if self.create_systemd_service(
                "cloudflared-singbox", 
                f"cloudflared tunnel --config {self.cloudflare_config_path} run {self.tunnel_name}", 
                "Cloudflare Tunnel for Singbox"
            ):
                if self.is_root:
                    self._run_command(["sudo", "systemctl", "start", "cloudflared-singbox"])
                else:
                    self._run_command(["systemctl", "--user", "start", "cloudflared-singbox"])
                print("Cloudflare 隧道服务已启动")
                
                # 检查状态
                time.sleep(2)
                if self.is_root:
                    result = self._run_command(
                        ["systemctl", "is-active", "cloudflared-singbox"],
                        capture_output=True,
                        check=False
                    )
                else:
                    result = self._run_command(
                        ["systemctl", "--user", "is-active", "cloudflared-singbox"],
                        capture_output=True,
                        check=False
                    )
                    
                if result.stdout.decode('utf-8').strip() != "active":
                    print("警告: Cloudflare 隧道服务未正常运行")
                    if self.is_root:
                        self._run_command(["systemctl", "status", "cloudflared-singbox"], capture_output=False, check=False)
                    else:
                        self._run_command(["systemctl", "--user", "status", "cloudflared-singbox"], capture_output=False, check=False)
            
            return True
            
        except Exception as e:
            print(f"启动服务失败: {e}")
            return False
            
    def display_configuration(self):
        """显示配置信息"""
        print("\n" + "="*50)
        print("配置完成! 您的 Singbox 节点信息如下:")
        print("="*50)
        print(f"域名: {self.domain}")
        print(f"协议: Shadowsocks")
        print(f"加密方法: chacha20-ietf-poly1305")
        print(f"密码: {self.ss_password}")
        print(f"端口: 443 (通过 Cloudflare 隧道)")
        print("\n使用说明:")
        print("1. 确保您的域名已正确配置 DNS 指向 Cloudflare")
        print("2. 在您的客户端中配置上述信息")
        print("3. 享受安全的网络连接")
        print("="*50 + "\n")

    def run(self):
        """运行安装程序"""
        print("="*50)
        print("  Singbox 节点与 Cloudflare 隧道一键配置脚本")
        print("="*50)
        
        if not self.is_root:
            print("注意: 此脚本以非root用户身份运行。某些操作可能需要手动配置。")
        
        # 步骤 1: 安装 Cloudflare 客户端
        if not self.install_cloudflared():
            print("安装 Cloudflare 客户端失败，退出脚本")
            return False
            
        # 步骤 2: 认证 Cloudflare 客户端
        if not self.authenticate_cloudflared():
            print("认证 Cloudflare 客户端失败，退出脚本")
            return False
            
        # 步骤 3: 创建隧道
        if not self.create_tunnel():
            print("创建 Cloudflare 隧道失败，退出脚本")
            return False
            
        # 步骤 4: 配置 Cloudflare 隧道
        if not self.configure_cloudflared():
            print("配置 Cloudflare 隧道失败，退出脚本")
            return False
            
        # 步骤 5: 配置 DNS 路由
        if not self.route_dns():
            print("配置 DNS 路由失败，退出脚本")
            return False
            
        # 步骤 6: 安装 Singbox
        if not self.install_singbox():
            print("安装 Singbox 失败，退出脚本")
            return False
            
        # 步骤 7: 配置 Singbox
        if not self.configure_singbox():
            print("配置 Singbox 失败，退出脚本")
            return False
            
        # 步骤 8: 启动服务
        if not self.start_services():
            print("启动服务失败，退出脚本")
            return False
            
        # 显示配置信息
        self.display_configuration()
        
        return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Singbox 节点与 Cloudflare 隧道一键配置脚本")
    parser.add_argument("--domain", help="指定域名")
    parser.add_argument("--port", type=int, default=8080, help="指定 Singbox 端口 (默认: 8080)")
    parser.add_argument("--uuid", help="指定 Cloudflare 隧道 UUID")
    parser.add_argument("--agk", help="指定 Cloudflare API 密钥")
    
    args = parser.parse_args()
    
    setup = SetupAssistant()
    if args.domain:
        setup.domain = args.domain
    if args.port:
        setup.ss_port = args.port
    if args.uuid:
        setup.tunnel_uuid = args.uuid
    if args.agk:
        setup.api_key = args.agk
        
    success = setup.run()
    
    if success:
        print("配置过程已完成!")
    else:
        print("配置过程中出现错误，脚本已退出。")        
