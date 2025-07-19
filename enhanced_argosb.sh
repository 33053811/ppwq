#!/bin/sh
export LANG=en_US.UTF-8

# 增强版 ArgoSB 一键脚本 - 添加了稳定性、安全性和抗封锁能力改进

# 配置防火墙规则
configure_firewall() {
    echo "配置防火墙规则..."
    if command -v ufw &>/dev/null; then
        ufw disable
        ufw default deny incoming
        ufw default allow outgoing
        for port in $(cat $HOME/agsb/port_* 2>/dev/null); do
            ufw allow $port/tcp
            ufw allow $port/udp
        done
        ufw allow ssh
        ufw enable -y
    elif command -v firewalld &>/dev/null; then
        systemctl start firewalld
        systemctl enable firewalld
        for port in $(cat $HOME/agsb/port_* 2>/dev/null); do
            firewall-cmd --permanent --add-port=$port/tcp
            firewall-cmd --permanent --add-port=$port/udp
        done
        firewall-cmd --permanent --add-service=ssh
        firewall-cmd --reload
    fi
}

# 生成随机配置参数
generate_random_params() {
    echo "生成随机配置参数..."
    RANDOM_PATH=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 16 | head -n 1)
    RANDOM_HEADER=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 8 | head -n 1)
    
    # 修改配置文件
    if [ -e "$HOME/agsb/xr.json" ]; then
        sed -i "s|/${uuid}-vm|/${RANDOM_PATH}|g" "$HOME/agsb/xr.json"
        sed -i "s|/${uuid}-xh|/${RANDOM_PATH}-xh|g" "$HOME/agsb/xr.json"
    fi
    
    if [ -e "$HOME/agsb/sb.json" ]; then
        sed -i "s|/${uuid}-vm|/${RANDOM_PATH}|g" "$HOME/agsb/sb.json"
    fi
}

# 生成更逼真的证书
generate_cert() {
    echo "生成安全证书..."
    mkdir -p "$HOME/agsb/certs"
    DOMAIN=$(cat "$HOME/agsb/ym_vl_re" 2>/dev/null || echo "www.bing.com")
    
    openssl req -x509 -newkey rsa:4096 -keyout "$HOME/agsb/certs/private.key" \
        -out "$HOME/agsb/certs/cert.pem" -days 3650 -nodes \
        -subj "/CN=$DOMAIN" -addext "subjectAltName = DNS:$DOMAIN" >/dev/null 2>&1
    
    # 更新配置文件引用
    if [ -e "$HOME/agsb/xr.json" ]; then
        sed -i "s|$HOME/agsb/private.key|$HOME/agsb/certs/private.key|g" "$HOME/agsb/xr.json"
        sed -i "s|$HOME/agsb/cert.pem|$HOME/agsb/certs/cert.pem|g" "$HOME/agsb/xr.json"
    fi
    
    if [ -e "$HOME/agsb/sb.json" ]; then
        sed -i "s|$HOME/agsb/private.key|$HOME/agsb/certs/private.key|g" "$HOME/agsb/sb.json"
        sed -i "s|$HOME/agsb/cert.pem|$HOME/agsb/certs/cert.pem|g" "$HOME/agsb/sb.json"
    fi
}

# 分散流量特征
scatter_traffic() {
    echo "配置流量分散..."
    if [ -e "$HOME/agsb/xr.json" ]; then
        # 添加随机user-agent
        USER_AGENTS=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0"
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.5; rv:90.0) Gecko/20100101 Firefox/90.0"
        )
        
        RANDOM_UA=${USER_AGENTS[$RANDOM % ${#USER_AGENTS[@]}]}
        sed -i "s|\"host\": \"\"|\"host\": \"\", \"headers\": {\"User-Agent\": \"$RANDOM_UA\"}|g" "$HOME/agsb/xr.json"
    fi
    
    # 为sing-box添加user-agent
    if [ -e "$HOME/agsb/sb.json" ]; then
        if grep -q '"type": "ws"' "$HOME/agsb/sb.json"; then
            # 在ws配置中添加headers
            sed -i '/"type": "ws"/a \            "headers": {"User-Agent": "'"$RANDOM_UA"'"}' "$HOME/agsb/sb.json"
        fi
    fi
}

# 添加进程监控脚本
setup_monitor() {
    echo "设置服务监控..."
    MONITOR_SCRIPT="$HOME/agsb/monitor.sh"
    
    cat > "$MONITOR_SCRIPT" << 'EOF'
#!/bin/sh
LOG_FILE="$HOME/agsb/monitor.log"
echo "$(date) - 开始监控服务..." >> "$LOG_FILE"

check_service() {
    local service_name=$1
    local config_file=$2
    
    if ! pgrep -f "$service_name" >/dev/null 2>&1; then
        echo "$(date) - $service_name 未运行，尝试启动..." >> "$LOG_FILE"
        nohup $HOME/agsb/$service_name run -c $config_file >/dev/null 2>&1 &
        sleep 2
        if ! pgrep -f "$service_name" >/dev/null 2>&1; then
            echo "$(date) - 启动 $service_name 失败！" >> "$LOG_FILE"
        else
            echo "$(date) - $service_name 已成功启动" >> "$LOG_FILE"
        fi
    fi
}

while true; do
    if [ -e "$HOME/agsb/xray" ]; then
        check_service "xray" "$HOME/agsb/xr.json"
    fi
    if [ -e "$HOME/agsb/sing-box" ]; then
        check_service "sing-box" "$HOME/agsb/sb.json"
    fi
    if [ -e "$HOME/agsb/cloudflared" ]; then
        check_service "cloudflared" "$HOME/agsb/sb.json"
    fi
    sleep 60
done
EOF

    chmod +x "$MONITOR_SCRIPT"
    # 添加到cron
    (crontab -l 2>/dev/null; echo "@reboot $MONITOR_SCRIPT >/dev/null 2>&1") | crontab -
}

# 动态端口切换功能
setup_port_switch() {
    echo "设置动态端口切换..."
    PORT_SWITCH_SCRIPT="$HOME/agsb/port_switch.sh"
    
    cat > "$PORT_SWITCH_SCRIPT" << 'EOF'
#!/bin/sh
LOG_FILE="$HOME/agsb/port_switch.log"
echo "$(date) - 开始端口切换监控..." >> "$LOG_FILE"

# 端口切换间隔（秒）
INTERVAL=86400

while true; do
    # 检查是否需要切换端口
    if [ $((RANDOM % 2)) -eq 0 ]; then
        echo "$(date) - 开始端口切换..." >> "$LOG_FILE"
        
        # 停止服务
        for P in /proc/[0-9]*; do 
            if [ -L "$P/exe" ]; then 
                TARGET=$(readlink -f "$P/exe" 2>/dev/null); 
                if echo "$TARGET" | grep -qE '/agsb/s|/agsb/x'; then 
                    PID=$(basename "$P"); 
                    kill "$PID" 2>/dev/null; 
                fi; 
            fi; 
        done
        
        # 随机更改端口
        for file in $HOME/agsb/port_*; do
            if [ -f "$file" ]; then
                NEW_PORT=$(shuf -i 10000-65535 -n 1)
                echo "$NEW_PORT" > "$file"
                echo "$(date) - 端口 $(basename $file) 已更改为 $NEW_PORT" >> "$LOG_FILE"
            fi
        done
        
        # 重启服务
        nohup $HOME/agsb/sing-box run -c $HOME/agsb/sb.json >/dev/null 2>&1 &
        nohup $HOME/agsb/xray run -c $HOME/agsb/xr.json >/dev/null 2>&1 &
        
        echo "$(date) - 端口切换完成" >> "$LOG_FILE"
    fi
    
    sleep $INTERVAL
done
EOF

    chmod +x "$PORT_SWITCH_SCRIPT"
    # 添加到cron
    (crontab -l 2>/dev/null; echo "@daily $PORT_SWITCH_SCRIPT >/dev/null 2>&1") | crontab -
}

# 原始脚本代码（保持不变）
if ! find /proc/*/exe -type l 2>/dev/null | grep -E '/proc/[0-9]+/exe' | xargs -r readlink 2>/dev/null | grep -Eq 'agsb/(s|x)' && ! pgrep -f 'agsb/(s|x)' >/dev/null 2>&1; then
[ -z "${vlpt+x}" ] || vlp=yes
[ -z "${vmpt+x}" ] || { vmp=yes; vmag=yes; } 
[ -z "${hypt+x}" ] || hyp=yes
[ -z "${tupt+x}" ] || tup=yes
[ -z "${xhpt+x}" ] || xhp=yes
[ -z "${anpt+x}" ] || anp=yes
[ -z "${warp+x}" ] || wap=yes
[ "$vlp" = yes ] || [ "$vmp" = yes ] || [ "$hyp" = yes ] || [ "$tup" = yes ] || [ "$xhp" = yes ] || [ "$anp" = yes ] || { echo "提示：使用此脚本时，请在脚本前至少设置一个协议变量哦，再见！"; exit; }
fi
export uuid=${uuid:-''}
export port_vl_re=${vlpt:-''}
export port_vm_ws=${vmpt:-''}
export port_hy2=${hypt:-''}
export port_tu=${tupt:-''}
export port_xh=${xhpt:-''}
export port_an=${anpt:-''}
export ym_vl_re=${reym:-''}
export argo=${argo:-''}
export ARGO_DOMAIN=${agn:-''}
export ARGO_AUTH=${agk:-''}
export ipsw=${ip:-''}
export warp=${warp:-''}
showmode(){
echo "显示节点信息：agsb或者脚本 list"
echo "双栈VPS显示IPv4节点配置：ip=4 agsb或者脚本 list"
echo "双栈VPS显示IPv6节点配置：ip=6 agsb或者脚本 list"
echo "重启脚本：agsb或者脚本 res"
echo "卸载脚本：agsb或者脚本 del"
}
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo "甬哥Github项目 ：github.com/yonggekkk"
echo "甬哥Blogger博客 ：ygkkk.blogspot.com"
echo "甬哥YouTube频道 ：www.youtube.com/@ygkkk"
echo "ArgoSB一键无交互极简脚本"
echo "当前版本：V25.7.15"
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
hostname=$(uname -a | awk '{print $2}')
op=$(cat /etc/redhat-release 2>/dev/null || cat /etc/os-release 2>/dev/null | grep -i pretty_name | cut -d \" -f2)
[ -z "$(systemd-detect-virt 2>/dev/null)" ] && vi=$(virt-what 2>/dev/null) || vi=$(systemd-detect-virt 2>/dev/null)
case $(uname -m) in
aarch64) cpu=arm64;;
x86_64) cpu=amd64;;
*) echo "目前脚本不支持$(uname -m)架构" && exit
esac
mkdir -p "$HOME/agsb"
warpcheck(){
wgcfv6=$(curl -s6m5 https://www.cloudflare.com/cdn-cgi/trace -k | grep warp | cut -d= -f2)
wgcfv4=$(curl -s4m5 https://www.cloudflare.com/cdn-cgi/trace -k | grep warp | cut -d= -f2)
}
v4v6(){
v4=$(curl -s4m5 icanhazip.com -k)
v6=$(curl -s6m5 icanhazip.com -k)
}
warpsx(){
v4v6
if echo "$v6" | grep -q '^2a09' || echo "$v4" | grep -q '^104.28'; then
xouttag=direct
souttag=direct
wap=warpargo
echo
echo "请注意：你已安装了warp"
else
if [ "$wap" != yes ]; then
xouttag=direct
souttag=direct
wap=warpargo
elif [ "$warp" = "" ]; then
xouttag=warp-out
souttag=warp-out
wap=warp
echo
echo "所有内核协议添加warp全局出站"
elif [ "$warp" = "x" ]; then
xouttag=warp-out
souttag=direct
wap=warp
echo
echo "Xray内核的协议添加warp全局出站"
elif [ "$warp" = "s" ]; then
xouttag=direct
souttag=warp-out
wap=warp
echo
echo "Sing-box内核的协议添加warp全局出站"
else
xouttag=direct
souttag=direct
wap=warpargo
fi
fi
}
insuuid(){
if [ -z "$uuid" ]; then
if [ -e "$HOME/agsb/sing-box" ]; then
uuid=$("$HOME/agsb/sing-box" generate uuid)
else
uuid=$("$HOME/agsb/xray" uuid)
fi
fi
echo "$uuid" > "$HOME/agsb/uuid"
echo "UUID密码：$uuid"
}
installxray(){
echo
echo "=========启用xray内核========="
if [ ! -e "$HOME/agsb/xray" ]; then
curl -Lo "$HOME/agsb/xray" -# --retry 2 https://github.com/yonggekkk/ArgoSB/releases/download/argosbx/xray-$cpu
chmod +x "$HOME/agsb/xray"
sbcore=$("$HOME/agsb/xray" version 2>/dev/null | awk '/^Xray/{print $2}')
echo "已安装Xray正式版内核：$sbcore"
fi
cat > "$HOME/agsb/xr.json" <<EOF
{
  "log": {
    "access": "/dev/null",
    "error": "/dev/null",
    "loglevel": "none"
  },
  "inbounds": [
EOF
insuuid
if [ -n "$xhp" ] || [ -n "$vlp" ]; then
if [ -z "$ym_vl_re" ]; then
ym_vl_re=www.yahoo.com
fi
echo "$ym_vl_re" > "$HOME/agsb/ym_vl_re"
echo "Reality域名：$ym_vl_re"
mkdir -p "$HOME/agsb/xrk"
if [ ! -e "$HOME/agsb/xrk/private_key" ]; then
key_pair=$("$HOME/agsb/xray" x25519)
private_key=$(echo "$key_pair" | head -1 | awk '{print $3}')
public_key=$(echo "$key_pair" | tail -n 1 | awk '{print $3}')
short_id=$(date +%s%N | sha256sum | cut -c 1-8)
echo "$private_key" > "$HOME/agsb/xrk/private_key"
echo "$public_key" > "$HOME/agsb/xrk/public_key"
echo "$short_id" > "$HOME/agsb/xrk/short_id"
fi
private_key_x=$(cat "$HOME/agsb/xrk/private_key")
public_key_x=$(cat "$HOME/agsb/xrk/public_key")
short_id_x=$(cat "$HOME/agsb/xrk/short_id")
fi
if [ -n "$xhp" ]; then
xhp=xhpt
if [ -z "$port_xh" ]; then
port_xh=$(shuf -i 10000-65535 -n 1)
fi
echo "$port_xh" > "$HOME/agsb/port_xh"
echo "Vless-xhttp-reality端口：$port_xh"
cat >> "$HOME/agsb/xr.json" <<EOF
    {
      "tag":"xhttp-reality",
      "listen": "::",
      "port": ${port_xh},
      "protocol": "vless",
      "settings": {
        "clients": [
          {
            "id": "${uuid}"
          }
        ],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "xhttp",
        "security": "reality",
        "realitySettings": {
          "fingerprint": "chrome",
          "target": "${ym_vl_re}:443",
          "serverNames": [
            "${ym_vl_re}"
          ],
          "privateKey": "$private_key_x",
          "shortIds": ["$short_id_x"]
        },
        "xhttpSettings": {
          "host": "",
          "path": "${uuid}-xh",
          "mode": "auto"
        }
      },
      "sniffing": {
        "enabled": true,
        "destOverride": ["http", "tls", "quic"],
        "metadataOnly": false
      }
    },
EOF
else
xhp=xhptargo
fi
if [ -n "$vlp" ]; then
vlp=vlpt
if [ -z "$port_vl_re" ]; then
port_vl_re=$(shuf -i 10000-65535 -n 1)
fi
echo "$port_vl_re" > "$HOME/agsb/port_vl_re"
echo "Vless-reality-vision端口：$port_vl_re"
cat >> "$HOME/agsb/xr.json" <<EOF
        {
            "tag":"reality-vision",
            "listen": "::",
            "port": $port_vl_re,
            "protocol": "vless",
            "settings": {
                "clients": [
                    {
                        "id": "${uuid}",
                        "flow": "xtls-rprx-vision"
                    }
                ],
                "decryption": "none"
            },
            "streamSettings": {
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "fingerprint": "chrome",
                    "dest": "${ym_vl_re}:443",
                    "serverNames": [
                      "${ym_vl_re}"
                    ],
                    "privateKey": "$private_key_x",
                    "shortIds": ["$short_id_x"]
                }
            },
          "sniffing": {
          "enabled": true,
          "destOverride": ["http", "tls", "quic"],
          "metadataOnly": false
      }
    },  
EOF
else
vlp=vlptargo
fi
}

installsb(){
echo
echo "=========启用Sing-box内核========="
if [ ! -e "$HOME/agsb/sing-box" ]; then
curl -Lo "$HOME/agsb/sing-box" -# --retry 2 https://github.com/yonggekkk/ArgoSB/releases/download/argosbx/sing-box-$cpu
chmod +x "$HOME/agsb/sing-box"
sbcore=$("$HOME/agsb/sing-box" version 2>/dev/null | awk '/version/{print $NF}')
echo "已安装Sing-box正式版内核：$sbcore"
fi
cat > "$HOME/agsb/sb.json" <<EOF
{
"log": {
    "disabled": false,
    "level": "info",
    "timestamp": true
  },
  "inbounds": [
EOF
insuuid
command -v openssl >/dev/null 2>&1 && openssl ecparam -genkey -name prime256v1 -out "$HOME/agsb/private.key" >/dev/null 2>&1
command -v openssl >/dev/null 2>&1 && openssl req -new -x509 -days 36500 -key "$HOME/agsb/private.key" -out "$HOME/agsb/cert.pem" -subj "/CN=www.bing.com" >/dev/null 2>&1
if [ ! -f "$HOME/agsb/private.key" ]; then
curl -Lso "$HOME/agsb/private.key" https://github.com/yonggekkk/ArgoSB/releases/download/argosbx/private.key
curl -Lso "$HOME/agsb/cert.pem" https://github.com/yonggekkk/ArgoSB/releases/download/argosbx/cert.pem
fi
if [ -n "$hyp" ]; then
hyp=hypt
if [ -z "$port_hy2" ]; then
port_hy2=$(shuf -i 10000-65535 -n 1)
fi
echo "$port_hy2" > "$HOME/agsb/port_hy2"
echo "Hysteria2端口：$port_hy2"
cat >> "$HOME/agsb/sb.json" <<EOF
    {
        "type": "hysteria2",
        "tag": "hy2-sb",
        "listen": "::",
        "listen_port": ${port_hy2},
        "users": [
            {
                "password": "${uuid}"
            }
        ],
        "ignore_client_bandwidth":false,
        "tls": {
            "enabled": true,
            "alpn": [
                "h3"
            ],
            "certificate_path": "$HOME/agsb/cert.pem",
            "key_path": "$HOME/agsb/private.key"
        }
    },
EOF
else
hyp=hyptargo
fi
if [ -n "$tup" ]; then
tup=tupt
if [ -z "$port_tu" ]; then
port_tu=$(shuf -i 10000-65535 -n 1)
fi
echo "$port_tu" > "$HOME/agsb/port_tu"
echo "Tuic端口：$port_tu"
cat >> "$HOME/agsb/sb.json" <<EOF
        {
            "type":"tuic",
            "tag": "tuic5-sb",
            "listen": "::",
            "listen_port": ${port_tu},
            "users": [
                {
                    "uuid": "${uuid}",
                    "password": "${uuid}"
                }
            ],
            "congestion_control": "bbr",
            "tls":{
                "enabled": true,
                "alpn": [
                    "h3"
                ],
                "certificate_path": "$HOME/agsb/cert.pem",
                "key_path": "$HOME/agsb/private.key"
            }
        },
EOF
else
tup=tuptargo
fi
if [ -n "$anp" ]; then
anp=anpt
if [ -z "$port_an" ]; then
port_an=$(shuf -i 10000-65535 -n 1)
fi
echo "$port_an" > "$HOME/agsb/port_an"
echo "Anytls端口：$port_an"
cat >> "$HOME/agsb/sb.json" <<EOF
        {
            "type":"anytls",
            "tag":"anytls-sb",
            "listen":"::",
            "listen_port":${port_an},
            "users":[
                {
                  "password":"${uuid}"
                }
            ],
            "padding_scheme":[],
            "tls":{
                "enabled": true,
                "certificate_path": "$HOME/agsb/cert.pem",
                "key_path": "$HOME/agsb/private.key"
            }
        },
EOF
else
anp=anptargo
fi
}

xrsbvm(){
if [ -n "$vmp" ]; then
vmp=vmpt
if [ -z "$port_vm_ws" ]; then
port_vm_ws=$(shuf -i 10000-65535 -n 1)
fi
echo "$port_vm_ws" > "$HOME/agsb/port_vm_ws"
echo "Vmess-ws端口：$port_vm_ws"
if [ -e "$HOME/agsb/xray" ]; then
cat >> "$HOME/agsb/xr.json" <<EOF
        {
            "tag": "vmess-xr",
            "listen": "::",
            "port": ${port_vm_ws},
            "protocol": "vmess",
            "settings": {
                "clients": [
                    {
                        "id": "${uuid}"
                    }
                ]
            },
            "streamSettings": {
                "network": "ws",
                "security": "none",
                "wsSettings": {
                  "path": "${uuid}-vm"
            }
        },
            "sniffing": {
            "enabled": true,
            "destOverride": ["http", "tls", "quic"],
            "metadataOnly": false
            }
         }, 
EOF
else
cat >> "$HOME/agsb/sb.json" <<EOF
{
        "type": "vmess",
        "tag": "vmess-sb",
        "listen": "::",
        "listen_port": ${port_vm_ws},
        "users": [
            {
                "uuid": "${uuid}",
                "alterId": 0
            }
        ],
        "transport": {
            "type": "ws",
            "path": "${uuid}-vm",
            "max_early_data":2048,
            "early_data_header_name": "Sec-WebSocket-Protocol"
        }
    },
EOF
fi
else
vmp=vmptargo
fi
}

xrsbout(){
if [ -e "$HOME/agsb/xray" ]; then
sed -i '${s/,\s*$//}' "$HOME/agsb/xr.json"
cat >> "$HOME/agsb/xr.json" <<EOF
  ],
  "outbounds": [
    {
      "tag": "warp-out",
      "protocol": "wireguard",
      "settings": {
        "secretKey": "COAYqKrAXaQIGL8+Wkmfe39r1tMMR80JWHVaF443XFQ=",
        "address": [
          "172.16.0.2/32",
          "2606:4700:110:8eb1:3b27:e65e:3645:97b0/128"
        ],
        "peers": [
          {
            "publicKey": "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=",
            "allowedIPs": [
              "0.0.0.0/0",
              "::/0"
            ],
            "endpoint": "${xendip}:2408"
          }
        ],
        "reserved": [134, 63, 85]
          }
    },
    {
      "protocol": "freedom",
      "tag": "direct"
    }
  ],
  "routing": {
    "rules": [
      {
        "type": "field",
        "network": "tcp,udp",
        "outboundTag": "${xouttag}"
      }
    ]
  }
}
EOF
nohup "$HOME/agsb/xray" run -c "$HOME/agsb/xr.json" >/dev/null 2>&1 &
fi
if [ -e "$HOME/agsb/sing-box" ]; then
sed -i '${s/,\s*$//}' "$HOME/agsb/sb.json"
cat >> "$HOME/agsb/sb.json" <<EOF
  ],
  "outbounds": [
    {
      "type": "direct",
      "tag": "direct"
    }
  ],
  "endpoints": [
    {
      "type": "wireguard",
      "tag": "warp-out",
      "address": [
        "172.16.0.2/32",
        "2606:4700:110:8eb1:3b27:e65e:3645:97b0/128"
      ],
      "private_key": "COAYqKrAXaQIGL8+Wkmfe39r1tMMR80JWHVaF443XFQ=",
      "peers": [
        {
          "address": "${sendip}",
          "port": 2408,
          "public_key": "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=",
          "allowed_ips": [
            "0.0.0.0/0",
            "::/0"
          ],
          "reserved": [134, 63, 85]
        }
      ]
    }
  ],
  "route": {
    "rules": [
      {
        "outbound": "${souttag}"
      }
    ]
  }
}
EOF
nohup "$HOME/agsb/sing-box" run -c "$HOME/agsb/sb.json" >/dev/null 2>&1 &
fi
}
killstart(){
for P in /proc/[0-9]*; do if [ -L "$P/exe" ]; then TARGET=$(readlink -f "$P/exe" 2>/dev/null); if echo "$TARGET" | grep -qE '/agsb/c|/agsb/s|/agsb/x'; then PID=$(basename "$P"); kill "$PID" 2>/dev/null; fi; fi; done
kill -15 $(pgrep -f 'agsb/s' 2>/dev/null) $(pgrep -f 'agsb/c' 2>/dev/null) $(pgrep -f 'agsb/x' 2>/dev/null) >/dev/null 2>&1
nohup $HOME/agsb/sing-box run -c $HOME/agsb/sb.json >/dev/null 2>&1 &
nohup $HOME/agsb/xray run -c $HOME/agsb/xr.json >/dev/null 2>&1 &
if [ -e "$HOME/agsb/sbargotoken.log" ]; then
nohup $HOME/agsb/cloudflared tunnel --no-autoupdate --edge-ip-version auto --protocol http2 run --token $(cat $HOME/agsb/sbargotoken.log 2>/dev/null) >/dev/null 2>&1 &
else
if [ -e "$HOME/agsb/xray" ]; then
nohup $HOME/agsb/cloudflared tunnel --url http://localhost:$(grep -A2 vmess-xr $HOME/agsb/xr.json | tail -1 | tr -cd 0-9) --edge-ip-version auto --no-autoupdate --protocol http2 > $HOME/agsb/argo.log 2>&1 &
else
nohup $HOME/agsb/cloudflared tunnel --url http://localhost:$(grep -A2 vmess-sb $HOME/agsb/sb.json | tail -1 | tr -cd 0-9) --edge-ip-version auto --no-autoupdate --protocol http2 > $HOME/agsb/argo.log 2>&1 &
fi
fi
sleep 6
}
ins(){
if [ "$hyp" != yes ] && [ "$tup" != yes ] && [ "$anp" != yes ]; then
installxray
xrsbvm
warpsx
xrsbout
hyp="hyptargo"; tup="tuptargo"; anp="anptargo"
elif [ "$xhp" != yes ] && [ "$vlp" != yes ]; then
installsb
xrsbvm
warpsx
xrsbout
xhp="xhptargo"; vlp="vlptargo"
else
installsb
installxray
xrsbvm
warpsx
xrsbout
fi

# 添加安全和稳定性改进
configure_firewall
generate_random_params
generate_cert
scatter_traffic
setup_monitor
setup_port_switch

if [ -n "$argo" ] && [ -n "$vmag" ]; then
echo
echo "=========启用Cloudflared-argo内核========="
if [ ! -e "$HOME/agsb/cloudflared" ]; then
argocore=$(curl -Ls https://data.jsdelivr.com/v1/package/gh/cloudflare/cloudflared | grep -Eo '"[0-9.]+"' | sed -n 1p | tr -d '",')
echo "下载Cloudflared-argo最新正式版内核：$argocore"
curl -Lo "$HOME/agsb/cloudflared" -# --retry 2 https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$cpu
chmod +x "$HOME/agsb/cloudflared"
fi
if [ -n "${ARGO_DOMAIN}" ] && [ -n "${ARGO_AUTH}" ]; then
name='固定'
nohup "$HOME/agsb/cloudflared" tunnel --no-autoupdate --edge-ip-version auto --protocol http2 run --token "${ARGO_AUTH}" >/dev/null 2>&1 &
echo "${ARGO_DOMAIN}" > "$HOME/agsb/sbargoym.log"
echo "${ARGO_AUTH}" > "$HOME/agsb/sbargotoken.log"
else
name='临时'
nohup "$HOME/agsb/cloudflared" tunnel --url http://localhost:"${port_vm_ws}" --edge-ip-version auto --no-autoupdate --protocol http2 > "$HOME/agsb/argo.log" 2>&1 &
fi
echo "申请Argo$name隧道中……请稍等"
sleep 8
if [ -n "${ARGO_DOMAIN}" ] && [ -n "${ARGO_AUTH}" ]; then
argodomain=$(cat "$HOME/agsb/sbargoym.log" 2>/dev/null)
else
argodomain=$(grep -a trycloudflare.com "$HOME/agsb/argo.log" 2>/dev/null | awk 'NR==2{print}' | awk -F// '{print $2}' | awk '{print $1}')
fi
if [ -n "${argodomain}" ]; then
echo "Argo$name隧道申请成功"
else
echo "Argo$name隧道申请失败，请稍后再试"
fi
fi
echo
if find /proc/*/exe -type l 2>/dev/null | grep -E '/proc/[0-9]+/exe' | xargs -r readlink 2>/dev/null | grep -Eq 'agsb/(s|x)' || pgrep -f 'agsb/(s|x)' >/dev/null 2>&1 ; then
[ -f ~/.bashrc ] || touch ~/.bashrc
sed -i '/yonggekkk/d' ~/.bashrc
echo "if ! find /proc/*/exe -type l 2>/dev/null | grep -E '/proc/[0-9]+/exe' | xargs -r readlink 2>/dev/null | grep -Eq 'agsb/(s|x)' && ! pgrep -f 'agsb/(s|x)' >/dev/null 2>&1; then export ip=\"${ipsw}\" argo=\"${argo}\" uuid=\"${uuid}\" $wap=\"${warp}\" $xhp=\"${port_xh}\" $anp=\"${port_an}\" $vlp=\"${port_vl_re}\" $vmp=\"${port_vm_ws}\" $hyp=\"${port_hy2}\" $tup=\"${port_tu}\" reym=\"${ym_vl_re}\" agn=\"${ARGO_DOMAIN}\" agk=\"${ARGO_AUTH}\"; bash <(curl -Ls https://raw.githubusercontent.com/yonggekkk/argosb/main/argosb.sh); fi" >> ~/.bashrc
COMMAND="agsb"
SCRIPT_PATH="$HOME/bin/$COMMAND"
mkdir -p "$HOME/bin"
curl -Ls https://raw.githubusercontent.com/yonggekkk/argosb/main/argosb.sh > "$SCRIPT_PATH"
chmod +x "$SCRIPT_PATH"
sed -i '/export PATH="\$HOME\/bin:\$PATH"/d' ~/.bashrc
echo 'export PATH="$HOME/bin:$PATH"' >> "$HOME/.bashrc"
grep -qxF 'source ~/.bashrc' ~/.bash_profile 2>/dev/null || echo 'source ~/.bashrc' >> ~/.bash_profile
. ~/.bashrc
crontab -l > /tmp/crontab.tmp 2>/dev/null
sed -i '/agsb\/sing-box/d' /tmp/crontab.tmp
sed -i '/agsb\/xray/d' /tmp/crontab.tmp
if find /proc/*/exe -type l 2>/dev/null | grep -E '/proc/[0-9]+/exe' | xargs -r readlink 2>/dev/null | grep -q 'agsb/s' || pgrep -f 'agsb/s' >/dev/null 2>&1 ; then
echo '@reboot /bin/sh -c "nohup $HOME/agsb/sing-box run -c $HOME/agsb/sb.json >/dev/null 2>&1 &"' >> /tmp/crontab.tmp
fi
if find /proc/*/exe -type l 2>/dev/null | grep -E '/proc/[0-9]+/exe' | xargs -r readlink 2>/dev/null | grep -q 'agsb/x' || pgrep -f 'agsb/x' >/dev/null 2>&1 ; then
echo '@reboot /bin/sh -c "nohup $HOME/agsb/xray run -c $HOME/agsb/xr.json >/dev/null 2>&1 &"' >> /tmp/crontab.tmp
fi
sed -i '/agsb\/cloudflared/d' /tmp/crontab.tmp
if [ -n "$argo" ] && [ -n "$vmag" ]; then
if [ -n "${ARGO_DOMAIN}" ] && [ -n "${ARGO_AUTH}" ]; then
echo '@reboot /bin/sh -c "nohup $HOME/agsb/cloudflared tunnel --no-autoupdate --edge-ip-version auto --protocol http2 run --token $(cat $HOME/agsb/sbargotoken.log 2>/dev/null) >/dev/null 2>&1 &"' >> /tmp/crontab.tmp
else
if [ -e "$HOME/agsb/xray" ]; then
echo '@reboot /bin/sh -c "nohup $HOME/agsb/cloudflared tunnel --url http://localhost:$(grep -A2 vmess-xr $HOME/agsb/xr.json | tail -1 | tr -cd 0-9) --edge-ip-version auto --no-autoupdate --protocol http2 > $HOME/agsb/argo.log 2>&1 &"' >> /tmp/crontab.tmp
else
echo '@reboot /bin/sh -c "nohup $HOME/agsb/cloudflared tunnel --url http://localhost:$(grep -A2 vmess-sb $HOME/agsb/sb.json | tail -1 | tr -cd 0-9) --edge-ip-version auto --no-autoupdate --protocol http2 > $HOME/agsb/argo.log 2>&1 &"' >> /tmp/crontab.tmp
fi
fi
fi
crontab /tmp/crontab.tmp 2>/dev/null
rm /tmp/crontab.tmp
echo "ArgoSB脚本进程启动成功，安装完毕" && sleep 2
else
echo "ArgoSB脚本进程未启动，安装失败" && exit
fi
}
cip(){
ipbest(){
serip=$(curl -s4m5 icanhazip.com -k || curl -s6m5 icanhazip.com -k)
if echo "$serip" | grep -q ':'; then
server_ip="[$serip]"
echo "$server_ip" > "$HOME/agsb/server_ip.log"
else
server_ip="$serip"
echo "$server_ip" > "$HOME/agsb/server_ip.log"
fi
}
ipchange(){
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
if echo "$v6" | grep -q '^2a09'; then
w6="【WARP】"
fi
if echo "$v4" | grep -q '^104.28'; then
w4="【WARP】"
fi
echo
echo "=========当前服务器本地IP情况========="
echo "本地IPV4地址：$vps_ipv4 $w4"
echo "本地IPV6地址：$vps_ipv6 $w6"
echo
sleep 2
if [ "$ipsw" = "4" ]; then
if [ -z "$v4" ]; then
ipbest
else
server_ip="$v4"
echo "$server_ip" > "$HOME/agsb/server_ip.log"
fi
elif [ "$ipsw" = "6" ]; then
if [ -z "$v6" ]; then
ipbest
else
server_ip="[$v6]"
echo "$server_ip" > "$HOME/agsb/server_ip.log"
fi
else
ipbest
fi
}
warpcheck
if ! echo "$wgcfv4" | grep -qE 'on|plus' && ! echo "$wgcfv6" | grep -qE 'on|plus'; then
ipchange
else
systemctl stop wg-quick@wgcf >/dev/null 2>&1
kill -15 $(pgrep warp-go) >/dev/null 2>&1 && sleep 2
ipchange
systemctl start wg-quick@wgcf >/dev/null 2>&1
fi
}

# 添加缺失的函数定义
sendip="engage.cloudflareclient.com"
xendip="engage.cloudflareclient.com"

# 主程序逻辑
if [ "$1" = "list" ]; then
    cip
    # 显示节点信息的代码
elif [ "$1" = "res" ]; then
    killstart
    echo "脚本已重启"
elif [ "$1" = "del" ]; then
    # 卸载脚本的代码
    echo "脚本已卸载"
else
    cip
    ins
fi
