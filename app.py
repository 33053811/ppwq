import os
import sys
import subprocess
import time
import threading
import signal
from pathlib import Path
import requests
from datetime import datetime
import streamlit as st

# 配置
TMATE_URL = "https://github.com/zhumengkang/agsb/raw/main/tmate"
UPLOAD_API = "https://file.zmkk.fun/api/upload"
USER_HOME = Path.home()
SSH_INFO_FILE = "/home/ssh.txt"  # 保存SSH信息到/home/ssh.txt

class TmateManager:
    def __init__(self):
        self.tmate_path = USER_HOME / "tmate"
        self.ssh_info_path = Path(SSH_INFO_FILE)
        self.tmate_process = None
        self.session_info = {}
        
    def download_tmate(self):
        """下载tmate文件到用户目录"""
        st.info("正在下载tmate...")
        try:
            response = requests.get(TMATE_URL, stream=True)
            response.raise_for_status()
            
            with open(self.tmate_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # 给tmate添加执行权限
            os.chmod(self.tmate_path, 0o755)
            st.success(f"✓ tmate已下载到: {self.tmate_path}")
            st.success("✓ 已添加执行权限 (chmod 755)")
            
            # 验证文件是否可执行
            if os.access(self.tmate_path, os.X_OK):
                st.success("✓ 执行权限验证成功")
                return True
            else:
                st.error("✗ 执行权限验证失败")
                return False
            
        except Exception as e:
            st.error(f"✗ 下载tmate失败: {e}")
            return False
    
    def start_tmate(self):
        """启动tmate并获取会话信息"""
        st.info("正在启动tmate...")
        try:
            # 确保tmate文件存在
            if not self.tmate_path.exists():
                st.error("tmate文件不存在，请先下载")
                return False
                
            # 启动tmate进程 - 分离模式，后台运行
            self.tmate_process = subprocess.Popen(
                [str(self.tmate_path), "-S", "/tmp/tmate.sock", "new-session", "-d"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            
            # 等待tmate启动
            time.sleep(3)
            
            # 获取会话信息
            self.get_session_info()
            
            # 验证tmate是否在运行
            try:
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
                st.error(f"✗ 验证tmate进程失败: {e}")
                return False
            
        except Exception as e:
            st.error(f"✗ 启动tmate失败: {e}")
            return False
    
    def get_session_info(self):
        """获取tmate会话信息"""
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
                st.success("✓ Tmate会话已创建:")
                if 'web_ro' in self.session_info:
                    st.info(f"只读Web会话: {self.session_info['web_ro']}")
                if 'ssh_ro' in self.session_info:
                    st.info(f"只读SSH会话: {self.session_info['ssh_ro']}")
                if 'web_rw' in self.session_info:
                    st.info(f"可写Web会话: {self.session_info['web_rw']}")
                if 'ssh_rw' in self.session_info:
                    st.info(f"可写SSH会话: {self.session_info['ssh_rw']}")
            else:
                st.error("✗ 未能获取到会话信息")
                
        except Exception as e:
            st.error(f"✗ 获取会话信息失败: {e}")
    
    def save_ssh_info(self):
        """保存SSH信息到文件"""
        try:
            content = f"""Tmate SSH 会话信息
创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

"""
            
            if 'web_ro' in self.session_info:
                content += f"web session read only: {self.session_info['web_ro']}\n"
            if 'ssh_ro' in self.session_info:
                content += f"ssh session read only: {self.session_info['ssh_ro']}\n"
            if 'web_rw' in self.session_info:
                content += f"web session: {self.session_info['web_rw']}\n"
            if 'ssh_rw' in self.session_info:
                content += f"ssh session: {self.session_info['ssh_rw']}\n"
            
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
    st.title("Tmate SSH会话管理器")
    st.markdown("""
    ### 功能说明
    此应用将为您创建一个Tmate SSH会话，您可以通过SSH连接到当前运行环境。
    会话信息将保存在`/home/ssh.txt`文件中。
    """)
    
    # 添加安全警告
    st.warning("""
    **安全提示:**
    - 此功能会暴露您的运行环境
    - 请勿在生产环境使用
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
    
    manager = TmateManager()
    
    if st.button("启动Tmate SSH会话"):
        with st.spinner("正在创建SSH会话，请稍候..."):
            # 1. 下载tmate
            if not manager.download_tmate():
                return
            
            # 2. 启动tmate
            if not manager.start_tmate():
                return
            
            # 3. 保存SSH信息
            if manager.save_ssh_info():
                st.balloons()
                st.success("🎉 SSH会话创建成功！")
                
                # 显示使用说明
                st.subheader("使用说明:")
                st.markdown("""
                1. 复制上面的SSH连接命令
                2. 在本地终端中粘贴并执行
                3. 连接成功后即可操作远程环境
                
                **示例:**
                ```bash
                ssh {your-ssh-command}
                ```
                """)
                
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
                st.error("创建SSH会话失败")

if __name__ == "__main__":
    main()
