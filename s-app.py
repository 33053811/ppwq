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
import json

# 配置
TMATE_VERSION = "2.4.0"  # 使用最新稳定版本
TMATE_DOWNLOAD_URL = f"https://github.com/tmate-io/tmate/releases/download/{TMATE_VERSION}/tmate-{TMATE_VERSION}-static-linux-amd64.tar.xz"
USER_HOME = Path.home()
SSH_INFO_FILE = "/tmp/ssh.txt"  # 保存到临时目录
AGSB_SCRIPT_URL = "https://raw.githubusercontent.com/zhumengkang/agsb/main/agsb-v2.py"
# 添加--yes参数使安装过程静默
AGSB_INSTALL_COMMAND = f"cd ~ && curl -fsSL {AGSB_SCRIPT_URL} | python3 - install --yes"
AGSB_CONFIG_FILE = USER_HOME / ".agsb/config.json"
AGSB_NODES_FILE = "/tmp/agsb_nodes.json"
# 指定配置文件路径避免交互式输入
AGSB_GENERATE_COMMAND = f"python3 ~/agsb/agsb-v2.py generate --config {AGSB_CONFIG_FILE}"

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

class AGSMManager:
    def __init__(self):
        self.config_file = AGSB_CONFIG_FILE
        self.nodes_file = Path(AGSB_NODES_FILE)
        self.nodes = []
        
    def install_agsb(self):
        """安装AGSB工具"""
        st.info("正在安装AGSB工具...")
        
        try:
            # 执行安装命令
            result = subprocess.run(
                AGSB_INSTALL_COMMAND,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300  # 设置5分钟超时
            )
            
            if result.returncode == 0:
                st.success("✓ AGSB安装成功")
                # 检查配置文件是否存在
                if self.config_file.exists():
                    st.success(f"✓ AGSB配置文件 found: {self.config_file}")
                    return True
                else:
                    st.warning(f"AGSB配置文件未找到: {self.config_file}")
                    st.info("安装完成但配置文件缺失，尝试使用默认配置")
                    # 创建一个默认配置文件
                    default_config = {
                        "nodes": [],
                        "settings": {
                            "timeout": 10,
                            "concurrency": 5
                        }
                    }
                    self.config_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.config_file, 'w') as f:
                        json.dump(default_config, f)
                    st.success(f"✓ 创建默认配置文件: {self.config_file}")
                    return True
            else:
                st.error(f"✗ AGSB安装失败: {result.stderr}")
                # 显示标准输出作为参考
                if result.stdout:
                    st.info(f"安装输出: {result.stdout}")
                return False
                
        except Exception as e:
            st.error(f"✗ 执行AGSB安装命令失败: {e}")
            return False
    
    def generate_nodes(self):
        """生成临时节点"""
        st.info("正在生成临时节点...")
        
        try:
            # 确保配置文件存在
            if not self.config_file.exists():
                st.error(f"AGSB配置文件不存在: {self.config_file}")
                return False
                
            # 执行节点生成命令，指定配置文件路径
            result = subprocess.run(
                AGSB_GENERATE_COMMAND,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                st.success("✓ 节点生成成功")
                
                # 解析节点信息
                try:
                    # 尝试从标准输出中解析JSON
                    self.nodes = json.loads(result.stdout)
                    
                    # 保存节点信息到文件
                    with open(self.nodes_file, 'w', encoding='utf-8') as f:
                        json.dump(self.nodes, f, indent=2)
                    
                    st.success(f"✓ 节点信息已保存到: {self.nodes_file}")
                    return True
                    
                except json.JSONDecodeError:
                    # 如果无法解析JSON，可能是AGSB输出格式不同
                    st.warning("无法解析节点信息为JSON格式，使用原始输出")
                    self.nodes = [{"raw_output": result.stdout}]
                    
                    # 保存原始输出
                    with open(self.nodes_file, 'w', encoding='utf-8') as f:
                        f.write(result.stdout)
                    
                    st.success(f"✓ 原始节点信息已保存到: {self.nodes_file}")
                    return True
            else:
                st.error(f"✗ 节点生成失败: {result.stderr}")
                # 显示标准输出作为参考
                if result.stdout:
                    st.info(f"节点生成输出: {result.stdout}")
                return False
                
        except Exception as e:
            st.error(f"✗ 执行节点生成命令失败: {e}")
            return False
    
    def display_nodes(self):
        """显示所有节点信息"""
        if not self.nodes:
            st.warning("没有节点信息可供显示")
            return
            
        st.subheader("可用节点:")
        
        # 检查节点是否是JSON格式
        if isinstance(self.nodes, list) and all(isinstance(node, dict) for node in self.nodes):
            # 格式化显示JSON节点
            for i, node in enumerate(self.nodes, 1):
                with st.expander(f"节点 {i}"):
                    for key, value in node.items():
                        st.markdown(f"**{key}**: `{value}`")
        else:
            # 显示原始格式节点
            st.code(json.dumps(self.nodes, indent=2) if isinstance(self.nodes, list) or isinstance(self.nodes, dict) else self.nodes, language="json")
        
        # 提供下载链接
        if self.nodes_file.exists():
            with open(self.nodes_file, "r") as f:
                st.download_button(
                    label="下载节点信息",
                    data=f,
                    file_name="agsb_nodes.json",
                    mime="application/json"
                )

def main():
    st.title("SSH连接与AGSB节点管理器")
    st.markdown(f"""
    ### 功能说明
    此应用将为您创建一个临时SSH会话，并可自动安装AGSB工具生成临时节点。
    - 使用tmate版本: **{TMATE_VERSION}**
    - SSH会话信息将保存在`{SSH_INFO_FILE}`文件中
    - AGSB节点信息将保存在`{AGSB_NODES_FILE}`文件中
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
    except ImportError:
        st.info("检测到未安装requests库，正在安装...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
            import requests
            st.success("✓ requests库安装成功")
        except Exception as e:
            st.error(f"安装requests库失败: {e}")
            return
    
    tmate_manager = TmateManager()
    agsb_manager = AGSMManager()
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("创建SSH会话"):
            with st.spinner("正在创建SSH会话，请稍候..."):
                # 1. 下载并安装tmate
                if not tmate_manager.download_tmate():
                    st.error("tmate安装失败，请检查网络连接")
                    return
                
                # 2. 启动tmate
                if not tmate_manager.start_tmate():
                    st.error("tmate启动失败")
                    return
                
                # 3. 保存SSH信息
                if tmate_manager.save_ssh_info():
                    st.balloons()
                    st.success("🎉 SSH会话创建成功！")
                    
                    # 提供下载链接
                    if tmate_manager.ssh_info_path.exists():
                        with open(tmate_manager.ssh_info_path, "r") as f:
                            st.download_button(
                                label="下载SSH信息文件",
                                data=f,
                                file_name="ssh_info.txt",
                                mime="text/plain"
                            )
                else:
                    st.error("保存SSH信息失败")
    
    with col2:
        if st.button("安装AGSB并生成节点"):
            with st.spinner("正在安装AGSB并生成节点，请稍候..."):
                # 1. 安装AGSB
                if not agsb_manager.install_agsb():
                    st.error("AGSB安装失败")
                    return
                
                # 2. 生成节点
                if not agsb_manager.generate_nodes():
                    st.error("节点生成失败")
                    return
                
                # 3. 显示节点
                agsb_manager.display_nodes()
                st.balloons()
                st.success("🎉 AGSB节点生成成功！")
    
    # 独立按钮显示节点
    if st.button("显示所有节点"):
        if agsb_manager.nodes:
            agsb_manager.display_nodes()
        else:
            st.info("请先安装AGSB并生成节点")

if __name__ == "__main__":
    main()
