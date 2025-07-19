#!/bin/bash

# 安装 cloudflared
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "[+] Installing cloudflared..."
  wget -O /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
  sudo dpkg -i /tmp/cloudflared.deb
else
  echo "[√] cloudflared already installed."
fi

set -e

# 定义常量
PASSWORD="密码"
PORTS=("端口" "端口" "端口")
NAMES=("隧道名称1" "隧道名称2" "隧道名称3")
TOKENS=(
"令牌"
"令牌"
"令牌"
)

# 安装依赖
apt update && apt install -y wget curl sudo unzip socat cloudflared openssl

# 安装 Hysteria2
mkdir -p /opt/hysteria
cd /opt/hysteria
wget -qO hysteria.tar.gz https://github.com/apernet/hysteria/releases/latest/download/hysteria-linux-amd64.tar.gz
tar -xzf hysteria.tar.gz
install -m 755 hysteria /usr/local/bin/hysteria

# 创建自签证书
mkdir -p /etc/hysteria/certs
openssl req -x509 -newkey rsa:2048 -keyout /etc/hysteria/certs/key.pem -out /etc/hysteria/certs/cert.pem -days 3650 -nodes -subj "/CN=localhost"

# 创建配置与服务
for i in ${!PORTS[@]}; do
  PORT=${PORTS[$i]}
  NAME=${NAMES[$i]}
  TOKEN=${TOKENS[$i]}
  mkdir -p /etc/hysteria/$NAME

  # 写入配置文件
  cat > /etc/hysteria/$NAME/config.yaml <<EOF
listen: :$PORT
protocol: udp
tls:
  cert: /etc/hysteria/certs/cert.pem
  key: /etc/hysteria/certs/key.pem
auth:
  type: password
  password: $PASSWORD
bandwidth:
  up: 100 mbps
  down: 100 mbps
EOF

  # 写入 systemd 服务文件
  cat > /etc/systemd/system/hysteria-$NAME.service <<EOF
[Unit]
Description=Hysteria2 $NAME Server
After=network.target

[Service]
ExecStart=/usr/local/bin/hysteria server -c /etc/hysteria/$NAME/config.yaml
Restart=always

[Install]
WantedBy=multi-user.target
EOF

  # 启用服务
  systemctl daemon-reexec
  systemctl daemon-reload
  systemctl enable --now hysteria-$NAME

  # 启动 cloudflared tunnel
  cat > /etc/systemd/system/cloudflared-$NAME.service <<EOF
[Unit]
Description=Cloudflare Tunnel $NAME
After=network.target

[Service]
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate run --token $TOKEN
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  systemctl enable --now cloudflared-$NAME
done

# 生成订阅文件
mkdir -p /etc/hysteria/sub
cat > /etc/hysteria/sub/karing.json <<EOF
[
  {
    "name": "JD主节点",
    "type": "hysteria2",
    "server": "jd.ppwq.us.kg",
    "port": 443,
    "auth_str": "$PASSWORD",
    "up_mbps": 100,
    "down_mbps": 100,
    "insecure": true
  },
  {
    "name": "JD备用1",
    "type": "hysteria2",
    "server": "jd1.ppwq.us.kg",
    "port": 443,
    "auth_str": "$PASSWORD",
    "up_mbps": 100,
    "down_mbps": 100,
    "insecure": true
  },
  {
    "name": "JD备用2",
    "type": "hysteria2",
    "server": "jd2.ppwq.us.kg",
    "port": 443,
    "auth_str": "$PASSWORD",
    "up_mbps": 100,
    "down_mbps": 100,
    "insecure": true
  }
]
EOF

echo "✅ 安装完成！订阅文件位于：/etc/hysteria/sub/karing.json"
