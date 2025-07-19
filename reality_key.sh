#!/bin/bash

UUID=$(uuidgen)
KEYS=$(docker run --rm ghcr.io/sagernet/sing-box:latest generate reality-keypair)
PRIVATE_KEY=$(echo "$KEYS" | grep private | awk '{print $3}')
PUBLIC_KEY=$(echo "$KEYS" | grep public | awk '{print $3}')
SHORT_ID="abcdef12"
DOMAIN="www.cloudflare.com"

cat > config.json <<EOF
{
  "log": {
    "level": "info",
    "output": "console"
  },
  "inbounds": [
    {
      "type": "vless",
      "listen": "::",
      "listen_port": 443,
      "users": [
        {
          "uuid": "$UUID"
        }
      ],
      "tls": {
        "enabled": true,
        "server_name": "$DOMAIN",
        "reality": {
          "enabled": true,
          "handshake": {
            "server": "$DOMAIN",
            "server_port": 443
          },
          "private_key": "$PRIVATE_KEY",
          "short_id": [
            "$SHORT_ID"
          ]
        }
      }
    }
  ],
  "outbounds": [
    {
      "type": "direct"
    }
  ]
}
EOF

echo -e "\n✅ Reality 密钥与配置生成成功"
echo "UUID: $UUID"
echo "PublicKey: $PUBLIC_KEY"
echo "Short ID: $SHORT_ID"
echo "SNI (伪装域名): $DOMAIN"
echo "订阅链接如下："
echo -e "\nvless://$UUID@<YOUR_IP>:443?encryption=none&flow=&type=tcp&security=reality&sni=$DOMAIN&fp=chrome&pbk=$PUBLIC_KEY&sid=$SHORT_ID#RealityNode"
