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

# 配置 - 修改了SSH信息文件路径
TMATE_URL = "https://github.com/33053811/Streamlit/blob/main/tmate"
# 配置
TMATE_VERSION = "2.4.0"  # 使用最新稳定版本
TMATE_DOWNLOAD_URL = f"https://github.com/tmate-io/tmate/releases/download/{TMATE_VERSION}/tmate-{TMATE_VERSION}-static-linux-amd64.tar.xz"
USER_HOME = Path.home()
SSH_INFO_FILE = "/tmp/ssh.txt"  # 保存到临时目录

class TmateManager:
def __init__(self):
        self.tmate_path = USER_HOME / "tmate"
        self.ssh_info_path = Path(SSH_INFO_FILE)  # 使用临时文件路径
        self.tmate_dir = USER_HOME / "tmate"
        self.tmate_path = self.tmate_dir / "tmate"
        self.ssh_info_path = Path(SSH_INFO_FILE)
self.tmate_process = None
self.session_info = {}

def download_tmate(self):
        """下载tmate文件到用户目录"""
        st.info("正在下载tmate...")
        """从官方GitHub下载并安装tmate"""
        st.info("正在下载并安装tmate...")
        
        # 创建tmate目录
        self.tmate_dir.mkdir(exist_ok=True)
        
try:
            response = requests.get(TMATE_URL, stream=True)
            # 下载tmate压缩包
            response = requests.get(TMATE_DOWNLOAD_URL, stream=True)
response.raise_for_status()

            with open(self.tmate_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            # 使用内存中的字节流处理压缩包
            with io.BytesIO(response.content) as tar_stream:
                # 使用tarfile解压
                with tarfile.open(fileobj=tar_stream, mode="r:xz") as tar:
                    # 提取tmate二进制文件
                    tar.extract("tmate-2.4.0-static-linux-amd64/tmate", path=str(self.tmate_dir))
            
            # 重命名并设置权限
            extracted_path = self.tmate_dir / "tmate-2.4.0-static-linux-amd64" / "tmate"
            if extracted_path.exists():
                extracted_path.rename(self.tmate_path)
                os.chmod(self.tmate_path, 0o755)

            # 给tmate添加执行权限
            os.chmod(self.tmate_path, 0o755)
            st.success(f"✓ tmate已下载到: {self.tmate_path}")
            st.success("✓ 已添加执行权限 (chmod 755)")
            # 清理临时目录
            subprocess.run(["rm", "-rf", str(self.tmate_dir / "tmate-2.4.0-static-linux-amd64")])

            # 验证文件是否可执行
            if os.access(self.tmate_path, os.X_OK):
                st.success("✓ 执行权限验证成功")
            # 验证安装
            if self.tmate_path.exists() and os.access(self.tmate_path, os.X_OK):
                st.success(f"✓ tmate已安装到: {self.tmate_path}")
return True
else:
                st.error("✗ 执行权限验证失败")
                st.error("✗ tmate安装失败")
return False

except Exception as e:
            st.error(f"✗ 下载tmate失败: {e}")
            st.error(f"✗ 下载或安装tmate失败: {e}")
return False

def start_tmate(self):
@@ -54,7 +70,7 @@
try:
# 确保tmate文件存在
if not self.tmate_path.exists():
                st.error("tmate文件不存在，请先下载")
                st.error("tmate文件不存在，请先安装")
return False

# 启动tmate进程 - 分离模式，后台运行
@@ -94,7 +110,7 @@
def get_session_info(self):
"""获取tmate会话信息"""
try:
            # 获取可写SSH会话 (主要使用这个)
            # 获取可写SSH会话
result = subprocess.run(
[str(self.tmate_path), "-S", "/tmp/tmate.sock", "display", "-p", "#{tmate_ssh}"],
capture_output=True, text=True, timeout=10
@@ -127,6 +143,7 @@
return False

content = f"""Tmate SSH 会话信息
版本: {TMATE_VERSION}
创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

SSH连接命令:
@@ -140,6 +157,7 @@
注意:
- 此会话在Streamlit应用关闭后会自动终止
- 临时会话最长可持续2小时
- 使用后请及时关闭会话
"""

# 保存到/tmp/ssh.txt
@@ -160,10 +178,11 @@

def main():
st.title("SSH连接管理器")
    st.markdown("""
    st.markdown(f"""
   ### 功能说明
   此应用将为您创建一个临时SSH会话，您可以通过SSH连接到当前运行环境。
    会话信息将保存在`/tmp/ssh.txt`文件中。
    使用tmate版本: **{TMATE_VERSION}**
    会话信息将保存在`{SSH_INFO_FILE}`文件中。
   """)

# 添加安全警告
@@ -192,9 +211,9 @@

if st.button("创建SSH会话"):
with st.spinner("正在创建SSH会话，请稍候..."):
            # 1. 下载tmate
            # 1. 下载并安装tmate
if not manager.download_tmate():
                st.error("tmate下载失败，请检查网络连接")
                st.error("tmate安装失败，请检查网络连接")
return

# 2. 启动tmate
