import subprocess
import streamlit as st

def execute_command(command):
    """执行命令并输出结果"""
    try:
        if not command.strip():
            st.warning("请输入要执行的命令。")
            return
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            st.success("命令执行成功：")
            st.code(result.stdout)
        else:
            st.error("命令执行出错：")
            st.code(result.stderr)
    except Exception as e:
        st.error(f"执行命令时出错: {e}")

def main():
    st.title("命令执行控制台")

    # 顶部命令输入框
    command_input = st.text_area(
        "输入要执行的命令：",
        height=120,
        placeholder="请输入 Shell 命令，如：ls -la /tmp"
    )

    # 执行按钮
    if st.button("执行命令"):
        execute_command(command_input)

if __name__ == "__main__":
    main()
