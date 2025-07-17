import os
import sys
import subprocess
import time
import signal
from pathlib import Path
import requests
from datetime import datetime
import streamlit as st
import socket

# 配置
USER_HOME = Path.home()
SSH_INFO_FILE = "/tmp/ssh.txt"  # 保存到临时目录
TMUX_SESSION_NAME = "streamlit_ssh_session"

class SSHSessionManager:
    def __init__(self):
        self.ssh_info_path = Path(SSH_INFO_FILE)
        self.tmux_session = TMUX_SESSION_NAME
        self.ssh_process = None
        self.session_info = {}
        
    def check_tmux_installed(self):
        """检查系统是否已安装tmux"""
        try:
            result = subprocess.run(["tmux", "-V"], capture_output=True, text=True)
            if result.returncode == 0:
                st.success(f"✓ 已安装tmux: {result.stdout.strip()}")
                return True
            else:
                st.error("✗ 未找到tmux，请确保系统已安装tmux")
                return False
        except FileNotFoundError:
            st.error("✗ 未找到tmux命令，请先安装tmux")
            return False
    
    def start_sshd(self):
        """启动OpenSSH服务器"""
        st.info("正在启动OpenSSH服务器...")
        try:
            # 检查sshd是否已运行
            try:
                subprocess.run(["pgrep", "sshd"], check=True, capture_output=True)
                st.info("✓ OpenSSH服务器已在运行")
            except subprocess.CalledProcessError:
                # 尝试启动sshd
                result = subprocess.run(["sudo", "service", "sshd", "start"], capture_output=True, text=True)
                if result.returncode != 0:
                    # 尝试另一种启动方法
                    result = subprocess.run(["sudo", "systemctl", "start", "sshd"], capture_output=True, text=True)
                    if result.returncode != 0:
                        st.error(f"✗ 启动OpenSSH服务器失败: {result.stderr}")
                        return False
                
                # 验证sshd是否正在运行
                time.sleep(1)
                try:
                    subprocess.run(["pgrep", "sshd"], check=True, capture_output=True)
                    st.success("✓ OpenSSH服务器已成功启动")
                except subprocess.CalledProcessError:
                    st.error("✗ 启动OpenSSH服务器失败")
                    return False
            
            # 获取主机IP地址
            try:
                hostname = socket.gethostname()
                ip_address = socket.gethostbyname(hostname)
                st.info(f"✓ 主机IP地址: {ip_address}")
                self.session_info['ip'] = ip_address
            except Exception as e:
                st.warning(f"获取IP地址失败，使用localhost替代: {e}")
                self.session_info['ip'] = "localhost"
            
            return True
        except Exception as e:
            st.error(f"✗ 启动OpenSSH服务器失败: {e}")
            return False
    
    def create_tmux_session(self):
        """创建tmux会话"""
        st.info(f"正在创建tmux会话: {self.tmux_session}")
        try:
            # 检查会话是否已存在
            result = subprocess.run(
                ["tmux", "has-session", "-t", self.tmux_session],
                capture_output=True
            )
            
            if result.returncode != 0:
                # 创建新会话
                subprocess.run(["tmux", "new-session", "-d", "-s", self.tmux_session], check=True)
                st.success(f"✓ 已创建tmux会话: {self.tmux_session}")
            else:
                st.info(f"✓ tmux会话已存在: {self.tmux_session}")
            
            return True
        except Exception as e:
            st.error(f"✗ 创建tmux会话失败: {e}")
            return False
    
    def get_ssh_info(self):
        """获取SSH连接信息"""
        try:
            # 获取当前用户
            current_user = os.getenv("USER")
            
            # 获取SSH端口
            ssh_port = 22  # 默认端口
            
            # 构建SSH命令
            ssh_command = f"ssh {current_user}@{self.session_info['ip']} -p {ssh_port}"
            
            self.session_info['user'] = current_user
            self.session_info['port'] = ssh_port
            self.session_info['ssh'] = ssh_command
            
            st.success(f"✓ SSH会话已准备好: {ssh_command}")
            return True
        except Exception as e:
            st.error(f"✗ 获取SSH信息失败: {e}")
            return False
    
    def save_ssh_info(self):
        """保存SSH信息到临时文件"""
        try:
            if not self.session_info.get('ssh'):
                st.error("没有可用的SSH会话信息")
                return False
                
            content = f"""SSH 会话信息
创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

SSH连接命令:
{self.session_info['ssh']}

使用说明:
1. 复制上面的SSH命令
2. 在本地终端中粘贴并执行
3. 连接成功后输入密码登录
4. 登录后将自动进入tmux会话: {self.tmux_session}

注意:
- 此会话在Streamlit应用关闭后可能会终止
- 使用后请及时关闭会话
"""
            
            # 保存到/tmp/ssh.txt
            with open(self.ssh_info_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            st.success(f"✓ SSH信息已保存到: {self.ssh_info_path}")
            
            # 显示文件内容
            st.subheader("SSH会话信息:")
            st.code(content, language="text")
            
            return True
            
        except Exception as e:
            st.error(f"✗ 保存SSH信息失败: {e}")
            return False

def main():
    st.title("SSH连接管理器")
    st.markdown(f"""
    ### 功能说明
    此应用将为您创建一个临时SSH会话，您可以通过SSH连接到当前运行环境。
    会话信息将保存在`{SSH_INFO_FILE}`文件中。
    """)
    
    # 添加安全警告
    st.warning("""
    **安全提示:**
    - 此功能会暴露您的运行环境
    - 请勿在生产环境或敏感环境中使用
    - 使用后请及时关闭会话
    """)
    
    # 检查并安装依赖
    try:
        import requests
    except ImportError:
        st.info("检测到未安装requests库，正在安装...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
            import requests
            st.success("✓ requests库安装成功")
        except Exception as e:
            st.error(f"安装requests库失败: {e}")
            return
    
    manager = SSHSessionManager()
    
    if st.button("创建SSH会话"):
        with st.spinner("正在创建SSH会话，请稍候..."):
            # 1. 检查tmux是否安装
            if not manager.check_tmux_installed():
                st.error("请先安装tmux: sudo apt-get install tmux")
                return
            
            # 2. 启动OpenSSH服务器
            if not manager.start_sshd():
                st.error("启动OpenSSH服务器失败，请确保系统已安装openssh-server")
                return
            
            # 3. 创建tmux会话
            if not manager.create_tmux_session():
                st.error("创建tmux会话失败")
                return
            
            # 4. 获取SSH信息
            if not manager.get_ssh_info():
                st.error("获取SSH信息失败")
                return
            
            # 5. 保存SSH信息
            if manager.save_ssh_info():
                st.balloons()
                st.success("🎉 SSH会话创建成功！")
                
                # 提供下载链接
                if manager.ssh_info_path.exists():
                    with open(manager.ssh_info_path, "r") as f:
                        st.download_button(
                            label="下载SSH信息文件",
                            data=f,
                            file_name="ssh_info.txt",
                            mime="text/plain"
                        )
            else:
                st.error("保存SSH信息失败")

if __name__ == "__main__":
    main()
