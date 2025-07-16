#!/bin/bash

# ------------- 基础参数 -------------
DOMAIN="jd.ppwq.us.kg"
PORT=22335
TUNNEL_TOKEN="eyJhIjoiMTcxNjEzYjZkNTdjZTY2YzdhMWQ2OGQzMGEyMDBlYTYiLCJ0IjoiMmE1ZTA0ZDQtZjMwMy00ZjAzLTgwM2ItNjc2NmRkYTc2MTU4IiwicyI6Ik4ySTROV00yTkRjdE5EVTBZaTAwWVdaakxXSTRPVEV0TkdGbE16WmhZVE5qT0dWaSJ9"
REALITY_DEST="www.liverpoolfc.com"
SHORT_ID="12345678"
FINGERPRINT="chrome"

# ------------- 安装 Docker -------------
echo "[+] Installing Docker..."
apt update && apt install -y curl wget unzip sudo
curl -fsSL https://get.docker.com | bash
systemctl enable docker && systemctl start docker
apt install -y docker-compose

# ------------- 生成密钥与UUID -------------
echo "[+] Generating X25519 keypair and UUID..."
KEY_JSON=$(docker run --rm teddysun/xray xray x25519)
PRIVATE_KEY=$(echo "$KEY_JSON" | grep 'Private key' | awk '{print $3}')
PUBLIC_KEY=$(echo "$KEY_JSON" | grep 'Public key' | awk '{print $3}')
UUID=$(uuidgen)

echo "[+] PRIVATE_KEY: $PRIVATE_KEY"
echo "[+] PUBLIC_KEY:  $PUBLIC_KEY"
echo "[+] UUID:        $UUID"

# ------------- 准备目录结构 -------------
mkdir -p ~/vless-reality-cf && cd ~/vless-reality-cf

# ------------- 写入 Xray 配置 -------------
cat > xray-config.json <<EOF
{
  "log": {
    "loglevel": "warning"
  },
  "inbounds": [
    {
      "port": $PORT,
      "protocol": "vless",
      "settings": {
        "clients": [
          {
            "id": "$UUID",
            "flow": "xtls-rprx-vision"
          }
        ],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "$REALITY_DEST:443",
          "xver": 0,
          "serverNames": ["$REALITY_DEST"],
          "privateKey": "$PRIVATE_KEY",
          "shortIds": ["$SHORT_ID"]
        }
      }
    }
  ],
  "outbounds": [
    {
      "protocol": "freedom"
    }
  ]
}
EOF

# ------------- 写入 Docker Compose -------------
cat > docker-compose.yml <<EOF
version: '3.8'
services:
  xray:
    image: teddysun/xray
    container_name: xray
    restart: always
    volumes:
      - ./xray-config.json:/etc/xray/config.json:ro
    network_mode: host

  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: always
    command: tunnel --no-autoupdate run --token $TUNNEL_TOKEN
EOF

# ------------- 启动服务 -------------
echo "[+] Starting containers..."
docker-compose up -d

# ------------- 生成节点链接并保存订阅 -------------
echo "[+] Generating VLESS Reality link..."
VLESS_LINK="vless://$UUID@$DOMAIN:$PORT?type=tcp&security=reality&encryption=none&pbk=$PUBLIC_KEY&sni=$REALITY_DEST&fp=$FINGERPRINT&alpn=h2&sid=$SHORT_ID&flow=xtls-rprx-vision#JD节点"

mkdir -p ~/sub
echo "$VLESS_LINK" > ~/sub/jd.txt

# 可选 Python3 本地订阅服务（默认8080）
cat > ~/sub/server.py <<EOF
import http.server
import socketserver

PORT = 8080
Handler = http.server.SimpleHTTPRequestHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print("Serving HTTP at port", PORT)
    httpd.serve_forever()
EOF

# 输出信息
echo
echo "=========== ✅ 部署完成 ==========="
echo "VLESS Reality 节点链接："
echo "$VLESS_LINK"
echo
echo "订阅地址（适配 Karing）:"
echo "http://$(curl -s ifconfig.me):8080/jd.txt"
echo
echo "如需启动本地订阅服务:"
echo "cd ~/sub && python3 server.py"
echo "==================================="
