#!/bin/bash
# =========================================
# TUIC v1.4.5 over QUIC 自动部署脚本（免 root）
# 固定 SNI：www.bing.com，自动生成配置与证书
# =========================================
set -euo pipefail
export LC_ALL=C
IFS=$'\n\t'

# ========== 全局参数 ==========
MASQ_DOMAIN="www.bing.com"
SERVER_TOML="server.toml"
CERT_PEM="tuic-cert.pem"
KEY_PEM="tuic-key.pem"
LINK_TXT="tuic_link.txt"
TUIC_BIN="./tuic-server"
TUIC_VERSION="1.4.5"

# ========== 随机端口函数 ==========
random_port() {
  echo $(( (RANDOM % 40000) + 20000 ))
}

# ========== 选择端口 ==========
select_port() {
  if [[ $# -ge 1 && -n "${1:-}" ]]; then
    TUIC_PORT="$1"
    echo "✅ Using specified port: $TUIC_PORT"
  else
    TUIC_PORT=$(random_port)
    echo "🎲 Random port selected: $TUIC_PORT"
  fi
}

# ========== 加载现有配置 ==========
load_existing_config() {
  if [[ -f "$SERVER_TOML" ]]; then
    echo "📂 Existing configuration detected. Loading..."
    TUIC_PORT=$(grep '^server' "$SERVER_TOML" | grep -Eo '[0-9]+')
    TUIC_UUID=$(grep '^\[users\]' -A1 "$SERVER_TOML" | tail -n1 | awk '{print $1}')
    TUIC_PASSWORD=$(grep '^\[users\]' -A1 "$SERVER_TOML" | tail -n1 | awk -F'"' '{print $2}')
    return 0
  fi
  return 1
}

# ========== 检查并生成证书 ==========
generate_cert() {
  if [[ -f "$CERT_PEM" && -f "$KEY_PEM" ]]; then
    echo "🔐 Certificate already exists, skipping."
    return
  fi
  echo "🔐 Generating self-signed certificate for ${MASQ_DOMAIN}..."
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
    -keyout "$KEY_PEM" -out "$CERT_PEM" -subj "/CN=${MASQ_DOMAIN}" -days 365 -nodes >/dev/null 2>&1
  chmod 600 "$KEY_PEM"
  chmod 644 "$CERT_PEM"
}

# ========== 检查并下载 tuic-server ==========
check_tuic_server() {
  if [[ -x "$TUIC_BIN" ]]; then
    echo "✅ tuic-server binary already exists."
    return
  fi

  echo "📥 Downloading tuic-server ${TUIC_VERSION}..."
  arch=$(uname -m)
  case "$arch" in
    x86_64) url="https://github.com/Itsusinn/tuic/releases/download/v${TUIC_VERSION}/tuic-server-x86_64-linux" ;;
    aarch64|arm64) url="https://github.com/Itsusinn/tuic/releases/download/v${TUIC_VERSION}/tuic-server-arm64-linux" ;;
    *) echo "❌ Unsupported architecture: $arch"; exit 1 ;;
  esac

  curl -L -o "$TUIC_BIN" "$url"
  chmod +x "$TUIC_BIN"
}

# ========== 生成配置文件 ==========
generate_config() {
cat > "$SERVER_TOML" <<EOF
log_level = "warn"
server = "0.0.0.0:${TUIC_PORT}"

udp_relay_ipv6 = false
zero_rtt_handshake = true
dual_stack = false
auth_timeout = "8s"
task_negotiation_timeout = "4s"
gc_interval = "8s"
gc_lifetime = "8s"
max_external_packet_size = 8192

[users]
${TUIC_UUID} = "${TUIC_PASSWORD}"

[tls]
certificate = "$CERT_PEM"
private_key = "$KEY_PEM"
alpn = ["h3"]

[restful]
addr = "127.0.0.1:${TUIC_PORT}"
secret = "$(openssl rand -hex 16)"
maximum_clients_per_user = 999999999

[quic]
initial_mtu = $((1200 + RANDOM % 200))
min_mtu = 1200
gso = true
pmtu = true
send_window = 33554432
receive_window = 16777216
max_idle_time = "25s"

[quic.congestion_control]
controller = "bbr"
initial_window = 6291456
EOF
  echo "✅ Configuration file generated: ${SERVER_TOML}"
}

# ========== 获取公网 IP ==========
get_server_ip() {
  curl -s --connect-timeout 5 https://api64.ipify.org || echo "127.0.0.1"
}

# ========== 生成 TUIC 链接 ==========
generate_link() {
  local ip="$1"
  cat > "$LINK_TXT" <<EOF
tuic://${TUIC_UUID}:${TUIC_PASSWORD}@${ip}:${TUIC_PORT}?congestion_control=bbr&alpn=h3&allowInsecure=1&sni=${MASQ_DOMAIN}&udp_relay_mode=native&disable_sni=0&reduce_rtt=1&max_udp_relay_packet_size=8192#TUIC-${ip}
EOF
  echo ""
  echo "🔗 TUIC Node Link (Saved to ${LINK_TXT}):"
  echo "------------------------------------------------------------"
  cat "$LINK_TXT"
  echo "------------------------------------------------------------"
}

# ========== 启动守护进程 ==========
run_background_loop() {
  echo "🚀 Starting TUIC server in background..."
  while true; do
    "$TUIC_BIN" -c "$SERVER_TOML" >/dev/null 2>&1 || true
    echo "⚠️ TUIC server crashed. Restarting in 5 seconds..."
    sleep 5
  done
}

# ========== 主执行流程 ==========
main() {
  if ! load_existing_config; then
    select_port "$@"
    TUIC_UUID="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || uuidgen)"
    TUIC_PASSWORD="$(openssl rand -hex 16)"
    generate_cert
    check_tuic_server
    generate_config
  else
    generate_cert
    check_tuic_server
  fi

  local ip
  ip="$(get_server_ip)"
  generate_link "$ip"
  run_background_loop
}

main "$@"
