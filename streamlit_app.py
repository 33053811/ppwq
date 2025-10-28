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
        self.ses
