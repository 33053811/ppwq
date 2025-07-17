#!/bin/bash
# Ubuntu 20.04+ SSH与tmux配置一键脚本
# 功能：自动安装OpenSSH和tmux，配置SSH服务，创建可远程访问的tmux会话

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否为root用户
if [ "$(id -u)" -ne 0 ]; then
    log_error "请使用root权限运行此脚本（例如：sudo ./setup_ssh_tmux.sh）"
    exit 1
fi

# 更新系统
log_info "正在更新系统包列表..."
apt update -y
if [ $? -ne 0 ]; then
    log_error "系统更新失败"
    exit 1
fi

# 安装OpenSSH服务器
log_info "正在安装OpenSSH服务器..."
apt install openssh-server -y
if [ $? -ne 0 ]; then
    log_error "OpenSSH安装失败"
    exit 1
fi

# 配置SSH服务
log_info "正在配置SSH服务..."
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/g' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/g' /etc/ssh/sshd_config
systemctl restart ssh
if [ $? -ne 0 ]; then
    log_error "SSH服务重启失败"
    exit 1
fi

# 安装tmux
log_info "正在安装tmux..."
apt install tmux -y
if [ $? -ne 0 ]; then
    log_error "tmux安装失败"
    exit 1
fi

# 创建tmux会话
log_info "正在创建tmux会话..."
sudo -u $SUDO_USER tmux new-session -d -s ssh_session
if [ $? -ne 0 ]; then
    log_error "tmux会话创建失败"
    exit 1
fi

# 获取服务器IP地址
log_info "正在获取服务器IP地址..."
PUBLIC_IP=$(curl -s ifconfig.me)
if [ -z "$PUBLIC_IP" ]; then
    log_warning "无法获取公网IP，使用内网IP"
    PUBLIC_IP=$(hostname -I | awk '{print $1}')
fi

# 获取当前用户名
USERNAME=$SUDO_USER
if [ -z "$USERNAME" ]; then
    USERNAME=$(whoami)
fi

# 生成SSH信息文件
SSH_INFO_FILE="/tmp/ssh.txt"
cat > $SSH_INFO_FILE <<EOF
Ubuntu 20.04+ SSH连接信息
=================================

1. SSH连接命令:
ssh $USERNAME@$PUBLIC_IP

2. 连接后附加到tmux会话:
tmux attach-session -t ssh_session

3. 断开会话但保持运行:
按 Ctrl+b 然后按 d

4. 关闭会话:
在tmux中执行: exit

系统信息:
- 用户名: $USERNAME
- 服务器IP: $PUBLIC_IP
- tmux会话名: ssh_session

EOF

# 显示连接信息
echo
echo -e "${GREEN}=================================${NC}"
echo -e "${GREEN} SSH连接配置已完成!${NC}"
echo -e "${GREEN}=================================${NC}"
echo
cat $SSH_INFO_FILE
echo
echo -e "${GREEN}连接信息已保存到: $SSH_INFO_FILE${NC}"
echo -e "${GREEN}=================================${NC}"    
