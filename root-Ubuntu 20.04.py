#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import time
import threading
import signal
from pathlib import Path
import requests
from datetime import datetime

# 配置（移除上传API相关配置）
TMATE_URL = "https://github.com/zhumengkang/agsb/raw/main/tmate"
USER_HOME = Path.home()
SSH_INFO_FILE = "ssh.txt"  # 会话信息保存文件名


class TmateManager:
    def __init__(self):
        self.tmate_path = USER_HOME / "tmate"
        self.ssh_info_path = USER_HOME / SSH_INFO_FILE
        self.tmate_process = None
        self.session_info = {}
        
    def download_tmate(self):
        """下载tmate文件到用户目录（适配Ubuntu的权限处理）"""
        print("正在下载tmate...")
        try:
            # Ubuntu系统下确保目录可写（root权限下兼容普通用户目录）
            if not USER_HOME.exists():
                USER_HOME.mkdir(parents=True, exist_ok=True)
                os.chmod(USER_HOME, 0o755)  # 修复目录权限（Ubuntu常见问题）
            
            response = requests.get(TMATE_URL, stream=True)
            response.raise_for_status()
            
            with open(self.tmate_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Ubuntu下设置执行权限（兼容root和普通用户）
            os.chmod(self.tmate_path, 0o755)
            print(f"✓ tmate已下载到: {self.tmate_path}")
            print(f"✓ 已添加执行权限 (chmod 755)")
            
            # 验证文件是否可执行（Ubuntu权限校验）
            if os.access(self.tmate_path, os.X_OK):
                print("✓ 执行权限验证成功")
            else:
                print("✗ 执行权限验证失败，尝试强制修复权限...")
                os.chmod(self.tmate_path, 0o777)  # Ubuntu下极端情况修复
                if os.access(self.tmate_path, os.X_OK):
                    print("✓ 权限强制修复成功")
                else:
                    print("✗ 权限修复失败，无法执行tmate")
                    return False
            
            return True
            
        except Exception as e:
            print(f"✗ 下载tmate失败: {e}")
            return False
    
    def start_tmate(self):
        """启动tmate并获取会话信息（适配Ubuntu进程管理）"""
        print("正在启动tmate...")
        try:
            # Ubuntu下使用/tmp目录（确保可写，root和普通用户均有权限）
            if not os.path.exists("/tmp"):
                os.makedirs("/tmp", exist_ok=True)
                os.chmod("/tmp", 0o1777)  # Ubuntu标准/tmp权限
            
            # 启动tmate进程（Ubuntu下使用分离模式，兼容systemd）
            self.tmate_process = subprocess.Popen(
                [str(self.tmate_path), "-S", "/tmp/tmate.sock", "new-session", "-d"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True  # 脱离父进程，避免被系统杀死
            )
            
            # Ubuntu下tmate启动可能较慢，延长等待时间
            time.sleep(8)
            
            # 获取会话信息
            self.get_session_info()
            
            # 验证tmate是否在运行（Ubuntu下进程检查）
            try:
                result = subprocess.run(
                    [str(self.tmate_path), "-S", "/tmp/tmate.sock", "list-sessions"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    print("✓ Tmate后台进程验证成功")
                    return True
                else:
                    print("✗ Tmate后台进程验证失败，尝试重启...")
                    # 重试一次（Ubuntu下偶尔启动失败）
                    self.tmate_process = subprocess.Popen(
                        [str(self.tmate_path), "-S", "/tmp/tmate.sock", "new-session", "-d"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    time.sleep(5)
                    result = subprocess.run(
                        [str(self.tmate_path), "-S", "/tmp/tmate.sock", "list-sessions"],
                        capture_output=True, text=True, timeout=5
                    )
                    return result.returncode == 0
            except Exception as e:
                print(f"✗ 验证tmate进程失败: {e}")
                return False
            
        except Exception as e:
            print(f"✗ 启动tmate失败: {e}")
            return False
    
    def get_session_info(self):
        """获取tmate会话信息（保持原逻辑，适配Ubuntu输出格式）"""
        try:
            # 获取只读web会话
            result = subprocess.run(
                [str(self.tmate_path), "-S", "/tmp/tmate.sock", "display", "-p", "#{tmate_web_ro}"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.session_info['web_ro'] = result.stdout.strip()
            
            # 获取只读SSH会话
            result = subprocess.run(
                [str(self.tmate_path), "-S", "/tmp/tmate.sock", "display", "-p", "#{tmate_ssh_ro}"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.session_info['ssh_ro'] = result.stdout.strip()
            
            # 获取可写web会话
            result = subprocess.run(
                [str(self.tmate_path), "-S", "/tmp/tmate.sock", "display", "-p", "#{tmate_web}"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.session_info['web_rw'] = result.stdout.strip()
            
            # 获取可写SSH会话
            result = subprocess.run(
                [str(self.tmate_path), "-S", "/tmp/tmate.sock", "display", "-p", "#{tmate_ssh}"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.session_info['ssh_rw'] = result.stdout.strip()
                
            # 显示会话信息
            if self.session_info:
                print("\n✓ Tmate会话已创建:")
                if 'web_ro' in self.session_info:
                    print(f"  只读Web会话: {self.session_info['web_ro']}")
                if 'ssh_ro' in self.session_info:
                    print(f"  只读SSH会话: {self.session_info['ssh_ro']}")
                if 'web_rw' in self.session_info:
                    print(f"  可写Web会话: {self.session_info['web_rw']}")
                if 'ssh_rw' in self.session_info:
                    print(f"  可写SSH会话: {self.session_info['ssh_rw']}")
            else:
                print("✗ 未能获取到会话信息")
                
        except Exception as e:
            print(f"✗ 获取会话信息失败: {e}")
    
    def save_ssh_info(self):
        """保存SSH信息到文件（Ubuntu下确保用户目录可写）"""
        try:
            content = f"""Tmate SSH 会话信息
创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
运行系统: Ubuntu (已适配)
运行权限: root

"""
            
            if 'web_ro' in self.session_info:
                content += f"web session read only: {self.session_info['web_ro']}\n"
            if 'ssh_ro' in self.session_info:
                content += f"ssh session read only: {self.session_info['ssh_ro']}\n"
            if 'web_rw' in self.session_info:
                content += f"web session: {self.session_info['web_rw']}\n"
            if 'ssh_rw' in self.session_info:
                content += f"ssh session: {self.session_info['ssh_rw']}\n"
            
            # Ubuntu下确保文件所有者正确（root运行时归属root）
            with open(self.ssh_info_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 修复文件权限（确保root创建的文件可被普通用户读取）
            os.chmod(self.ssh_info_path, 0o644)
            print(f"✓ SSH信息已保存到: {self.ssh_info_path}")
            return True
            
        except Exception as e:
            print(f"✗ 保存SSH信息失败: {e}")
            return False
    
    def cleanup(self):
        """清理资源（Ubuntu下不终止tmate会话）"""
        print("✓ Python脚本资源清理完成（tmate会话保持运行）")


def signal_handler(signum, frame):
    """信号处理器（适配Ubuntu信号机制）"""
    print("\n收到退出信号，正在清理...")
    if hasattr(signal_handler, 'manager'):
        signal_handler.manager.cleanup()
    sys.exit(0)


def check_ubuntu_version():
    """检查是否为Ubuntu 20.04及以上版本"""
    try:
        # 读取/etc/os-release（Ubuntu标准系统信息文件）
        with open("/etc/os-release", 'r') as f:
            content = f.read()
        
        # 检查是否为Ubuntu
        if "Ubuntu" not in content:
            print("✗ 检测到非Ubuntu系统，本脚本仅支持Ubuntu 20.04及以上版本")
            return False
        
        # 提取版本号（如20.04、22.04）
        for line in content.splitlines():
            if line.startswith("VERSION_ID="):
                version = line.split("=")[1].strip('"')
                major, minor = map(int, version.split("."))
                if (major > 20) or (major == 20 and minor >= 4):
                    print(f"✓ 系统检测通过：Ubuntu {version}")
                    return True
                else:
                    print(f"✗ 检测到Ubuntu {version}，需20.04及以上版本")
                    return False
        
        print("✗ 无法识别Ubuntu版本")
        return False
        
    except Exception as e:
        print(f"✗ 系统版本检测失败: {e}")
        return False


def check_root_permission():
    """检查是否以root权限运行"""
    if os.geteuid() != 0:
        print("✗ 未检测到root权限，本脚本需以root权限运行")
        print("  请使用命令：sudo python3 脚本名.py")
        return False
    print("✓ root权限检测通过")
    return True


def main():
    # 前置检查：系统版本和root权限
    if not check_ubuntu_version():
        return False
    if not check_root_permission():
        return False

    manager = TmateManager()
    
    # 注册信号处理器（Ubuntu下兼容SIGINT/SIGTERM）
    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        signal_handler.manager = manager
    except ValueError:
        print("⚠ 检测到非主线程环境，跳过信号处理器注册")
    
    try:
        print("=== Tmate SSH 会话管理器（Ubuntu专用版） ===")
        
        # 检查并安装依赖（Ubuntu下自动安装requests）
        try:
            import requests
        except ImportError:
            print("检测到未安装requests库，正在通过apt和pip安装...")
            # Ubuntu下先确保pip3可用
            subprocess.check_call(["apt", "update", "-qq"])
            subprocess.check_call(["apt", "install", "-y", "python3-pip", "python3-requests"])
            import requests
            print("✓ requests库安装成功")
        
        # 1. 下载tmate
        if not manager.download_tmate():
            return False
        
        # 2. 启动tmate
        if not manager.start_tmate():
            return False
        
        # 3. 保存SSH信息（移除上传步骤）
        if not manager.save_ssh_info():
            return False
        
        print("\n=== 所有操作完成 ===")
        print("✓ Tmate会话已在后台运行（root权限）")
        print(f"✓ 会话信息已保存到: {manager.ssh_info_path}")
        print("\n🎉 脚本执行完成！")
        print("📍 Tmate会话将继续在后台运行，可以直接使用SSH连接")
        print("📍 如需停止tmate会话，请执行: sudo pkill -f tmate")
        print("📍 查看tmate进程状态: sudo ps aux | grep tmate")
        
        return True
            
    except Exception as e:
        print(f"✗ 程序执行出错: {e}")
        return False
    finally:
        manager.cleanup()
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
