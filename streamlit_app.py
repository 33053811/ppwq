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

# 配置
TMATE_VERSION = "2.4.0"  # 使用最新稳定版本
TMATE_DOWNLOAD_URL = f"https://github.com/tmate-io/tmate/releases/download/{TMATE_VERSION}/tmate-{TMATE_VERSION}-static-linux-amd64.tar.xz"
USER_HOME = Path.home()
SSH_INFO_FILE = "/tmp/ssh.txt"  # 保存到临时目录

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

def run_command_in_container(command: str, timeout: int = 3600):
    """
    在当前容器里运行命令，并实时把 stdout/stderr 输出到 Streamlit 界面。
    注意：command 会作为 bash -c 的参数执行，因此可以包含管道和重定向等 shell 语法。
    timeout 单位：秒（默认 3600s = 1 小时）
    """
    placeholder = st.empty()
    log_area = placeholder.container()
    log_lines = []
    start_time = time.time()

    # 记录到临时日志文件（方便事后下载）
    log_path = "/tmp/command_run.log"
    try:
        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write(f"\n\n--- COMMAND START {datetime.now().isoformat()} ---\n")
            logf.write(command + "\n\n")

        # 使用 Popen 以便实时读取输出
        process = subprocess.Popen(
            ["bash", "-lc", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            start_new_session=True
        )

        # 实时流式更新
        with open(log_path, "a", encoding="utf-8") as logf:
            for line in iter(process.stdout.readline, ""):
                if line == "" and process.poll() is not None:
                    break
                if line:
                    # 保留原始输出
                    log_lines.append(line)
                    logf.write(line)
                    # 每行更新一次界面（避免太频繁刷新导致卡顿）
                    if len(log_lines) % 5 == 0:
                        log_area.code("".join(log_lines[-500:]), language="bash")
            # 等待进程结束
            process.stdout.close()
            retcode = process.wait(timeout=max(1, timeout - int(time.time() - start_time)))
        
        # 最后一次刷新全部内容
        log_area.code("".join(log_lines), language="bash")

        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write(f"\n--- COMMAND END {datetime.now().isoformat()} RETURN {retcode} ---\n")

        return {"returncode": retcode, "log_path": log_path, "output": "".join(log_lines)}
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except Exception:
            pass
        msg = "\n⚠️ 命令执行超时并已终止（TimeoutExpired）\n"
        log_lines.append(msg)
        log_area.code("".join(log_lines), language="bash")
        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write(msg)
        return {"returncode": -1, "log_path": log_path, "output": "".join(log_lines)}
    except Exception as e:
        err_msg = f"\n✗ 运行命令时发生异常: {e}\n"
        log_lines.append(err_msg)
        log_area.code("".join(log_lines), language="bash")
        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write(err_msg)
        return {"returncode": -2, "log_path": log_path, "output": "".join(log_lines)}

def main():
    st.title("SSH连接管理器（含在容器内执行命令）")
    st.markdown(f"""
    ### 功能说明
    - 在当前运行环境创建临时 tmate 会话（可选）
    - **直接在当前容器里执行 shell 命令（包括 `curl | python3`）并实时显示输出**
    - 会话信息将保存在`{SSH_INFO_FILE}`文件中（如果创建了 tmate 会话）
    """)
    
    # 添加安全警告
    st.warning("""
    **安全提示:**
    - 直接在容器内执行命令会对当前运行环境造成影响（安装/修改文件/启动进程等）。
    - 请勿在生产或敏感环境中运行不受信任的脚本或命令。
    - 确认命令来源可信再执行。
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
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("创建SSH会话"):
            with st.spinner("正在创建SSH会话..."):
                if not manager.download_tmate():
                    st.error("tmate安装失败，请检查网络连接")
                else:
                    if not manager.start_tmate():
                        st.error("tmate启动失败")
                    else:
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
    with col2:
        if st.button("停止所有 tmate 进程（谨慎）"):
            # 尝试通过 pkill 停止 tmate（谨慎）
            try:
                subprocess.run(["pkill", "-f", "tmate"], check=False)
                st.success("尝试停止 tmate 进程（已发送信号）")
            except Exception as e:
                st.error(f"停止 tmate 失败: {e}")
    
    st.markdown("---")
    st.header("在当前容器内执行命令（方案 B）")
    st.markdown("在下面编辑要执行的命令（会作为 `bash -c` 执行，支持管道）。默认已填入你提供的命令；注意命令中存在空的选项（例如 `--port`、`--agk`、`--domain`），请根据需要补充。")

    default_cmd = r"cd ~ &&   curl -fsSL https://raw.githubusercontent.com/zhumengkang/agsb/main/agsb-v2.py | python3 - install  --uuid c8354ea6-3ace-9501-0fc5-34f495406741  --port   --agk   --domain "
    cmd = st.text_area("要执行的命令（可修改）", value=default_cmd, height=120)
    timeout_seconds = st.number_input("最大等待时间（秒）", min_value=10, value=1800, step=60)
    agree = st.checkbox("我已确认命令来源可信并同意在此运行上述命令（危险操作）", value=False)

    run_col1, run_col2 = st.columns([1, 1])
    with run_col1:
        if st.button("在本容器执行命令") and agree:
            st.info("开始在容器内执行命令，输出将实时显示在下方。")
            result = run_command_in_container(cmd, timeout=int(timeout_seconds))
            if result["returncode"] == 0:
                st.success("命令执行完成（returncode=0）。")
            elif result["returncode"] > 0:
                st.warning(f"命令执行结束，但返回码为 {result['returncode']}。")
            else:
                st.error(f"命令执行异常或超时，返回码 {result['returncode']}")
            if os.path.exists(result["log_path"]):
                with open(result["log_path"], "r", encoding="utf-8") as lf:
                    st.download_button(
                        label="下载命令日志",
                        data=lf,
                        file_name=f"command_log_{int(time.time())}.log",
                        mime="text/plain"
                    )
    with run_col2:
        if st.button("显示 /tmp 目录（调试用）"):
            try:
                out = subprocess.run(["bash", "-lc", "ls -la /tmp"], capture_output=True, text=True, timeout=10)
                st.code(out.stdout, language="bash")
            except Exception as e:
                st.error(f"列出 /tmp 失败: {e}")

if __name__ == "__main__":
    main()
