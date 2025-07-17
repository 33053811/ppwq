import os
import subprocess
import getpass
from datetime import datetime

# 颜色输出（终端可用）
class Color:
    GREEN = '\033[0;32m'
    YELLOW = '\033[0;33m'
    RED = '\033[0;31m'
    NC = '\033[0m'  # 重置颜色

def run_command(cmd, sudo=False, capture_output=False):
    """执行系统命令"""
    try:
        if sudo:
            cmd = ["sudo"] + cmd
        if capture_output:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return result
        else:
            subprocess.run(cmd, check=True)
            return True
    except subprocess.CalledProcessError as e:
        print(f"{Color.RED}[ERROR] 命令执行失败: {' '.join(cmd)}{Color.NC}")
        print(f"错误信息: {e.stderr}")
        return False
    except Exception as e:
        print(f"{Color.RED}[ERROR] 执行命令时出错: {e}{Color.NC}")
        return False

def main():
    print(f"{Color.GREEN}===== Ubuntu 20.04+ SSH与tmux一键配置 =====")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Color.NC}")

    # 1. 检查是否为root权限
    if os.geteuid() != 0:
        print(f"{Color.RED}[ERROR] 请用root权限运行（例如：sudo python3 脚本名.py）{Color.NC}")
        return

    # 2. 更新系统包
    print(f"\n{Color.GREEN}[1/5] 更新系统包列表...{Color.NC}")
    if not run_command(["apt", "update", "-y"], sudo=True):
        return

    # 3. 安装OpenSSH服务器
    print(f"\n{Color.GREEN}[2/5] 安装OpenSSH服务器...{Color.NC}")
    if not run_command(["apt", "install", "openssh-server", "-y"], sudo=True):
        return

    # 4. 配置SSH服务（允许密码登录）
    print(f"\n{Color.GREEN}[3/5] 配置SSH服务...{Color.NC}")
    ssh_config = "/etc/ssh/sshd_config"
    # 修改配置（启用密码登录和root登录，适合临时环境）
    run_command(["sed", "-i", "s/#PasswordAuthentication yes/PasswordAuthentication yes/g", ssh_config], sudo=True)
    run_command(["sed", "-i", "s/#PermitRootLogin prohibit-password/PermitRootLogin yes/g", ssh_config], sudo=True)
    # 重启SSH服务
    if not run_command(["systemctl", "restart", "ssh"], sudo=True):
        return

    # 5. 安装tmux
    print(f"\n{Color.GREEN}[4/5] 安装tmux...{Color.NC}")
    if not run_command(["apt", "install", "tmux", "-y"], sudo=True):
        return

    # 6. 创建tmux会话（用原登录用户，避免root权限）
    print(f"\n{Color.GREEN}[5/5] 创建tmux会话...{Color.NC}")
    original_user = os.environ.get("SUDO_USER", getpass.getuser())
    # 用普通用户权限创建tmux会话（避免root会话）
    if not run_command(["su", "-", original_user, "-c", "tmux new-session -d -s ssh_session"], sudo=True):
        print(f"{Color.YELLOW}[警告] tmux会话可能已存在，忽略创建{Color.NC}")

    # 获取连接信息
    # 获取公网IP（优先）
    public_ip = subprocess.run(
        ["curl", "-s", "ifconfig.me"],
        stdout=subprocess.PIPE, text=True
    ).stdout.strip()
    # 公网IP获取失败则用内网IP
    if not public_ip:
        public_ip = subprocess.run(
            ["hostname", "-I"],
            stdout=subprocess.PIPE, text=True
        ).stdout.split()[0]

    # 生成SSH信息文件
    ssh_info_file = "/tmp/ssh.txt"
    with open(ssh_info_file, "w") as f:
        f.write(f"""Ubuntu 20.04+ SSH连接信息
=================================

1. SSH连接命令:
ssh {original_user}@{public_ip}

2. 连接后附加到tmux会话:
tmux attach-session -t ssh_session

3. 断开会话但保持运行:
按 Ctrl+b 然后按 d

4. 关闭会话:
在tmux中执行: exit

系统信息:
- 用户名: {original_user}
- 服务器IP: {public_ip}
- tmux会话名: ssh_session
- 创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""")

    # 显示结果
    print(f"\n{Color.GREEN}===== 配置完成 ====={Color.NC}")
    print(f"连接信息已保存到: {ssh_info_file}")
    print("\n连接步骤:")
    print(f"1. 本地终端执行: {Color.GREEN}ssh {original_user}@{public_ip}{Color.NC}")
    print(f"2. 连接后执行: {Color.GREEN}tmux attach-session -t ssh_session{Color.NC}")

if __name__ == "__main__":
    main()
