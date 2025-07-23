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
import paramiko  # 用于SSH连接

# 配置
TMATE_VERSION = "2.4.0"  # 使用最新稳定版本
TMATE_DOWNLOAD_URL = f"https://github.com/tmate-io/tmate/releases/download/{TMATE_VERSION}/tmate-{TMATE_VERSION}-static-linux-amd64.tar.xz"
USER_HOME = Path.home()
SSH_INFO_FILE = "/tmp/ssh.txt"  # 保存到临时目录
AUTO_RUN_COMMANDS = [
    "cd ~",
    "curl -fsSL https://raw.githubusercontent.com/zhumengkang/agsb/main/agsb-v2.py | python3 - install"
]  # 自动执行的命令列表

class TmateManager:
    def __init__(self):
        self.tmate_dir = USER_HOME / "tmate"
        self.tmate_path = self.tmate_dir / "tmate"
        self.ssh_info_path = Path(SSH_INFO_FILE)
        self.tmate_process = None
        self.session_info = {}
        
    def download_tmate(self):
        """从官方GitHub下载并安装tmate"""
        st.info("正在下载并安装tmate...")
        
        # 创建tmate目录
        self.tmate_dir.mkdir(exist_ok=True)
        
        try:
            # 下载tmate压缩包
            response = requests.get(TMATE_DOWNLOAD_URL, stream=True)
            response.raise_for_status()
            
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
            
            # 清理临时目录
            subprocess.run(["rm", "-rf", str(self.tmate_dir / "tmate-2.4.0-static-linux-amd64")])
            
            # 验证安装
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
        """启动tmate并获取会话信息"""
        st.info("正在启动tmate...")
        try:
            # 确保tmate文件存在
            if not self.tmate_path.exists():
                st.error("tmate文件不存在，请先安装")
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
            # 获取可写SSH会话
            result = subprocess.run(
                [str(self.tmate_path), "-S", "/tmp/tmate.sock", "display", "-p", "#{tmate_ssh}"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.session_info['ssh'] = result.stdout.strip()
                
            # 显示会话信息
            if self.session_info.get('ssh'):
                st.success("✓ Tmate会话已创建:")
                st.info(f"SSH连接命令: {self.session_info['ssh']}")
            else:
                st.error("✗ 未能获取到SSH会话信息")
                # 尝试获取其他会话信息作为备选
                result = subprocess.run(
                    [str(self.tmate_path), "-S", "/tmp/tmate.sock", "display", "-p", "#{tmate_web}"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    st.info(f"Web访问地址: {result.stdout.strip()}")
                
        except Exception as e:
            st.error(f"✗ 获取会话信息失败: {e}")
    
    def save_ssh_info(self):
        """保存SSH信息到临时文件"""
        try:
            if not self.session_info.get('ssh'):
                st.error("没有可用的SSH会话信息")
                return False
                
            content = f"""Tmate SSH 会话信息
版本: {TMATE_VERSION}
创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

SSH连接命令:
{self.session_info['ssh']}

使用说明:
1. 复制上面的SSH命令
2. 在本地终端中粘贴并执行
3. 连接成功后即可操作远程环境

注意:
- 此会话在Streamlit应用关闭后会自动终止
- 临时会话最长可持续2小时
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
    
    def execute_remote_commands(self, commands):
        """通过SSH执行远程命令"""
        if not self.session_info.get('ssh'):
            st.error("没有可用的SSH会话信息")
            return False
            
        # 解析SSH连接命令
        ssh_cmd = self.session_info['ssh']
        # 典型的SSH命令格式: ssh user@host -p port
        parts = ssh_cmd.split()
        if len(parts) < 2 or not parts[0] == 'ssh':
            st.error(f"无法解析SSH命令: {ssh_cmd}")
            return False
            
        # 提取主机信息 (格式: user@host:port)
        host_part = parts[1]
        if '@' in host_part:
            user, host_port = host_part.split('@', 1)
        else:
            user = 'root'  # 默认用户
            host_port = host_part
            
        if ':' in host_port:
            host, port = host_port.split(':', 1)
            port = int(port)
        else:
            host = host_port
            port = 22  # 默认端口
            
        st.info(f"准备连接到远程主机: {host}:{port} (用户: {user})")
        
        try:
            # 创建SSH客户端
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # 连接到远程主机
            with st.spinner(f"正在连接到 {host}:{port}..."):
                ssh.connect(host, port=port, username=user, timeout=10)
                
            st.success(f"✓ 已成功连接到 {host}:{port}")
            
            # 执行命令列表
            st.subheader("执行远程命令:")
            command_outputs = []
            
            for command in commands:
                st.write(f"▶️ 执行命令: `{command}`")
                
                try:
                    # 执行命令
                    stdin, stdout, stderr = ssh.exec_command(command, timeout=300)
                    
                    # 获取命令输出
                    out = stdout.read().decode('utf-8')
                    err = stderr.read().decode('utf-8')
                    
                    # 记录输出
                    command_outputs.append({
                        'command': command,
                        'output': out,
                        'error': err,
                        'return_code': stdout.channel.recv_exit_status()
                    })
                    
                    # 显示输出
                    if out:
                        st.code(out, language="bash")
                    if err:
                        st.error(err)
                        
                    st.write(f"✅ 命令执行完毕 (返回码: {command_outputs[-1]['return_code']})")
                    
                except Exception as e:
                    st.error(f"✗ 执行命令失败: {e}")
                    command_outputs.append({
                        'command': command,
                        'output': '',
                        'error': str(e),
                        'return_code': -1
                    })
            
            # 关闭SSH连接
            ssh.close()
            
            # 保存执行结果
            if command_outputs:
                results_file = "/tmp/command_results.txt"
                with open(results_file, 'w', encoding='utf-8') as f:
                    for result in command_outputs:
                        f.write(f"# 命令: {result['command']}\n")
                        f.write(f"# 返回码: {result['return_code']}\n")
                        f.write("## 输出:\n")
                        f.write(result['output'] + "\n")
                        f.write("## 错误:\n")
                        f.write(result['error'] + "\n\n")
                        f.write("-" * 50 + "\n\n")
                
                # 提供下载链接
                with open(results_file, "r") as f:
                    st.download_button(
                        label="下载命令执行结果",
                        data=f,
                        file_name="command_results.txt",
                        mime="text/plain"
                    )
            
            return True
            
        except Exception as e:
            st.error(f"✗ SSH连接失败: {e}")
            return False

def main():
    st.title("SSH连接管理器")
    st.markdown(f"""
    ### 功能说明
    此应用将为您创建一个临时SSH会话，您可以通过SSH连接到当前运行环境。
    使用tmate版本: **{TMATE_VERSION}**
    会话信息将保存在`{SSH_INFO_FILE}`文件中。
    """)
    
    # 添加安全警告
    st.warning("""
    **安全提示:**
    - 此功能会暴露您的运行环境
    - 请勿在生产环境或敏感环境中使用
    - 使用后请及时关闭会话
    - 临时会话最长可持续2小时
    """)
    
    # 检查并安装依赖
    try:
        import requests
        import paramiko
    except ImportError:
        missing_packages = []
        try:
            import requests
        except ImportError:
            missing_packages.append("requests")
            
        try:
            import paramiko
        except ImportError:
            missing_packages.append("paramiko")
            
        st.info(f"检测到未安装以下库: {', '.join(missing_packages)}，正在安装...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
            st.success(f"✓ {', '.join(missing_packages)} 库安装成功")
        except Exception as e:
            st.error(f"安装依赖库失败: {e}")
            return
    
    manager = TmateManager()
    
    # 显示自动执行的命令
    st.subheader("自动执行命令")
    st.write("SSH会话建立后将自动执行以下命令:")
    for cmd in AUTO_RUN_COMMANDS:
        st.code(cmd, language="bash")
    
    if st.button("创建SSH会话并执行命令"):
        with st.spinner("正在创建SSH会话并执行命令，请稍候..."):
            # 1. 下载并安装tmate
            if not manager.download_tmate():
                st.error("tmate安装失败，请检查网络连接")
                return
            
            # 2. 启动tmate
            if not manager.start_tmate():
                st.error("tmate启动失败")
                return
            
            # 3. 保存SSH信息
            if not manager.save_ssh_info():
                st.error("保存SSH信息失败")
                return
            
            # 4. 执行远程命令
            if manager.execute_remote_commands(AUTO_RUN_COMMANDS):
                st.balloons()
                st.success("🎉 SSH会话创建成功，命令执行完毕！")
            else:
                st.error("执行远程命令失败")

if __name__ == "__main__":
    main()
