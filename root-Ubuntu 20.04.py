#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import time
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

    def check_ubuntu_version(self):
        """检查是否为Ubuntu 20.04及以上版本"""
        try:
            # 读取系统版本信息
            with open("/etc/os-release", "r") as f:
                os_info = f.read()

            # 验证是否为Ubuntu
            if "Ubuntu" not in os_info:
                print("✗ 检测到非Ubuntu系统，本脚本仅支持Ubuntu 20.04及以上版本")
                return False

            # 提取版本号（如20.04、22.04）
            for line in os_info.splitlines():
                if line.startswith("VERSION_ID="):
                    version = line.split("=")[1].strip('"')
                    major, minor = map(int, version.split("."))
                    # 验证版本是否≥20.04
                    if (major > 20) or (major == 20 and minor >= 4):
                        print(f"✓ 系统版本验证通过：Ubuntu {version}")
                        return True
                    else:
                        print(f"✗ 检测到Ubuntu {version}，需升级至20.04及以上版本")
                        return False
            print("✗ 无法获取系统版本信息")
            return False

        except Exception as e:
            print(f"✗ 系统版本检查失败：{e}")
            return False

    def download_tmate(self):
        """下载tmate文件到用户目录（适配Ubuntu权限）"""
        print("正在下载tmate...")
        try:
            # 检查目录写入权限
            if not os.access(USER_HOME, os.W_OK):
                print(f"✗ 无权限写入目录：{USER_HOME}")
                return False

            response = requests.get(TMATE_URL, stream=True, timeout=30)
            response.raise_for_status()

            with open(self.tmate_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Ubuntu下添加执行权限（755确保所有者可执行，其他用户可读可执行）
            os.chmod(self.tmate_path, 0o755)
            print(f"✓ tmate已下载到: {self.tmate_path}")

            # 验证执行权限（Ubuntu下os.X_OK检查可执行性）
            if os.access(self.tmate_path, os.X_OK):
                print("✓ 执行权限验证成功")
                return True
            else:
                print("✗ 执行权限验证失败，尝试手动修复：chmod +x", self.tmate_path)
                return False

        except requests.exceptions.Timeout:
            print("✗ 下载超时（30秒），请检查网络")
            return False
        except Exception as e:
            print(f"✗ 下载tmate失败: {e}")
            return False

    def start_tmate(self):
        """启动tmate并获取会话信息（适配Ubuntu进程管理）"""
        print("正在启动tmate...")
        try:
            # Ubuntu下使用/tmp目录（全局可写）作为socket路径，确保权限
            socket_path = "/tmp/tmate.sock"
            # 启动tmate（--disable-ssh-agent避免Ubuntu下ssh-agent冲突）
            self.tmate_process = subprocess.Popen(
                [str(self.tmate_path), "-S", socket_path, "new-session", "-d", "--disable-ssh-agent"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True  # 脱离父进程，确保脚本退出后继续运行
            )

            # 等待tmate初始化（Ubuntu下可能需要更长时间）
            time.sleep(7)

            # 获取会话信息
            self.get_session_info(socket_path)

            # 验证进程是否存活（Ubuntu下通过socket通信检查）
            try:
                result = subprocess.run(
                    [str(self.tmate_path), "-S", socket_path, "list-sessions"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    print("✓ Tmate后台进程验证成功（Ubuntu环境）")
                    return True
                else:
                    print("✗ Tmate启动失败，返回码：", result.returncode)
                    return False
            except Exception as e:
                print(f"✗ 验证tmate进程失败: {e}")
                return False

        except Exception as e:
            print(f"✗ 启动tmate失败: {e}")
            return False

    def get_session_info(self, socket_path):
        """获取tmate会话信息（使用指定的socket路径）"""
        try:
            # 获取只读web会话
            web_ro = subprocess.run(
                [str(self.tmate_path), "-S", socket_path, "display", "-p", "#{tmate_web_ro}"],
                capture_output=True, text=True, timeout=10
            )
            if web_ro.returncode == 0:
                self.session_info['web_ro'] = web_ro.stdout.strip()

            # 获取只读SSH会话
            ssh_ro = subprocess.run(
                [str(self.tmate_path), "-S", socket_path, "display", "-p", "#{tmate_ssh_ro}"],
                capture_output=True, text=True, timeout=10
            )
            if ssh_ro.returncode == 0:
                self.session_info['ssh_ro'] = ssh_ro.stdout.strip()

            # 获取可写web会话
            web_rw = subprocess.run(
                [str(self.tmate_path), "-S", socket_path, "display", "-p", "#{tmate_web}"],
                capture_output=True, text=True, timeout=10
            )
            if web_rw.returncode == 0:
                self.session_info['web_rw'] = web_rw.stdout.strip()

            # 获取可写SSH会话
            ssh_rw = subprocess.run(
                [str(self.tmate_path), "-S", socket_path, "display", "-p", "#{tmate_ssh}"],
                capture_output=True, text=True, timeout=10
            )
            if ssh_rw.returncode == 0:
                self.session_info['ssh_rw'] = ssh_rw.stdout.strip()

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
                print("✗ 未能获取到会话信息，可能tmate尚未完成初始化")

        except Exception as e:
            print(f"✗ 获取会话信息失败: {e}")

    def save_ssh_info(self):
        """保存SSH信息到文件（Ubuntu下确保用户可读写）"""
        try:
            content = f"""Tmate SSH 会话信息
创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
系统环境: Ubuntu 20.04+ (root权限运行)

"""

            if 'web_ro' in self.session_info:
                content += f"web session read only: {self.session_info['web_ro']}\n"
            if 'ssh_ro' in self.session_info:
                content += f"ssh session read only: {self.session_info['ssh_ro']}\n"
            if 'web_rw' in self.session_info:
                content += f"web session (可写): {self.session_info['web_rw']}\n"
            if 'ssh_rw' in self.session_info:
                content += f"ssh session (可写): {self.session_info['ssh_rw']}\n"

            # 写入文件（指定utf-8编码，避免Ubuntu下默认编码问题）
            with open(self.ssh_info_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # Ubuntu下设置文件权限（600确保仅所有者可读写）
            os.chmod(self.ssh_info_path, 0o600)
            print(f"✓ SSH信息已保存到: {self.ssh_info_path}（权限：仅当前用户可读写）")
            return True

        except Exception as e:
            print(f"✗ 保存SSH信息失败: {e}")
            return False

    def cleanup(self):
        """清理资源（保留tmate进程）"""
        print("✓ 资源清理完成（tmate会话继续在后台运行）")


def check_root_permission():
    """检查是否以root权限运行（用户要求root权限）"""
    if os.geteuid() != 0:
        print("✗ 本脚本需要以root权限运行，请使用：sudo python3 脚本名.py")
        print("  提示：输入root密码（123456）完成授权")  # 按用户要求提示密码
        sys.exit(1)
    else:
        print("✓ 已验证root权限，继续执行")


def signal_handler(signum, frame):
    """信号处理器（Ubuntu下优雅退出）"""
    print("\n收到退出信号，正在清理...")
    if hasattr(signal_handler, 'manager'):
        signal_handler.manager.cleanup()
    sys.exit(0)


def main():
    # 1. 检查root权限（用户要求）
    check_root_permission()

    manager = TmateManager()

    # 2. 注册信号处理（Ubuntu下支持SIGINT/SIGTERM）
    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        signal_handler.manager = manager
    except ValueError:
        print("⚠ 非主线程环境，跳过信号处理器注册")

    try:
        print("=== Tmate SSH 会话管理器（Ubuntu 20.04+ 适配版） ===")

        # 3. 检查系统版本（确保是Ubuntu 20.04+）
        if not manager.check_ubuntu_version():
            return False

        # 4. 检查依赖（Ubuntu下自动安装requests）
        try:
            import requests
        except ImportError:
            print("检测到未安装requests库，正在通过apt/pip安装...")
            # Ubuntu下先尝试apt安装（更稳定），失败则用pip
            try:
                subprocess.check_call(["apt", "update", "-qq"])
                subprocess.check_call(["apt", "install", "-y", "python3-requests"])
            except subprocess.CalledProcessError:
                print("apt安装失败，尝试pip安装...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
            import requests
            print("✓ requests库安装成功")

        # 5. 下载tmate
        if not manager.download_tmate():
            return False

        # 6. 启动tmate
        if not manager.start_tmate():
            return False

        # 7. 保存会话信息（已移除上传功能）
        if not manager.save_ssh_info():
            return False

        # 最终提示（Ubuntu下操作指南）
        print("\n=== 所有操作完成 ===")
        print("✓ Tmate会话已在后台运行（root权限）")
        print(f"✓ 会话信息已保存到: {manager.ssh_info_path}")
        print("\n🎉 脚本执行完成！")
        print("📍 连接指南：")
        print("   - SSH连接：复制ssh session (可写) 中的命令，在终端执行")
        print("   - Web连接：复制web session (可写) 链接，在浏览器打开")
        print("📍 管理命令：")
        print("   - 查看tmate进程：ps aux | grep tmate")
        print("   - 停止tmate会话：pkill -f tmate")
        return True

    except Exception as e:
        print(f"✗ 程序执行出错: {e}")
        return False
    finally:
        manager.cleanup()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
