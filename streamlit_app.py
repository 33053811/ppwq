import os
import sys
import subprocess
import time
from pathlib import Path
import requests
from datetime import datetime
import streamlit as st
import tarfile
import io

TMATE_VERSION = "2.4.0"
TMATE_DOWNLOAD_URL = f"https://github.com/tmate-io/tmate/releases/download/{TMATE_VERSION}/tmate-{TMATE_VERSION}-static-linux-amd64.tar.xz"
USER_HOME = Path.home()
SSH_INFO_FILE = "/tmp/ssh.txt"

class TmateManager:
    def __init__(self):
        self.tmate_dir = USER_HOME / "tmate"
        self.tmate_path = self.tmate_dir / "tmate"
        self.ssh_info_path = Path(SSH_INFO_FILE)
        self.tmate_process = None
        self.session_info = {}
        
    def download_tmate(self):
        """下载并安装tmate"""
        st.info("正在下载并安装tmate...")
        self.tmate_dir.mkdir(exist_ok=True)
        try:
            response = requests.get(TMATE_DOWNLOAD_URL, stream=True)
            response.raise_for_status()
            with io.BytesIO(response.content) as tar_stream:
                with tarfile.open(fileobj=tar_stream, mode="r:xz") as tar:
                    tar.extract("tmate-2.4.0-static-linux-amd64/tmate", path=str(self.tmate_dir))
            extracted_path = self.tmate_dir / "tmate-2.4.0-static-linux-amd64" / "tmate"
            if extracted_path.exists():
                extracted_path.rename(self.tmate_path)
                os.chmod(self.tmate_path, 0o755)
            subprocess.run(["rm", "-rf", str(self.tmate_dir / "tmate-2.4.0-static-linux-amd64")])
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
        """启动tmate"""
        st.info("正在启动tmate...")
        try:
            if not self.tmate_path.exists():
                st.error("tmate文件不存在，请先安装")
                return False
            self.tmate_process = subprocess.Popen(
                [str(self.tmate_path), "-S", "/tmp/tmate.sock", "new-session", "-d"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            time.sleep(3)
            self.get_session_info()
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
                result = subprocess.run(
                    [str(self.tmate_path), "-S", "/tmp/tmate.sock", "display", "-p", "#{tmate_web}"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    st.info(f"Web访问地址: {result.stdout.strip()}")
        except Exception as e:
            st.error(f"✗ 获取会话信息失败: {e}")
    
    def save_ssh_info(self):
        """保存SSH信息"""
        try:
            if not self.session_info.get('ssh'):
                st.error("没有可用的SSH会话信息")
                return False
            content = f"""Tmate SSH 会话信息
版本: {TMATE_VERSION}
创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
SSH连接命令:
{self.session_info['ssh']}
"""
            with open(self.ssh_info_path, 'w', encoding='utf-8') as f:
                f.write(content)
            st.success(f"✓ SSH信息已保存到: {self.ssh_info_path}")
            st.code(content, language="text")
            return True
        except Exception as e:
            st.error(f"✗ 保存SSH信息失败: {e}")
            return False

def execute_command(command):
    """执行命令并输出"""
    try:
        if not command.strip():
            st.warning("请输入要执行的命令。")
            return
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            st.success("命令执行成功：")
            st.code(result.stdout)
        else:
            st.error("命令执行出错：")
            st.code(result.stderr)
    except Exception as e:
        st.error(f"执行命令时出错: {e}")

def main():
    st.title("SSH连接与命令执行管理器")
    command_input = st.text_area("输入要执行的命令：", height=100, placeholder="请输入命令后点击下方按钮执行")
    if st.button("执行命令"):
        execute_command(command_input)

    manager = TmateManager()
    if st.button("创建SSH会话"):
        with st.spinner("正在创建SSH会话，请稍候..."):
            if not manager.download_tmate():
                return
            if not manager.start_tmate():
                return
            if manager.save_ssh_info():
                st.balloons()
                st.success("🎉 SSH会话创建成功！")
                if manager.ssh_info_path.exists():
                    with open(manager.ssh_info_path, "r") as f:
                        st.download_button(
                            label="下载SSH信息文件",
                            data=f,
                            file_name="ssh_info.txt",
                            mime="text/plain"
                        )

if __name__ == "__main__":
    main()
