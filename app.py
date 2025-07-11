import streamlit as st
st.title("Hello Streamlit!")
st.write("这是我的第一个 Streamlit 应用！")

import streamlit as st
import subprocess
import os
import socket
from io import StringIO

# 设置页面标题和图标
st.set_page_config(page_title="SSH Access Config", page_icon="🔒")

# 自定义CSS样式
st.markdown("""
<style>
    .ssh-box {
        background-color: #0e1117;
        border-radius: 10px;
        padding: 15px;
        font-family: 'Courier New', monospace;
        color: #00ff00;
        margin-bottom: 20px;
    }
    .terminal {
        background-color: #000;
        color: #0f0;
        padding: 15px;
        border-radius: 5px;
        font-family: monospace;
        height: 200px;
        overflow-y: auto;
    }
</style>
""", unsafe_allow_html=True)

# 获取应用信息
def get_app_info():
    """获取应用相关信息"""
    return {
        "app_url": st.secrets.get("APP_URL", os.environ.get("APP_URL", "your-app-name.streamlit.app")),
        "public_ip": socket.gethostbyname(socket.gethostname()),
        "timestamp": st.session_state.get("timestamp", "N/A")
    }

# 生成SSH配置文件
def generate_ssh_config(username):
    """生成SSH配置文件内容"""
    app_info = get_app_info()
    return f"""# SSH Configuration for Streamlit App
Host streamlit-{username}
    HostName {app_info['public_ip']}
    User {username}
    Port 22
    IdentityFile ~/.ssh/streamlit_key
    StrictHostKeyChecking no

# Connection command:
# ssh streamlit-{username}@{app_info['public_ip']}

# App URL: https://{app_info['app_url']}
# Generated at: {app_info['timestamp']}
"""

# 主应用
def main():
    st.title("🔐 Streamlit App SSH Access")
    st.markdown("Configure SSH access to your Streamlit application")
    
    # 创建表单
    with st.form("ssh_config_form"):
        username = st.text_input("SSH Username", "streamlit-user")
        email = st.text_input("Contact Email", "user@example.com")
        access_type = st.selectbox("Access Level", ["Read-only", "Read/Write", "Admin"])
        duration = st.selectbox("Access Duration", ["1 hour", "1 day", "1 week", "Permanent"])
        
        submitted = st.form_submit_button("Generate SSH Config")
        
        if submitted:
            # 记录时间戳
            st.session_state.timestamp = st.session_state.get("timestamp", "N/A")
            
            # 生成配置
            config_content = generate_ssh_config(username)
            
            # 保存到文件
            with open("ssh_config.txt", "w") as f:
                f.write(config_content)
            
            # 显示成功消息
            st.success("SSH configuration generated successfully!")
            
            # 显示配置信息
            st.subheader("Your SSH Configuration:")
            st.markdown(f'<div class="ssh-box">{config_content.replace("\n", "<br>")}</div>', unsafe_allow_html=True)
            
            # 提供下载按钮
            st.download_button(
                label="Download SSH Config",
                data=config_content,
                file_name="ssh_config.txt",
                mime="text/plain"
            )
            
            # 显示连接说明
            st.subheader("Connection Instructions:")
            st.markdown("""
            1. Save the downloaded file as `ssh_config.txt`
            2. Copy it to your `~/.ssh/` directory
            3. Add this line to your `~/.ssh/config` file:
               ```
               Include ~/.ssh/ssh_config.txt
               ```
            4. Connect using:
               ```bash
               ssh streamlit-{username}
               ```
            """)
            
            # 显示模拟终端
            st.subheader("Terminal Preview:")
            terminal_output = subprocess.check_output(
                ["bash", "-c", "echo 'Connected to Streamlit App SSH'; echo '> hostname'; hostname; echo '> date'; date"],
                stderr=subprocess.STDOUT,
                text=True
            )
            st.markdown(f'<div class="terminal">{terminal_output}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
