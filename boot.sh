#!/bin/bash

# 设置根文件系统目录为当前目录
ROOTFS_DIR=$(pwd)
# 添加路径
export PATH=$PATH:~/.local/usr/bin
# 设置最大重试次数和超时时间
MAX_RETRIES=10
TIMEOUT=5
# 获取系统架构
ARCH=$(uname -m)
# 获取当前用户名
CURRENT_USER=$(whoami)
# Ubuntu 版本
UBUNTU_VERSION="22.04"
UBUNTU_CODENAME="jammy"

# 定义颜色
CYAN='\e[0;36m'
WHITE='\e[0;37m'
RED='\e[0;31m'
GREEN='\e[0;32m'
YELLOW='\e[0;33m'
BLUE='\e[0;34m'
MAGENTA='\e[0;35m'
RESET_COLOR='\e[0m'

# 显示带时间戳的消息
log() {
    local color=$1
    local message=$2
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    echo -e "${color}[${timestamp}] ${message}${RESET_COLOR}"
}

# 显示安装完成信息
display_gg() {
    echo -e "\n${WHITE}══════════════════════════════════════════════════════════════${RESET_COLOR}"
    echo -e "                  ${CYAN}🚀 UBUNTU PROOT 安装完成! 🚀${RESET_COLOR}"
    echo -e "${WHITE}══════════════════════════════════════════════════════════════${RESET_COLOR}"
    echo -e "${GREEN}▸ 启动命令: ${WHITE}./start-proot.sh${RESET_COLOR}"
    echo -e "${GREEN}▸ 退出环境: ${WHITE}在proot中执行 'exit'${RESET_COLOR}"
    echo -e "${GREEN}▸ 删除环境: ${WHITE}./root.sh del${RESET_COLOR}"
    echo -e "${GREEN}▸ 帮助信息: ${WHITE}./root.sh help${RESET_COLOR}"
    echo -e "${WHITE}══════════════════════════════════════════════════════════════${RESET_COLOR}\n"
}

# 显示帮助信息
display_help() {
    echo -e "${CYAN}╔════════════════════════ Ubuntu Proot 环境安装脚本 ═══════════════════════╗${RESET_COLOR}"
    echo -e "${CYAN}║${RESET_COLOR}${GREEN} 功能:${RESET_COLOR} 在非root环境下安装完整的Ubuntu系统                               ${CYAN}║${RESET_COLOR}"
    echo -e "${CYAN}╠══════════════════════════════════════════════════════════════════════════╣${RESET_COLOR}"
    echo -e "${CYAN}║${RESET_COLOR}${WHITE} 使用方法:${RESET_COLOR}                                                              ${CYAN}║${RESET_COLOR}"
    echo -e "${CYAN}║${RESET_COLOR}  ${GREEN}./root.sh${RESET_COLOR}         - 安装Ubuntu Proot环境                              ${CYAN}║${RESET_COLOR}"
    echo -e "${CYAN}║${RESET_COLOR}  ${GREEN}./root.sh del${RESET_COLOR}     - 删除所有配置和文件                                ${CYAN}║${RESET_COLOR}"
    echo -e "${CYAN}║${RESET_COLOR}  ${GREEN}./root.sh help${RESET_COLOR}    - 显示此帮助信息                                   ${CYAN}║${RESET_COLOR}"
    echo -e "${CYAN}╠══════════════════════════════════════════════════════════════════════════╣${RESET_COLOR}"
    echo -e "${CYAN}║${RESET_COLOR}${YELLOW} 系统要求:${RESET_COLOR}                                                              ${CYAN}║${RESET_COLOR}"
    echo -e "${CYAN}║${RESET_COLOR} - 支持架构: x86_64, aarch64                                ${CYAN}║${RESET_COLOR}"
    echo -e "${CYAN}║${RESET_COLOR} - 磁盘空间: 至少1GB可用空间                                ${CYAN}║${RESET_COLOR}"
    echo -e "${CYAN}║${RESET_COLOR} - 网络连接: 需要访问互联网                                ${CYAN}║${RESET_COLOR}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${RESET_COLOR}"
    echo -e "${WHITE}更多信息请查看 README.md 文件${RESET_COLOR}\n"
}

# 检查命令是否存在
command_exists() {
    command -v "$@" >/dev/null 2>&1
}

# 安全下载函数
safe_download() {
    local url=$1
    local output=$2
    local retries=0
    
    while [ $retries -lt $MAX_RETRIES ]; do
        if curl --retry 3 --connect-timeout $TIMEOUT -sSL -o "$output" "$url"; then
            if [ -s "$output" ]; then
                log $GREEN "下载成功: $(basename $output)"
                return 0
            fi
        fi
        
        retries=$((retries+1))
        log $YELLOW "下载失败 (尝试 $retries/$MAX_RETRIES): $(basename $output)"
        sleep 2
    done
    
    log $RED "无法下载文件: $(basename $output)"
    return 1
}

# 删除所有配置和文件
delete_all() {
    echo -e "\n${RED}════════════════════ 警告: 将删除所有配置和文件 ════════════════════${RESET_COLOR}"
    read -p "确定要删除Ubuntu Proot环境? (y/N): " confirm
    
    if [[ $confirm =~ ^[Yy]$ ]]; then
        log $YELLOW "正在删除Ubuntu Proot环境..."
        
        # 删除proot目录下的所有文件，但保留root.sh和README.md
        find "$ROOTFS_DIR" -mindepth 1 -not -name "root.sh" -not -name "README.md" -not -name ".git" -not -path "*/.git/*" -exec rm -rf {} \; 2>/dev/null
        
        log $GREEN "所有配置和文件已删除!"
        echo -e "${WHITE}如果需要重新安装，请运行:${RESET_COLOR} ${GREEN}./root.sh${RESET_COLOR}\n"
    else
        log $YELLOW "取消删除操作"
    fi
    exit 0
}

# 安装Ubuntu基础系统
install_ubuntu() {
    log $BLUE "开始安装Ubuntu ${UBUNTU_VERSION} 基础系统..."
    
    # 根据CPU架构设置对应的架构名称
    case "$ARCH" in
        x86_64) ARCH_ALT=amd64 ;;
        aarch64) ARCH_ALT=arm64 ;;
        armv7l) ARCH_ALT=armhf ;;
        *) 
            log $RED "不支持的CPU架构: $ARCH"
            exit 1
            ;;
    esac
    
    # Ubuntu基础镜像URL
    local UBUNTU_URL="https://partner-images.canonical.com/core/${UBUNTU_CODENAME}/current/ubuntu-${UBUNTU_CODENAME}-core-cloudimg-${ARCH_ALT}-root.tar.gz"
    
    # 下载Ubuntu基础系统
    if ! safe_download "$UBUNTU_URL" "/tmp/rootfs.tar.gz"; then
        exit 1
    fi
    
    log $BLUE "解压Ubuntu基础系统到 $ROOTFS_DIR..."
    tar -xzpf /tmp/rootfs.tar.gz -C $ROOTFS_DIR
    rm -f /tmp/rootfs.tar.gz
}

# 安装proot
install_proot() {
    log $BLUE "安装PROOT环境..."
    mkdir -p $ROOTFS_DIR/usr/local/bin
    
    # PROOT下载URL
    local PROOT_URL="https://raw.githubusercontent.com/zhumengkang/agsb/main/proot-${ARCH}"
    
    log $CYAN "下载PROOT..."
    if ! safe_download "$PROOT_URL" "$ROOTFS_DIR/usr/local/bin/proot"; then
        exit 1
    fi
    
    chmod 755 $ROOTFS_DIR/usr/local/bin/proot
}

# 完成安装配置
setup_environment() {
    log $BLUE "配置系统环境..."
    
    # 设置DNS服务器
    printf "nameserver 1.1.1.1\nnameserver 8.8.8.8" > ${ROOTFS_DIR}/etc/resolv.conf
    
    # 创建用户目录
    mkdir -p $ROOTFS_DIR/home/$CURRENT_USER
    
    # 创建安装标记文件
    touch $ROOTFS_DIR/.installed
}

# 创建初始化脚本
create_init_script() {
    log $BLUE "创建初始化脚本..."
    
    cat > $ROOTFS_DIR/root/init.sh << EOF
#!/bin/bash

# 使用传入的物理机用户名
HOST_USER="$CURRENT_USER"

# 设置终端
echo "export TERM=xterm-256color" >> /root/.bashrc
echo "export PS1='\[\033[1;32m\]proot-ubuntu\[\033[0m\]:\[\033[1;34m\]\w\[\033[0m\]\\\\$ '" >> /root/.bashrc

# 创建物理机用户目录
mkdir -p /home/\$HOST_USER 2>/dev/null
echo -e "\033[1;32m已创建用户目录: /home/\$HOST_USER\033[0m"

# 更新系统
echo -e "\033[1;33m正在更新系统...\033[0m"
apt-get update -qq
apt-get upgrade -y -qq

# 安装基本软件包
echo -e "\033[1;33m正在安装基本软件包...\033[0m"
apt-get install -y -qq --no-install-recommends \\
    curl wget git vim nano htop \\
    tmux python3 python3-pip \\
    build-essential net-tools \\
    zip unzip sudo locales \\
    tree ca-certificates \\
    gnupg lsb-release \\
    iproute2 cron \\
    neofetch

# 清理缓存
apt-get autoremove -y -qq
apt-get clean -qq
rm -rf /var/lib/apt/lists/*

# 设置语言环境
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8

# 显示欢迎信息
clear
neofetch
echo -e "\033[1;36m════════════════════════ Ubuntu Proot 环境 ════════════════════════\033[0m"
echo -e "\033[1;35m系统信息:\033[0m"
echo -e "  ▸ \033[1;34m用户名:\033[0m \033[0;33mroot\033[0m"
echo -e "  ▸ \033[1;34m主机用户:\033[0m \033[0;33m\$HOST_USER\033[0m"
echo -e "  ▸ \033[1;34mUbuntu版本:\033[0m \033[0;33m$UBUNTU_VERSION ($UBUNTU_CODENAME)\033[0m"
echo -e "  ▸ \033[1;34m架构:\033[0m \033[0;33m$ARCH\033[0m"
echo -e "\033[1;35m常用命令:\033[0m"
echo -e "  ▸ \033[1;32m更新系统:\033[0m apt update && apt upgrade"
echo -e "  ▸ \033[1;32m安装软件:\033[0m apt install <软件包>"
echo -e "  ▸ \033[1;32m退出环境:\033[0m exit"
echo -e "\033[1;36m══════════════════════════════════════════════════════════════════\033[0m"
echo -e "\033[1;33m提示: 输入 'exit' 可以退出proot环境\033[0m\n"
EOF

    chmod +x $ROOTFS_DIR/root/init.sh
}

# 创建启动脚本
create_start_script() {
    log $BLUE "创建启动脚本..."
    
    cat > $ROOTFS_DIR/start-proot.sh << EOF
#!/bin/bash
# Ubuntu Proot 启动脚本
echo -e "${CYAN}正在启动Ubuntu ${UBUNTU_VERSION} Proot环境...${RESET_COLOR}"
cd $ROOTFS_DIR
$ROOTFS_DIR/usr/local/bin/proot \\
  --rootfs="$ROOTFS_DIR" \\
  --cwd=/root \\
  --bind=/dev \\
  --bind=/sys \\
  --bind=/proc \\
  --bind=/etc/resolv.conf \\
  --bind=/tmp \\
  --bind=$HOME:/host-home \\
  /bin/bash -c "cd /root && /bin/bash /root/init.sh && /bin/bash"
EOF

    chmod +x $ROOTFS_DIR/start-proot.sh
}

# 主安装流程
main_install() {
    clear
    echo -e "${CYAN}╔════════════════════ Ubuntu Proot 安装程序 ═══════════════════╗${RESET_COLOR}"
    echo -e "${CYAN}║${RESET_COLOR}${GREEN} 版本: 2.0.0${RESET_COLOR}                                                  ${CYAN}║${RESET_COLOR}"
    echo -e "${CYAN}║${RESET_COLOR}${GREEN} 作者: 康康${RESET_COLOR}                                                      ${CYAN}║${RESET_COLOR}"
    echo -e "${CYAN}║${RESET_COLOR}${GREEN} GitHub: https://github.com/zhumengkang/${RESET_COLOR}              ${CYAN}║${RESET_COLOR}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${RESET_COLOR}"
    
    # 显示系统信息
    echo -e "${WHITE}▸ 当前用户: ${GREEN}$CURRENT_USER${RESET_COLOR}"
    echo -e "${WHITE}▸ 系统架构: ${GREEN}$ARCH${RESET_COLOR}"
    echo -e "${WHITE}▸ Ubuntu版本: ${GREEN}$UBUNTU_VERSION ($UBUNTU_CODENAME)${RESET_COLOR}"
    echo -e "${WHITE}▸ 工作目录: ${GREEN}$ROOTFS_DIR${RESET_COLOR}"
    echo -e "${WHITE}══════════════════════════════════════════════════════════════${RESET_COLOR}"
    
    # 检查是否已安装
    if [ -e $ROOTFS_DIR/.installed ]; then
        log $YELLOW "检测到已安装的环境，跳过安装步骤"
        display_gg
        exit 0
    fi
    
    # 确认安装
    read -p "是否继续安装Ubuntu Proot环境? (Y/n): " confirm_install
    [[ "$confirm_install" =~ ^[Nn]$ ]] && exit 0
    
    # 安装步骤
    install_ubuntu
    install_proot
    setup_environment
    create_init_script
    create_start_script
    
    # 完成安装
    clear
    display_gg
    
    # 询问是否立即启动
    read -p "是否立即启动Ubuntu Proot环境? (Y/n): " start_now
    if [[ ! "$start_now" =~ ^[Nn]$ ]]; then
        log $CYAN "启动Ubuntu Proot环境..."
        $ROOTFS_DIR/start-proot.sh
    else
        log $GREEN "安装完成！您可以使用 ./start-proot.sh 命令随时启动环境"
    fi
}

# 处理命令行参数
case "$1" in
    del|delete)
        delete_all
        ;;
    help|--help|-h)
        display_help
        exit 0
        ;;
    *)
        main_install
        ;;
esac
