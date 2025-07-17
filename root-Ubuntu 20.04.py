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

# 配置（适配 Ubuntu 20.04+）
TMATE_URL = "https://github.com/zhumengkang/agsb/raw/main/tmate"
USER_HOME = Path.home()
SSH_INFO_FILE = "ssh.txt"  # 会话信息保存文件名
# 移除 UPLOAD_API 相关配置（已删除上传功能）


class TmateManager:
    def __init__(self):
        self.tmate_path = USER_HOME / "tmate"
        self.ssh_info_path = USER_HOME / SSH_INFO_FILE
        self.tmate_process = None
        self.session_info = {}
        # Ubuntu 系统依赖检查列表
        self.ubuntu_deps = ["libssl1.1", "libevent-2.1-7", "libtinfo5"]  # Ubuntu 20.04+ 必要依赖

    def check_root_permission(self):
        """检查是否以 root 权限运行"""
        if os.geteuid() != 0:
            print("✗ 请以 root 权限运行此脚本（使用 sudo 或直接登录 root）")
            print("  示例：sudo python3 script.py")
            return False
        print("✓ root 权限验证通过")
        return True

    def check_ubuntu_deps(self):
        """检查并安装 Ubuntu 必要依赖"""
        print("正在检查 Ubuntu 系统依赖...")
        try:
            # 检查系统是否为 Ubuntu 20.04+
            with open("/etc/os-release", "r") as f:
                os_info = f.read()
            if "Ubuntu" not in os_info:
                print("✗ 此脚本仅支持 Ubuntu 系统")
                return False
            if "20.04" not in os_info and "22.04" not in os_info and "24.04" not in os_info:
                print("✗ 推荐使用 Ubuntu 20.04、22.04 或 24.04 版本")
                return False

            # 检查依赖是否已安装
            missing_deps = []
            for dep in self.ubuntu_deps:
                result = subprocess.run(
                    ["dpkg", "-s", dep],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                if result.returncode != 0:
                    missing_deps.append(dep)

            # 安装缺失的依赖
            if missing_deps:
                print(f"检测到缺失依赖：{missing_deps}，正在自动安装...")
                # 使用 apt 安装依赖（需要 root 权限）
                install_result = subprocess.run(
                    ["apt", "update", "-y"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                if install_result.returncode != 0:
                    print("✗ apt 更新失败，无法安装依赖")
                    return False

                install_result = subprocess.run(
                    ["apt", "install", "-y"] + missing_deps,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                if install_result.returncode != 0:
                    print(f"✗ 安装依赖 {missing_deps} 失败")
                    return False
                print(f"✓ 依赖 {missing_deps} 安装完成")

            print("✓ Ubuntu 系统依赖检查通过")
            return True

        except Exception as e:
            print(f"✗ 依赖检查失败：{e}")
            return False

    def download_tmate(self):
        """下载 tmate 到用户目录（适配 Ubuntu 可执行权限）"""
        print("正在下载 tmate 程序...")
        try:
            # 检查本地是否已存在 tmate（避免重复下载）
            if self.tmate_path.exists() and os.access(self.tmate_path, os.X_OK):
                print(f"✓ tmate 已存在（{self.tmate_path}），跳过下载")
                return True

            # 下载 tmate
            response = requests.get(TMATE_URL, stream=True, timeout=30)
            response.raise_for_status()

            with open(self.tmate_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Ubuntu 下设置可执行权限（root 权限下确保权限生效）
            os.chmod(self.tmate_path, 0o755)
            print(f"✓ tmate 已下载到：{self.tmate_path}")

            # 验证执行权限（Ubuntu 下严格检查）
            if os.access(self.tmate_path, os.X_OK):
                print("✓ tmate 执行权限验证成功")
                return True
            else:
                print("✗ tmate 执行权限验证失败（可能是文件系统权限限制）")
                return False

        except Exception as e:
            print(f"✗ 下载 tmate 失败：{e}")
            return False

    def start_tmate(self):
        """启动 tmate 并验证进程（适配 Ubuntu 进程管理）"""
        print("正在启动 tmate 会话...")
        try:
            # 清理旧的 tmate 套接字（避免残留文件影响）
            if os.path.exists("/tmp/tmate.sock"):
                os.remove("/tmp/tmate.sock")
                print("✓ 清理旧 tmate 套接字文件")

            # 启动 tmate（Ubuntu 下使用独立进程组）
            self.tmate_process = subprocess.Popen(
                [str(self.tmate_path), "-S", "/tmp/tmate.sock", "new-session", "-d"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True  # Ubuntu 下确保进程后台运行
            )

            # 等待 tmate 初始化（Ubuntu 下可能需要更长时间）
            time.sleep(8)

            # 获取会话信息
            self.get_session_info()

            # 验证 tmate 进程是否存活（Ubuntu 下进程检查）
            try:
                result = subprocess.run(
                    [str(self.tmate_path), "-S", "/tmp/tmate.sock", "list-sessions"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and "tmate" in result.stdout:
                    print("✓ tmate 后台进程启动成功（Ubuntu 环境验证通过）")
                    return True
                else:
                    print(f"✗ tmate 进程启动失败（返回码：{result.returncode}）")
                    return False
            except Exception as e:
                print(f"✗ 验证 tmate 进程失败：{e}")
                return False

        except Exception as e:
            print(f"✗ 启动 tmate 失败：{e}")
            return False

    def get_session_info(self):
        """获取 tmate 会话信息（Ubuntu 下适配命令输出）"""
        try:
            # 获取 4 类会话信息（Ubuntu 下 tmate 命令输出格式适配）
            info_types = {
                'web_ro': "#{tmate_web_ro}",    # 只读 Web 会话
                'ssh_ro': "#{tmate_ssh_ro}",    # 只读 SSH 会话
                'web_rw': "#{tmate_web}",       # 可写 Web 会话
                'ssh_rw': "#{tmate_ssh}"        # 可写 SSH 会话
            }

            for key, format_str in info_types.items():
                result = subprocess.run(
                    [str(self.tmate_path), "-S", "/tmp/tmate.sock", "display", "-p", format_str],
                    capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0 and result.stdout.strip():
                    self.session_info[key] = result.stdout.strip()

            # 显示获取到的信息
            if self.session_info:
                print("\n✓ 获取到 tmate 会话信息：")
                for key, value in self.session_info.items():
                    print(f"  {key.replace('_', ' ')}: {value}")
            else:
                print("✗ 未获取到任何会话信息（可能是 tmate 服务器连接失败）")

        except Exception as e:
            print(f"✗ 获取会话信息失败：{e}")

    def save_ssh_info(self):
        """保存会话信息到本地文件（Ubuntu 下确保路径可写）"""
        try:
            # 构建保存内容（包含时间戳）
            content = f"""Tmate SSH 会话信息（Ubuntu 系统）
创建时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
运行用户：root（已验证 root 权限）

"""
            # 添加会话信息
            info_mapping = {
                'web_ro': "只读 Web 会话",
                'ssh_ro': "只读 SSH 会话",
                'web_rw': "可写 Web 会话",
                'ssh_rw': "可写 SSH 会话"
            }
            for key, label in info_mapping.items():
                if key in self.session_info:
                    content += f"{label}：{self.session_info[key]}\n"

            # 写入文件（Ubuntu 下用户目录权限适配）
            with open(self.ssh_info_path, 'w', encoding='utf-8') as f:
                f.write(content)

            print(f"\n✓ 会话信息已保存到：{self.ssh_info_path}")
            return True

        except Exception as e:
            print(f"✗ 保存会话信息失败：{e}")
            return False

    def cleanup(self):
        """清理脚本资源（保留 tmate 后台进程）"""
        print("\n✓ 脚本资源清理完成（tmate 会话将继续在后台运行）")


def signal_handler(signum, frame):
    """信号处理（Ubuntu 下优雅退出）"""
    print("\n收到退出信号，正在清理资源...")
    if hasattr(signal_handler, 'manager'):
        signal_handler.manager.cleanup()
    sys.exit(0)


def main():
    manager = TmateManager()

    # 注册信号处理（Ubuntu 下支持 Ctrl+C 退出）
    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        signal_handler.manager = manager
    except ValueError:
        print("⚠ 非主线程环境，跳过信号注册（不影响核心功能）")

    try:
        print("=== Ubuntu 专用 Tmate 会话管理器 ===")

        # 1. 检查 root 权限（核心前置条件）
        if not manager.check_root_permission():
            return False

        # 2. 检查 Ubuntu 系统依赖
        if not manager.check_ubuntu_deps():
            return False

        # 3. 检查并安装 requests（依赖）
        try:
            import requests
        except ImportError:
            print("检测到缺失 requests 库，正在安装...")
            install_result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "requests"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if install_result.returncode != 0:
                print("✗ 安装 requests 失败（请手动执行：pip install requests）")
                return False
            import requests
            print("✓ requests 库安装成功")

        # 4. 下载 tmate
        if not manager.download_tmate():
            return False

        # 5. 启动 tmate 并获取会话
        if not manager.start_tmate():
            return False

        # 6. 保存会话信息到本地（已移除上传功能）
        if not manager.save_ssh_info():
            return False

        # 最终提示（适配 Ubuntu 操作习惯）
        print("\n=== 所有操作完成 ===")
        print("✓ tmate 会话已在后台运行（root 权限下稳定运行）")
        print(f"✓ 会话信息已保存到：{manager.ssh_info_path}")
        print("\n操作提示：")
        print("  1. 使用 SSH 连接：复制 '可写 SSH 会话' 地址，执行 ssh 命令")
        print("  2. 查看 tmate 进程：ps -aux | grep tmate")
        print("  3. 停止会话：pkill -f tmate（注意：会终止所有 tmate 进程）")
        print("  4. 重新获取信息：运行此脚本即可（不会重复下载）")
        print("\n🎉 脚本执行完成！")
        return True

    except Exception as e:
        print(f"✗ 程序执行出错：{e}")
        return False
    finally:
        manager.cleanup()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
