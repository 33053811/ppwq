#!/bin/bash
set -e

echo "[1/4] 检查 Docker & Docker Compose ..."
if ! command -v docker >/dev/null 2>&1; then
    echo "❌ 请先安装 Docker"
    exit 1
fi
if ! command -v docker-compose >/dev/null 2>&1; then
    echo "❌ 请先安装 docker-compose"
    exit 1
fi

echo "[2/4] 启动服务 ..."
docker-compose up -d --build

echo "[3/4] 等待服务启动 ..."
sleep 5

echo "[4/4] 部署完成 ✅"
echo "Web访问地址: http://<服务器IP>:8080"
