#!/usr/bin/env python3
import os
import sys
import json
import random
import string
import subprocess
import argparse
import socket
import time
from pathlib import Path

class SingBoxInstaller:
    def __init__(self):
        self.base_dir = Path.home() / 'singbox'
        self.config_dir = self.base_dir / 'config'
        self.log_dir = self.base_dir / 'log'
        self.bin_dir = self.base_dir / 'bin'
        self.service_file = '/etc/systemd/system/singbox.service'
        self.singbox_bin = self.bin_dir / 'singbox'
        self.cfd_bin = self.bin_dir / 'cloudflared'
        self.domain = None
        self.reality_uuid = None
        self.reality_short_id = None
        self.reality_private_key = None
        self.reality_public_key = None
        self.port = 443
        self.tls_port = 2053  # 用于Cloudflare代理的端口
        self.cfd_token = None

    def check_root(self):
        if os.geteuid() != 0:
            print("请使用root权限运行此脚本")
            sys.exit(1)

    def create_directories(self):
        for directory in [self.base_dir, self.config_dir, self.log_dir, self.bin_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def install_dependencies(self):
        print("正在安装依赖...")
        try:
            if os.path.exists('/etc/debian_version'):
                subprocess.run(['apt', 'update', '-y'], check=True)
                subprocess.run(['apt', 'install', 'curl', 'wget', 'unzip', 'xz-utils', '-y'], check=True)
            elif os.path.exists('/etc/redhat-release'):
                subprocess.run(['yum', 'update', '-y'], check=True)
                subprocess.run(['yum', 'install', 'curl', 'wget', 'unzip', 'xz-utils', '-y'], check=True)
            else:
                print("不支持的操作系统")
                sys.exit(1)
        except subprocess.CalledProcessError as e:
            print(f"安装依赖失败: {e}")
            sys.exit(1)

    def download_singbox(self):
        print("正在下载singbox...")
        try:
            arch = self.get_architecture()
            download_url = f"https://github.com/SagerNet/sing-box/releases/latest/download/sing-box-{arch}-linux.zip"
            zip_file = self.bin_dir / "sing-box.zip"
            
            subprocess.run(['curl', '-L', '-o', str(zip_file), download_url], check=True)
            subprocess.run(['unzip', '-o', str(zip_file), '-d', str(self.bin_dir)], check=True)
            os.chmod(str(self.singbox_bin), 0o755)
            zip_file.unlink()
            
            print("singbox下载完成")
        except Exception as e:
            print(f"下载singbox失败: {e}")
            sys.exit(1)

    def download_cloudflared(self):
        print("正在下载cloudflared...")
        try:
            arch = self.get_architecture()
            if arch == 'amd64':
                cf_arch = 'amd64'
            elif arch == 'arm64':
                cf_arch = 'arm64'
            else:
                cf_arch = 'arm'
            
            download_url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{cf_arch}"
            
            subprocess.run(['curl', '-L', '-o', str(self.cfd_bin), download_url], check=True)
            os.chmod(str(self.cfd_bin), 0o755)
            
            print("cloudflared下载完成")
        except Exception as e:
            print(f"下载cloudflared失败: {e}")
            sys.exit(1)

    def get_architecture(self):
        machine = os.uname().machine
        if machine == 'x86_64':
            return 'amd64'
        elif machine.startswith('arm') or machine == 'aarch64':
            return 'arm64'
        else:
            return 'amd64'  # 默认使用amd64

    def generate_config(self):
        print("正在生成配置文件...")
        self.reality_uuid = self.generate_uuid()
        self.reality_short_id = self.generate_short_id()
        
        # 生成Reality密钥对
        keygen_output = subprocess.check_output([str(self.singbox_bin), 'gen', ' reality-keypair']).decode('utf-8')
        lines = keygen_output.strip().split('\n')
        self.reality_private_key = lines[0].split(': ')[1].strip()
        self.reality_public_key = lines[1].split(': ')[1].strip()
        
        # 生成singbox配置
        config = {
            "log": {
                "level": "info",
                "timestamp": True,
                "output": str(self.log_dir / "singbox.log")
            },
            "inbounds": [
                {
                    "type": "vless",
                    "listen": "0.0.0.0",
                    "listen_port": self.port,
                    "users": [
                        {
                            "uuid": self.reality_uuid
                        }
                    ],
                    "encryption": "none",
                    "transport": {
                        "type": "tcp"
                    },
                    "tls": {
                        "enabled": True,
                        "server_name": self.domain,
                        "reality": {
                            "enabled": True,
                            "private_key": self.reality_private_key,
                            "short_id": [self.reality_short_id],
                            "handshake": {
                                "server": self.domain,
                                "server_port": 443
                            }
                        }
                    }
                }
            ],
            "outbounds": [
                {
                    "type": "direct"
                }
            ]
        }
        
        config_file = self.config_dir / "config.json"
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print("配置文件生成完成")
        return config_file

    def generate_uuid(self):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=32))

    def generate_short_id(self):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

    def create_service(self):
        print("正在创建systemd服务...")
        service_content = f"""[Unit]
Description=SingBox Service
After=network.target nss-lookup.target

[Service]
User=root
WorkingDirectory={self.base_dir}
ExecStart={self.singbox_bin} run -c {self.config_dir}/config.json
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
"""
        
        with open(self.service_file, 'w') as f:
            f.write(service_content)
        
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', 'singbox'], check=True)
        
        print("systemd服务创建完成")

    def configure_cloudflared(self):
        print("正在配置Cloudflare Tunnel...")
        # 创建Cloudflare配置文件
        cfd_config = {
            "url": f"tcp://localhost:{self.port}",
            "protocol": "http2",
            "no-tls-verify": True
        }
        
        cfd_config_file = self.config_dir / "cloudflared.json"
        with open(cfd_config_file, 'w') as f:
            json.dump(cfd_config, f, indent=2)
        
        # 创建Cloudflare服务
        cfd_service_file = '/etc/systemd/system/cloudflared.service'
        cfd_service_content = f"""[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={self.base_dir}
ExecStart={self.cfd_bin} tunnel --config {cfd_config_file} --url tcp://localhost:{self.port} run
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        
        with open(cfd_service_file, 'w') as f:
            f.write(cfd_service_content)
        
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', 'cloudflared'], check=True)
        
        print("Cloudflare Tunnel配置完成")

    def start_services(self):
        print("正在启动服务...")
        subprocess.run(['systemctl', 'start', 'singbox'], check=True)
        subprocess.run(['systemctl', 'start', 'cloudflared'], check=True)
        
        # 检查服务状态
        time.sleep(2)
        singbox_status = subprocess.run(['systemctl', 'is-active', 'singbox'], capture_output=True, text=True).stdout.strip()
        cfd_status = subprocess.run(['systemctl', 'is-active', 'cloudflared'], capture_output=True, text=True).stdout.strip()
        
        if singbox_status != 'active' or cfd_status != 'active':
            print("服务启动失败，请检查日志")
            sys.exit(1)
        
        print("服务已成功启动")

    def show_config(self):
        print("\n===== 节点配置信息 =====")
        print(f"Domain: {self.domain}")
        print(f"UUID: {self.reality_uuid}")
        print(f"ShortID: {self.reality_short_id}")
        print(f"PublicKey: {self.reality_public_key}")
        print(f"Port: {self.port}")
        
        # 生成客户端配置示例
        vless_url = f"vless://{self.reality_uuid}@{self.domain}:{self.tls_port}?encryption=none&security=reality&sni={self.domain}&fp=chrome&pbk={self.reality_public_key}&sid={self.reality_short_id}&type=tcp&flow=xtls-rprx-vision#SingBox-VLESS-Reality"
        
        print("\n===== 客户端配置链接 =====")
        print(vless_url)
        
        client_config = {
            "outbounds": [
                {
                    "type": "vless",
                    "server": self.domain,
                    "server_port": self.tls_port,
                    "uuid": self.reality_uuid,
                    "flow": "xtls-rprx-vision",
                    "network": "tcp",
                    "tls": {
                        "enabled": true,
                        "server_name": self.domain,
                        "reality": {
                            "enabled": true,
                            "public_key": self.reality_public_key,
                            "short_id": self.reality_short_id,
                            "fingerprint": "chrome"
                        }
                    }
                }
            ]
        }
        
        print("\n===== 客户端配置JSON =====")
        print(json.dumps(client_config, indent=2))

    def open_firewall(self):
        print("正在配置防火墙...")
        try:
            if os.path.exists('/usr/sbin/ufw'):
                subprocess.run(['ufw', 'allow', str(self.port)], check=True)
                subprocess.run(['ufw', 'allow', str(self.tls_port)], check=True)
                subprocess.run(['ufw', 'reload'], check=True)
            elif os.path.exists('/usr/sbin/firewalld'):
                subprocess.run(['firewall-cmd', '--permanent', '--add-port', f'{self.port}/tcp'], check=True)
                subprocess.run(['firewall-cmd', '--permanent', '--add-port', f'{self.tls_port}/tcp'], check=True)
                subprocess.run(['firewall-cmd', '--reload'], check=True)
            else:
                print("未检测到防火墙，跳过配置")
        except Exception as e:
            print(f"配置防火墙失败: {e}")

    def run(self):
        parser = argparse.ArgumentParser(description='SingBox VLESS Reality 节点一键安装脚本')
        parser.add_argument('--domain', required=True, help='你的域名')
        parser.add_argument('--port', type=int, default=443, help='服务端口，默认为443')
        parser.add_argument('--tls-port', type=int, default=2053, help='Cloudflare代理端口，默认为2053')
        
        args = parser.parse_args()
        
        self.domain = args.domain
        self.port = args.port
        self.tls_port = args.tls_port
        
        print("===== SingBox VLESS Reality 节点安装脚本 =====")
        
        self.check_root()
        self.create_directories()
        self.install_dependencies()
        self.download_singbox()
        self.download_cloudflared()
        self.generate_config()
        self.create_service()
        self.configure_cloudflared()
        self.open_firewall()
        self.start_services()
        self.show_config()
        
        print("\n===== 安装完成 =====")
        print("节点已成功配置并启动")
        print("请确保你的域名已正确解析到本服务器IP")
        print("并在Cloudflare面板中配置相应的代理规则")

if __name__ == "__main__":
    installer = SingBoxInstaller()
    installer.run()    
