#!/usr/bin/env bash

# 设置根文件系统目录为当前目录
ROOTFS_DIR=$(pwd)
# 添加路径
export PATH=$PATH:${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin
# 设置最大重试次数和超时时间
max_retries=5
timeout=60  # 增加超时时间
# 获取系统架构
ARCH=$(uname -m)
# 获取当前用户名
CURRENT_USER=$(whoami)

# 定义颜色
CYAN='\e[0;36m'
WHITE='\e[0;37m'
RED='\e[0;31m'
GREEN='\e[0;32m'
YELLOW='\e[0;33m'
RESET_COLOR='\e[0m'

# 显示安装完成信息
display_gg() {
  clear
  echo -e "${WHITE}___________________________________________________${RESET_COLOR}"
  echo -e ""
  echo -e "           ${CYAN}-----> PROOT 环境已就绪! <----${RESET_COLOR}"
  echo -e ""
  echo -e "   ${WHITE}使用命令启动: ${GREEN}./start-proot.sh${RESET_COLOR}"
  echo -e "   ${WHITE}删除环境: ${RED}./root.sh del${RESET_COLOR}"
  echo -e "${WHITE}___________________________________________________${RESET_COLOR}"
}

# 显示帮助信息
display_help() {
  echo -e "${CYAN}Ubuntu Proot 环境安装脚本${RESET_COLOR}"
  echo -e "${WHITE}版本: 2.2 | 内核: $(uname -r)${RESET_COLOR}"
  echo -e "${WHITE}使用方法:${RESET_COLOR}"
  echo -e "  ${GREEN}./root.sh${RESET_COLOR}         - 安装Ubuntu Proot环境"
  echo -e "  ${GREEN}./root.sh del${RESET_COLOR}     - 删除所有配置和文件"
  echo -e "  ${GREEN}./root.sh help${RESET_COLOR}    - 显示此帮助信息"
  echo -e ""
  echo -e "${WHITE}系统信息:${RESET_COLOR}"
  echo -e "  ${WHITE}架构: ${YELLOW}$ARCH${RESET_COLOR}"
  echo -e "  ${WHITE}主机: ${YELLOW}$(hostname)${RESET_COLOR}"
  echo -e "  ${WHITE}用户: ${YELLOW}$CURRENT_USER${RESET_COLOR}"
  echo -e "  ${WHITE}路径: ${YELLOW}$ROOTFS_DIR${RESET_COLOR}"
}

# 删除所有配置和文件
delete_all() {
  echo -e "${YELLOW}[!] 正在删除所有配置和文件...${RESET_COLOR}"
  
  # 删除proot目录下的所有文件，但保留root.sh和README.md
  find "$ROOTFS_DIR" -mindepth 1 -not -name "root.sh" -not -name "README.md" -not -name ".git" -not -path "*/.git/*" -exec rm -rf {} \; 2>/dev/null
  
  echo -e "${GREEN}[✓] 所有配置和文件已删除!${RESET_COLOR}"
  echo -e "${WHITE}如果需要重新安装，请运行:${RESET_COLOR} ${GREEN}./root.sh${RESET_COLOR}"
  exit 0
}

# 检查命令是否存在
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# 安装必要依赖
install_dependencies() {
  local missing=()
  
  if ! command_exists curl; then
    missing+=("curl")
  fi
  
  if ! command_exists tar; then
    missing+=("tar")
  fi
  
  if ! command_exists gzip; then
    missing+=("gzip")
  fi
  
  if [ ${#missing[@]} -gt 0 ]; then
    echo -e "${YELLOW}[!] 缺少必要依赖: ${missing[*]}${RESET_COLOR}"
    echo -e "${CYAN}[*] 尝试安装依赖...${RESET_COLOR}"
    
    if command_exists apt-get; then
      sudo apt-get update && sudo apt-get install -y "${missing[@]}" || {
        echo -e "${RED}[✗] 依赖安装失败${RESET_COLOR}"
        exit 1
      }
    elif command_exists yum; then
      sudo yum install -y "${missing[@]}" || {
        echo -e "${RED}[✗] 依赖安装失败${RESET_COLOR}"
        exit 1
      }
    elif command_exists dnf; then
      sudo dnf install -y "${missing[@]}" || {
        echo -e "${RED}[✗] 依赖安装失败${RESET_COLOR}"
        exit 1
      }
    elif command_exists zypper; then
      sudo zypper install -y "${missing[@]}" || {
        echo -e "${RED}[✗] 依赖安装失败${RESET_COLOR}"
        exit 1
      }
    else
      echo -e "${RED}[✗] 无法自动安装依赖，请手动安装: ${missing[*]}${RESET_COLOR}"
      exit 1
    fi
  fi
}

# 处理命令行参数
case "$1" in
  del)
    delete_all
    ;;
  help|--help|-h)
    display_help
    exit 0
    ;;
esac

# 安装必要依赖
install_dependencies

echo -e "${CYAN}[*] 系统信息:${RESET_COLOR}"
echo -e "  ${WHITE}用户: ${YELLOW}$CURRENT_USER${RESET_COLOR}"
echo -e "  ${WHITE}架构: ${YELLOW}$ARCH${RESET_COLOR}"
echo -e "  ${WHITE}工作目录: ${YELLOW}$ROOTFS_DIR${RESET_COLOR}"
echo -e "  ${WHITE}内核版本: ${YELLOW}$(uname -r)${RESET_COLOR}"
echo -e "  ${WHITE}可用磁盘空间: ${YELLOW}$(df -h . | awk 'NR==2 {print $4}')${RESET_COLOR}"

# 根据CPU架构设置对应的架构名称
if [ "$ARCH" = "x86_64" ]; then
  ARCH_ALT=amd64
elif [ "$ARCH" = "aarch64" ]; then
  ARCH_ALT=arm64
else
  echo -e "${RED}[✗] 不支持的CPU架构: $ARCH${RESET_COLOR}"
  exit 1
fi

echo -e "${CYAN}[*] 架构别名: ${YELLOW}$ARCH_ALT${RESET_COLOR}"

# 检查是否已安装
if [ ! -e $ROOTFS_DIR/.installed ]; then
  echo -e "${CYAN}"
  echo "#######################################################################################"
  echo "#"
  echo "#                            Ubuntu Proot 环境安装程序"
  echo "#"
  echo "#                        优化版 | 内核: $(uname -r) | $(date)"
  echo "#"
  echo "#######################################################################################"
  echo -e "${RESET_COLOR}"

  read -p "是否安装Ubuntu 20.04 LTS (Focal Fossa)? [Y/n]: " install_ubuntu
fi

# 根据用户输入决定是否安装Ubuntu
case "$install_ubuntu" in
  [nN][oO]|[nN])
    echo "跳过Ubuntu安装。"
    ;;
  *)
    echo -e "${GREEN}[*] 开始下载Ubuntu基础系统...${RESET_COLOR}"
    # 使用官方Ubuntu源下载基础系统
    UBUNTU_URL="https://cdimage.ubuntu.com/ubuntu-base/releases/20.04/release/ubuntu-base-20.04.4-base-${ARCH_ALT}.tar.gz"
    
    # 显示下载信息
    echo -e "  ${WHITE}URL: ${YELLOW}$UBUNTU_URL${RESET_COLOR}"
    
    # 下载文件
    if ! curl --retry $max_retries --connect-timeout $timeout -L -o /tmp/rootfs.tar.gz "$UBUNTU_URL"; then
      echo -e "${RED}[✗] 错误: Ubuntu基础系统下载失败${RESET_COLOR}"
      exit 1
    fi
    
    # 检查文件是否下载成功
    if [ ! -s "/tmp/rootfs.tar.gz" ]; then
      echo -e "${RED}[✗] 错误: 下载的文件为空${RESET_COLOR}"
      rm -f /tmp/rootfs.tar.gz
      exit 1
    fi
    
    echo -e "${GREEN}[✓] 下载完成!${RESET_COLOR}"
    
    echo -e "${GREEN}[*] 解压Ubuntu基础系统到 $ROOTFS_DIR...${RESET_COLOR}"
    # 创建临时目录用于解压
    TEMP_DIR=$(mktemp -d)
    
    # 解压到临时目录
    if ! tar -xzf /tmp/rootfs.tar.gz -C "$TEMP_DIR"; then
      echo -e "${RED}[✗] 错误: 解压Ubuntu基础系统失败${RESET_COLOR}"
      echo -e "${YELLOW}可能原因:"
      echo -e "  1. 下载文件损坏"
      echo -e "  2. 磁盘空间不足 (当前剩余: $(df -h . | awk 'NR==2 {print $4}'))"
      echo -e "  3. 文件权限问题"
      echo -e "${RESET_COLOR}"
      rm -rf "$TEMP_DIR"
      rm -f /tmp/rootfs.tar.gz
      exit 1
    fi
    
    # 移动解压后的文件到目标目录
    if ! mv "$TEMP_DIR"/* "$ROOTFS_DIR"; then
      echo -e "${RED}[✗] 错误: 移动文件失败${RESET_COLOR}"
      rm -rf "$TEMP_DIR"
      exit 1
    fi
    
    # 清理临时目录
    rm -rf "$TEMP_DIR"
    
    echo -e "${GREEN}[✓] 解压成功!${RESET_COLOR}"
    ;;
esac

# 安装proot
if [ ! -e $ROOTFS_DIR/.installed ] && [ ! -e $ROOTFS_DIR/usr/local/bin/proot ]; then
  echo -e "${GREEN}[*] 安装PROOT...${RESET_COLOR}"
  
  mkdir -p "$ROOTFS_DIR/usr/local/bin"
  
  # 使用官方proot构建
  PROOT_VERSION="5.3.0"
  
  # 根据架构选择正确的URL
  if [ "$ARCH" = "x86_64" ]; then
    PROOT_URL="https://github.com/proot-me/proot/releases/download/v${PROOT_VERSION}/proot-v${PROOT_VERSION}-x86_64-static"
  elif [ "$ARCH" = "aarch64" ]; then
    PROOT_URL="https://github.com/proot-me/proot/releases/download/v${PROOT_VERSION}/proot-v${PROOT_VERSION}-aarch64-static"
  else
    echo -e "${RED}[✗] 不支持的架构: $ARCH${RESET_COLOR}"
    exit 1
  fi
  
  # 下载proot
  echo -e "  ${WHITE}下载: ${YELLOW}$PROOT_URL${RESET_COLOR}"
  if ! curl -L --retry $max_retries --connect-timeout $timeout -o "$ROOTFS_DIR/usr/local/bin/proot" "$PROOT_URL"; then
    echo -e "${RED}[✗] 错误: proot下载失败${RESET_COLOR}"
    exit 1
  fi

  # 验证proot文件
  if [ ! -s "$ROOTFS_DIR/usr/local/bin/proot" ]; then
    echo -e "${RED}[✗] 错误: proot文件为空或无效${RESET_COLOR}"
    rm -f "$ROOTFS_DIR/usr/local/bin/proot"
    exit 1
  fi

  # 设置proot执行权限
  if ! chmod 755 "$ROOTFS_DIR/usr/local/bin/proot"; then
    echo -e "${RED}[✗] 错误: 设置proot权限失败${RESET_COLOR}"
    exit 1
  fi
  
  echo -e "${GREEN}[✓] PROOT安装成功!${RESET_COLOR}"
fi

# 完成安装配置
if [ ! -e $ROOTFS_DIR/.installed ]; then
  echo -e "${GREEN}[*] 配置环境...${RESET_COLOR}"
  
  # 设置DNS服务器
  mkdir -p "${ROOTFS_DIR}/etc"
  printf "nameserver 1.1.1.1\nnameserver 8.8.8.8\nnameserver 2606:4700:4700::1111" > "${ROOTFS_DIR}/etc/resolv.conf"
  
  # 创建用户目录
  mkdir -p "$ROOTFS_DIR/home/$CURRENT_USER"
  
  # 创建.bashrc文件
  mkdir -p "$ROOTFS_DIR/root"
  cat > "$ROOTFS_DIR/root/.bashrc" << 'EOF'
# 默认.bashrc内容
if [ -f /etc/bash.bashrc ]; then
  . /etc/bash.bashrc
fi

# 显示提示信息
PS1='\[\033[1;32m\]proot-ubuntu\[\033[0m\]:\[\033[1;34m\]\w\[\033[0m\]\\$ '
EOF

  # 创建初始化脚本
  cat > "$ROOTFS_DIR/root/init.sh" << 'EOF'
#!/bin/bash

# 使用传入的物理机用户名
HOST_USER=$(whoami)

# 创建物理机用户目录
mkdir -p "/home/${HOST_USER}" 2>/dev/null
echo -e "\033[1;32m[✓] 已创建用户目录: /home/${HOST_USER}\033[0m"

# 备份原始软件源
cp /etc/apt/sources.list /etc/apt/sources.list.bak 2>/dev/null

# 设置正确的软件源 (Ubuntu 20.04 focal)
cat > /etc/apt/sources.list <<SOURCES
deb http://archive.ubuntu.com/ubuntu focal main universe restricted multiverse
deb http://archive.ubuntu.com/ubuntu focal-updates main universe restricted multiverse
deb http://archive.ubuntu.com/ubuntu focal-backports main universe restricted multiverse
deb http://security.ubuntu.com/ubuntu focal-security main universe restricted multiverse
SOURCES

# 显示系统信息
echo -e "\033[1;36m[系统信息]"
echo -e "  主机名: \033[1;33m$(hostname)\033[0m"
echo -e "  用户: \033[1;33m${HOST_USER}\033[0m"
echo -e "  内核: \033[1;33m$(uname -r)\033[0m"
echo -e "  内存: \033[1;33m$(free -m | awk '/Mem/{print $2}') MB\033[0m"

# 更新系统
echo -e "\033[1;32m[✓] 软件源已更新为Ubuntu 20.04 (Focal)源\033[0m"
echo -e "\033[1;33m[*] 正在更新系统并安装必要软件包，请稍候...\033[0m"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y upgrade
apt-get install -y --no-install-recommends \
  curl wget git vim nano htop tmux \
  python3 python3-pip python3-venv \
  build-essential net-tools zip unzip \
  sudo locales tree ca-certificates \
  gnupg lsb-release iproute2 cron

# 清理APT缓存
apt-get clean
rm -rf /var/lib/apt/lists/*

echo -e "\033[1;32m[✓] 系统更新和软件安装完成!\033[0m"


\033[1;36m欢迎进入Ubuntu 20.04环境!\033[0m

\033[1;33m提示: 输入 'exit' 可以退出proot环境\033[0m

WELCOME
EOF

  # 设置初始化脚本执行权限
  chmod +x "$ROOTFS_DIR/root/init.sh"
  
  # 创建启动脚本
  cat > "$ROOTFS_DIR/start-proot.sh" << EOF
#!/bin/bash
# 启动proot环境
echo -e "\033[1;36m[*] 正在启动PROOT环境...\033[0m"
echo -e "  工作目录: \033[1;33m$ROOTFS_DIR\033[0m"
echo -e "  用户: \033[1;33m$CURRENT_USER\033[0m"
echo -e "  架构: \033[1;33m$ARCH\033[0m"
echo -e "  内核: \033[1;33m$(uname -r)\033[0m"

"$ROOTFS_DIR/usr/local/bin/proot" \\
  --rootfs="$ROOTFS_DIR" \\
  --cwd=/root \\
  --bind=/dev --bind=/sys --bind=/proc \\
  --bind=/etc/resolv.conf \\
  --bind=/etc/hosts \\
  --bind=/etc/localtime \\
  /bin/bash -c "cd /root && /bin/bash /root/init.sh && /bin/bash"
EOF

  chmod +x "$ROOTFS_DIR/start-proot.sh"
  
  # 清理临时文件
  rm -f /tmp/rootfs.tar.gz
  
  # 创建安装标记文件
  touch "$ROOTFS_DIR/.installed"
  
  echo -e "${GREEN}[✓] 环境配置完成!${RESET_COLOR}"
fi

# 显示完成信息
display_gg

# 启动选项
echo -e "\n${WHITE}是否立即启动PROOT环境? [Y/n]: ${RESET_COLOR}"
read -r start_now

case "$start_now" in
  [nN][oO]|[nN])
    echo -e "您可以使用以下命令启动:"
    echo -e "  ${GREEN}./start-proot.sh${RESET_COLOR}"
    ;;
  *)
    echo -e "${CYAN}[*] 启动PROOT环境...${RESET_COLOR}"
    cd "$ROOTFS_DIR"
    exec "./start-proot.sh"
    ;;
esac
