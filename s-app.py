#!/bin/sh

# 确保目录存在
mkdir -p "$HOME/agsb"

# 生成UUID
generate_uuid() {
    if command -v uuidgen >/dev/null 2>&1; then
        uuid=$(uuidgen)
    else
        uuid=$(cat /proc/sys/kernel/random/uuid)
    fi
    echo "$uuid" > "$HOME/agsb/uuid"
    echo "UUID: $uuid"
}

# 获取服务器IP
get_server_ip() {
    ip=$(curl -s4m5 icanhazip.com -k || curl -s6m5 icanhazip.com -k)
    if echo "$ip" | grep -q ':'; then
        server_ip="[$ip]"
    else
        server_ip="$ip"
    fi
    echo "$server_ip" > "$HOME/agsb/server_ip.log"
}

# 生成Reality密钥
generate_reality_keys() {
    mkdir -p "$HOME/agsb/xrk"
    
    if command -v openssl >/dev/null 2>&1; then
        # 生成EC密钥对
        openssl ecparam -genkey -name prime256v1 -out "$HOME/agsb/xrk/private_key" 2>/dev/null
        openssl ec -in "$HOME/agsb/xrk/private_key" -pubout -out "$HOME/agsb/xrk/public_key" 2>/dev/null
        
        # 提取Base64格式的密钥
        private_key=$(openssl ec -in "$HOME/agsb/xrk/private_key" -noout -text 2>/dev/null | grep priv -A 3 | tail -n 1 | tr -d '[:space:]:' | xxd -r -p | base64)
        public_key=$(openssl ec -in "$HOME/agsb/xrk/public_key" -noout -text 2>/dev/null | grep pub -A 5 | tail -n 1 | tr -d '[:space:]:' | xxd -r -p | base64)
        
        echo "$private_key" > "$HOME/agsb/xrk/private_key_b64"
        echo "$public_key" > "$HOME/agsb/xrk/public_key_b64"
    else
        # 使用预生成的密钥对（不推荐，仅用于演示）
        private_key="COAYqKrAXaQIGL8+Wkmfe39r1tMMR80JWHVaF443XFQ="
        public_key="bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo="
        echo "$private_key" > "$HOME/agsb/xrk/private_key_b64"
        echo "$public_key" > "$HOME/agsb/xrk/public_key_b64"
    fi
    
    short_id=$(date +%s%N | sha256sum | cut -c 1-8)
    echo "$short_id" > "$HOME/agsb/xrk/short_id"
    echo "Reality公钥: $public_key"
}

# 申请Cloudflare Argo隧道
create_argo_tunnel() {
    echo "申请Cloudflare Argo临时隧道..."
    
    # 下载cloudflared客户端
    if [ ! -e "$HOME/agsb/cloudflared" ]; then
        case $(uname -m) in
            aarch64) cpu=arm64;;
            x86_64) cpu=amd64;;
            *) echo "不支持的架构: $(uname -m)" && return 1
        esac
        
        curl -Lo "$HOME/agsb/cloudflared" -# --retry 2 https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$cpu
        chmod +x "$HOME/agsb/cloudflared"
    fi
    
    # 启动隧道并获取域名
    nohup "$HOME/agsb/cloudflared" tunnel --url http://localhost:${vmess_port} --edge-ip-version auto --no-autoupdate --protocol http2 > "$HOME/agsb/argo.log" 2>&1 &
    
    # 等待隧道启动
    sleep 8
    
    argo_domain=$(grep -a trycloudflare.com "$HOME/agsb/argo.log" 2>/dev/null | awk 'NR==2{print}' | awk -F// '{print $2}' | awk '{print $1}')
    
    if [ -n "$argo_domain" ]; then
        echo "Argo域名: $argo_domain"
        echo "$argo_domain" > "$HOME/agsb/argo_domain"
        return 0
    else
        echo "申请Argo隧道失败"
        return 1
    fi
}

# 生成节点配置
generate_nodes() {
    uuid=$(cat "$HOME/agsb/uuid")
    server_ip=$(cat "$HOME/agsb/server_ip.log")
    public_key=$(cat "$HOME/agsb/xrk/public_key_b64")
    short_id=$(cat "$HOME/agsb/xrk/short_id")
    reality_host="www.yahoo.com"
    
    # 清空并创建节点文件
    > "$HOME/agsb/nodes.txt"
    
    # 生成随机端口
    reality_port=$(shuf -i 10000-65535 -n 1)
    vmess_port=$(shuf -i 10000-65535 -n 1)
    hysteria_port=$(shuf -i 10000-65535 -n 1)
    
    # VLESS Reality节点
    echo "【VLESS Reality】"
    vless_link="vless://${uuid}@${server_ip}:${reality_port}?encryption=none&security=reality&sni=${reality_host}&fp=chrome&pbk=${public_key}&sid=${short_id}&type=tcp&headerType=none#Reality_${server_ip}"
    echo "$vless_link"
    echo "$vless_link" >> "$HOME/agsb/nodes.txt"
    echo
    
    # VMess WS节点
    echo "【VMess WS】"
    vmess_config="{\"v\":\"2\",\"ps\":\"VMess_${server_ip}\",\"add\":\"${server_ip}\",\"port\":\"${vmess_port}\",\"id\":\"${uuid}\",\"aid\":\"0\",\"scy\":\"auto\",\"net\":\"ws\",\"type\":\"none\",\"host\":\"www.bing.com\",\"path\":\"/${uuid}-ws\",\"tls\":\"\"}"
    vmess_link="vmess://$(echo "$vmess_config" | base64 -w0)"
    echo "$vmess_link"
    echo "$vmess_link" >> "$HOME/agsb/nodes.txt"
    echo
    
    # Hysteria2节点
    echo "【Hysteria2】"
    hysteria_link="hysteria2://${uuid}@${server_ip}:${hysteria_port}?security=tls&alpn=h3&insecure=1&sni=www.bing.com#Hysteria2_${server_ip}"
    echo "$hysteria_link"
    echo "$hysteria_link" >> "$HOME/agsb/nodes.txt"
    echo
    
    # 检查是否成功获取Argo域名
    if [ -f "$HOME/agsb/argo_domain" ]; then
        argo_domain=$(cat "$HOME/agsb/argo_domain")
        
        # 基于Argo的VMess节点
        echo "【VMess WS TLS (Argo)】"
        argo_config="{\"v\":\"2\",\"ps\":\"VMess_Argo_${argo_domain}\",\"add\":\"104.16.0.0\",\"port\":\"443\",\"id\":\"${uuid}\",\"aid\":\"0\",\"scy\":\"auto\",\"net\":\"ws\",\"type\":\"none\",\"host\":\"${argo_domain}\",\"path\":\"/${uuid}-ws\",\"tls\":\"tls\",\"sni\":\"${argo_domain}\"}"
        argo_link="vmess://$(echo "$argo_config" | base64 -w0)"
        echo "$argo_link"
        echo "$argo_link" >> "$HOME/agsb/nodes.txt"
        echo
        
        echo "【VMess WS (Argo HTTP)】"
        argo_http_config="{\"v\":\"2\",\"ps\":\"VMess_Argo_HTTP_${argo_domain}\",\"add\":\"104.21.0.0\",\"port\":\"80\",\"id\":\"${uuid}\",\"aid\":\"0\",\"scy\":\"auto\",\"net\":\"ws\",\"type\":\"none\",\"host\":\"${argo_domain}\",\"path\":\"/${uuid}-ws\",\"tls\":\"\"}"
        argo_http_link="vmess://$(echo "$argo_http_config" | base64 -w0)"
        echo "$argo_http_link"
        echo "$argo_http_link" >> "$HOME/agsb/nodes.txt"
        echo
    fi
    
    echo "节点已保存到: $HOME/agsb/nodes.txt"
}

# 主程序
echo "======================================"
echo "   ArgoSB 临时节点生成工具   "
echo "======================================"

echo "检查必要的依赖..."
for cmd in curl base64; do
    command -v $cmd >/dev/null 2>&1 || { echo "需要安装 $cmd"; exit 1; }
done

echo "清理旧进程..."
pkill -f "cloudflared tunnel" >/dev/null 2>&1

echo "生成UUID..."
generate_uuid

echo "获取服务器IP..."
get_server_ip

echo "生成Reality密钥..."
generate_reality_keys

echo "创建Argo隧道..."
create_argo_tunnel

echo "生成节点配置..."
generate_nodes

echo "======================================"
echo "  临时节点生成完成，享受高速连接！  "
echo "======================================"
