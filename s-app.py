#!/bin/sh
export LANG=en_US.UTF-8

# 确保目录存在
mkdir -p "$HOME/agsb"

# 生成UUID
insuuid() {
    if [ -z "$uuid" ]; then
        if command -v uuidgen >/dev/null 2>&1; then
            uuid=$(uuidgen)
        else
            uuid=$(cat /proc/sys/kernel/random/uuid)
        fi
    fi
    echo "$uuid" > "$HOME/agsb/uuid"
    echo "UUID密码：$uuid"
}

# 获取服务器IP
v4v6() {
    v4=$(curl -s4m5 icanhazip.com -k)
    v6=$(curl -s6m5 icanhazip.com -k)
}

# 获取最佳IP
ipbest() {
    serip=$(curl -s4m5 icanhazip.com -k || curl -s6m5 icanhazip.com -k)
    if echo "$serip" | grep -q ':'; then
        server_ip="[$serip]"
    else
        server_ip="$serip"
    fi
    echo "$server_ip" > "$HOME/agsb/server_ip.log"
}

# 显示节点信息
cip() {
    v4v6
    if [ -z "$v4" ]; then
        vps_ipv4='无IPV4'
        vps_ipv6="$v6"
    elif [ -n "$v4" ] && [ -n "$v6" ]; then
        vps_ipv4="$v4"
        vps_ipv6="$v6"
    else
        vps_ipv4="$v4"
        vps_ipv6='无IPV6'
    fi
    
    echo
    echo "=========当前服务器本地IP情况========="
    echo "本地IPV4地址：$vps_ipv4"
    echo "本地IPV6地址：$vps_ipv6"
    echo
    
    ipbest
    rm -rf "$HOME/agsb/jh.txt"
    uuid=$(cat "$HOME/agsb/uuid")
    server_ip=$(cat "$HOME/agsb/server_ip.log")
    
    echo "*********************************************************"
    echo "*********************************************************"
    echo "ArgoSB脚本输出节点配置如下："
    echo
    
    # VLESS Reality节点
    if [ ! -f "$HOME/agsb/xrk/public_key" ]; then
        mkdir -p "$HOME/agsb/xrk"
        # 生成EC密钥对
        if command -v openssl >/dev/null 2>&1; then
            openssl ecparam -genkey -name prime256v1 -out "$HOME/agsb/xrk/private_key" 2>/dev/null
            openssl ec -in "$HOME/agsb/xrk/private_key" -pubout -out "$HOME/agsb/xrk/public_key" 2>/dev/null
            private_key_x=$(openssl ec -in "$HOME/agsb/xrk/private_key" -noout -text 2>/dev/null | grep priv -A 3 | tail -n 1 | tr -d '[:space:]:' | xxd -r -p | base64)
            public_key_x=$(openssl ec -in "$HOME/agsb/xrk/public_key" -noout -text 2>/dev/null | grep pub -A 5 | tail -n 1 | tr -d '[:space:]:' | xxd -r -p | base64)
        else
            # 使用预生成的密钥对
            private_key_x="COAYqKrAXaQIGL8+Wkmfe39r1tMMR80JWHVaF443XFQ="
            public_key_x="bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo="
            echo "$private_key_x" > "$HOME/agsb/xrk/private_key"
            echo "$public_key_x" > "$HOME/agsb/xrk/public_key"
        fi
        short_id_x=$(date +%s%N | sha256sum | cut -c 1-8)
        echo "$short_id_x" > "$HOME/agsb/xrk/short_id"
        ym_vl_re="www.yahoo.com"
        echo "$ym_vl_re" > "$HOME/agsb/ym_vl_re"
    else
        private_key_x=$(cat "$HOME/agsb/xrk/private_key")
        public_key_x=$(cat "$HOME/agsb/xrk/public_key")
        short_id_x=$(cat "$HOME/agsb/xrk/short_id")
        ym_vl_re=$(cat "$HOME/agsb/ym_vl_re")
    fi
    
    # VLESS Reality Vision
    port_vl_re=$(shuf -i 10000-65535 -n 1)
    echo "$port_vl_re" > "$HOME/agsb/port_vl_re"
    echo "【 vless-reality-vision 】节点信息如下："
    vl_link="vless://$uuid@$server_ip:$port_vl_re?encryption=none&flow=xtls-rprx-vision&security=reality&sni=$ym_vl_re&fp=chrome&pbk=$public_key_x&sid=$short_id_x&type=tcp&headerType=none#vl-reality-vision-$HOSTNAME"
    echo "$vl_link" >> "$HOME/agsb/jh.txt"
    echo "$vl_link"
    echo
    
    # VLESS xHTTP Reality
    port_xh=$(shuf -i 10000-65535 -n 1)
    echo "$port_xh" > "$HOME/agsb/port_xh"
    echo "【 vless-xhttp-reality 】节点信息如下："
    vl_xh_link="vless://$uuid@$server_ip:$port_xh?encryption=none&security=reality&sni=$ym_vl_re&fp=chrome&pbk=$public_key_x&sid=$short_id_x&type=xhttp&path=$uuid-xh&mode=auto#vl-xhttp-reality-$HOSTNAME"
    echo "$vl_xh_link" >> "$HOME/agsb/jh.txt"
    echo "$vl_xh_link"
    echo
    
    # Vmess WS
    port_vm_ws=$(shuf -i 10000-65535 -n 1)
    echo "$port_vm_ws" > "$HOME/agsb/port_vm_ws"
    echo "【 vmess-ws 】节点信息如下："
    vm_link="vmess://$(echo "{ \"v\": \"2\", \"ps\": \"vm-ws-$HOSTNAME\", \"add\": \"$server_ip\", \"port\": \"$port_vm_ws\", \"id\": \"$uuid\", \"aid\": \"0\", \"scy\": \"auto\", \"net\": \"ws\", \"type\": \"none\", \"host\": \"www.bing.com\", \"path\": \"/$uuid-vm?ed=2048\", \"tls\": \"\"}" | base64 -w0)"
    echo "$vm_link" >> "$HOME/agsb/jh.txt"
    echo "$vm_link"
    echo
    
    # Hysteria2
    port_hy2=$(shuf -i 10000-65535 -n 1)
    echo "$port_hy2" > "$HOME/agsb/port_hy2"
    echo "【 Hysteria2 】节点信息如下："
    hy2_link="hysteria2://$uuid@$server_ip:$port_hy2?security=tls&alpn=h3&insecure=1&sni=www.bing.com#hy2-$HOSTNAME"
    echo "$hy2_link" >> "$HOME/agsb/jh.txt"
    echo "$hy2_link"
    echo
    
    # Tuic
    port_tu=$(shuf -i 10000-65535 -n 1)
    echo "$port_tu" > "$HOME/agsb/port_tu"
    echo "【 Tuic 】节点信息如下："
    tuic5_link="tuic://$uuid:$uuid@$server_ip:$port_tu?congestion_control=bbr&udp_relay_mode=native&alpn=h3&sni=www.bing.com&allow_insecure=1#tuic-$HOSTNAME"
    echo "$tuic5_link" >> "$HOME/agsb/jh.txt"
    echo "$tuic5_link"
    echo
    
    # AnyTLS
    port_an=$(shuf -i 10000-65535 -n 1)
    echo "$port_an" > "$HOME/agsb/port_an"
    echo "【 AnyTLS 】节点信息如下："
    an_link="anytls://$uuid@$server_ip:$port_an?insecure=1#anytls-$HOSTNAME"
    echo "$an_link" >> "$HOME/agsb/jh.txt"
    echo "$an_link"
    echo
    
    # 申请临时Argo隧道
    echo "申请临时Argo隧道中……请稍等"
    if [ ! -e "$HOME/agsb/cloudflared" ]; then
        case $(uname -m) in
            aarch64) cpu=arm64;;
            x86_64) cpu=amd64;;
            *) echo "目前脚本不支持$(uname -m)架构" && exit
        esac
        curl -Lo "$HOME/agsb/cloudflared" -# --retry 2 https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$cpu
        chmod +x "$HOME/agsb/cloudflared"
    fi
    
    nohup "$HOME/agsb/cloudflared" tunnel --url http://localhost:"${port_vm_ws}" --edge-ip-version auto --no-autoupdate --protocol http2 > "$HOME/agsb/argo.log" 2>&1 &
    sleep 8
    
    argodomain=$(grep -a trycloudflare.com "$HOME/agsb/argo.log" 2>/dev/null | awk 'NR==2{print}' | awk -F// '{print $2}' | awk '{print $1}')
    
    if [ -n "$argodomain" ]; then
        echo "Argo临时隧道申请成功"
        
        # 生成基于Argo的节点
        vmatls_link1="vmess://$(echo "{ \"v\": \"2\", \"ps\": \"vmess-ws-tls-argo-$HOSTNAME-443\", \"add\": \"104.16.0.0\", \"port\": \"443\", \"id\": \"$uuid\", \"aid\": \"0\", \"scy\": \"auto\", \"net\": \"ws\", \"type\": \"none\", \"host\": \"$argodomain\", \"path\": \"/$uuid-vm?ed=2048\", \"tls\": \"tls\", \"sni\": \"$argodomain\", \"alpn\": \"\", \"fp\": \"\"}" | base64 -w0)"
        echo "$vmatls_link1" >> "$HOME/agsb/jh.txt"
        
        vma_link7="vmess://$(echo "{ \"v\": \"2\", \"ps\": \"vmess-ws-argo-$HOSTNAME-80\", \"add\": \"104.21.0.0\", \"port\": \"80\", \"id\": \"$uuid\", \"aid\": \"0\", \"scy\": \"auto\", \"net\": \"ws\", \"type\": \"none\", \"host\": \"$argodomain\", \"path\": \"/$uuid-vm?ed=2048\", \"tls\": \"\"}" | base64 -w0)"
        echo "$vma_link7" >> "$HOME/agsb/jh.txt"
        
        argoshow=$(echo "Vmess主协议端口(Argo临时隧道端口)：$port_vm_ws\n当前Argo临时域名：$argodomain\n1、443端口的vmess-ws-tls-argo节点\n$vmatls_link1\n\n2、80端口的vmess-ws-argo节点\n$vma_link7\n")
    else
        echo "Argo临时隧道申请失败，请稍后再试"
        argoshow=""
    fi
    
    echo "---------------------------------------------------------"
    echo -e "$argoshow"
    echo "---------------------------------------------------------"
    echo "聚合节点信息，请查看$HOME/agsb/jh.txt文件或者运行cat $HOME/agsb/jh.txt进行复制"
    echo "---------------------------------------------------------"
    echo
}

# 主程序
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo "甬哥Github项目 ：github.com/yonggekkk"
echo "ArgoSB一键无交互极简脚本 - 临时节点生成版"
echo "当前版本：V25.7.23"
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"

echo "VPS系统：$(cat /etc/redhat-release 2>/dev/null || cat /etc/os-release 2>/dev/null | grep -i pretty_name | cut -d \" -f2)"
echo "CPU架构：$(uname -m)"
echo "开始生成临时节点信息…………" && sleep 2

# 清理旧进程
for P in /proc/[0-9]*; do 
    if [ -L "$P/exe" ]; then 
        TARGET=$(readlink -f "$P/exe" 2>/dev/null); 
        if echo "$TARGET" | grep -qE '/agsb/c|/agsb/s|/agsb/x'; then 
            PID=$(basename "$P"); 
            kill "$PID" 2>/dev/null; 
        fi; 
    fi; 
done
kill -15 $(pgrep -f 'agsb/s' 2>/dev/null) $(pgrep -f 'agsb/c' 2>/dev/null) $(pgrep -f 'agsb/x' 2>/dev/null) >/dev/null 2>&1

# 确保必要工具存在
command -v curl >/dev/null 2>&1 || { echo "请先安装curl"; exit 1; }
command -v base64 >/dev/null 2>&1 || { echo "请先安装base64工具"; exit 1; }

# 生成UUID
insuuid

# 显示节点
cip
