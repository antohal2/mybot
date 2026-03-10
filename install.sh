#!/usr/bin/env bash
# =============================================================================
#  install.sh — Automated installer for mybot (3x-ui Telegram Bot)
#  Tested on: Ubuntu 20.04 / 22.04 / Debian 11 / 12
# =============================================================================
set -euo pipefail

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Config ───────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/antohal2/mybot.git"
INSTALL_DIR="/opt/mybot"
SERVICE_NAME="mybot"
PYTHON_MIN="3.10"

# ── Root check ───────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  error "Run this script as root: sudo bash install.sh"
fi

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     mybot — 3x-ui Telegram Bot Setup     ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── Step 1: System packages ──────────────────────────────────────────────────
info "Updating package list..."
apt-get update -qq

info "Installing system dependencies..."
apt-get install -y -qq \
  python3 python3-pip python3-venv \
  git curl wget \
  2>/dev/null
success "System packages installed."

# ── Step 2: Python version check ─────────────────────────────────────────────
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "Detected Python $PY_VER"

if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"; then
  success "Python version is sufficient."
else
  warn "Python $PY_VER detected, minimum required is $PYTHON_MIN."
  info "Installing python3.11 via deadsnakes PPA..."
  apt-get install -y -qq software-properties-common
  add-apt-repository -y ppa:deadsnakes/ppa
  apt-get update -qq
  apt-get install -y -qq python3.11 python3.11-venv python3.11-distutils
  update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
  success "Python 3.11 installed."
fi

# ── Step 3: Clone / update repo ──────────────────────────────────────────────
if [[ -d "$INSTALL_DIR/.git" ]]; then
  info "Repository already exists, pulling latest changes..."
  git -C "$INSTALL_DIR" pull --ff-only
  success "Repository updated."
else
  info "Cloning repository to $INSTALL_DIR..."
  git clone "$REPO_URL" "$INSTALL_DIR"
  success "Repository cloned."
fi

cd "$INSTALL_DIR"

# ── Step 4: Virtual environment ──────────────────────────────────────────────
if [[ ! -d "$INSTALL_DIR/venv" ]]; then
  info "Creating Python virtual environment..."
  python3 -m venv "$INSTALL_DIR/venv"
  success "Virtual environment created."
fi

info "Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q
success "Python dependencies installed."

# ── Step 5: Interactive .env configuration ───────────────────────────────────
echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}         Bot configuration (press Enter to skip)  ${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

ENV_FILE="$INSTALL_DIR/.env"

# Load existing values if .env exists
if [[ -f "$ENV_FILE" ]]; then
  warn ".env already exists. Existing values will be shown as defaults."
  source "$ENV_FILE" 2>/dev/null || true
fi

prompt() {
  local VAR_NAME="$1"
  local PROMPT_TEXT="$2"
  local DEFAULT="${!VAR_NAME:-${3:-}}"
  local INPUT
  if [[ -n "$DEFAULT" ]]; then
    read -rp "  $PROMPT_TEXT [${DEFAULT}]: " INPUT
    INPUT="${INPUT:-$DEFAULT}"
  else
    read -rp "  $PROMPT_TEXT: " INPUT
  fi
  echo "$INPUT"
}

BOT_TOKEN=$(prompt BOT_TOKEN        "Telegram Bot Token (@BotFather)"         "")
ADMIN_IDS=$(prompt ADMIN_IDS        "Admin Telegram ID(s) comma-separated"    "")
XUI_HOST=$(prompt  XUI_HOST         "3x-ui panel URL (e.g. http://IP:2053)"   "http://127.0.0.1:2053")
XUI_USERNAME=$(prompt XUI_USERNAME  "3x-ui username"                           "admin")
XUI_PASSWORD=$(prompt XUI_PASSWORD  "3x-ui password"                           "admin")
XUI_INBOUND_ID=$(prompt XUI_INBOUND_ID "Inbound ID in 3x-ui"                  "1")
DEFAULT_TRAFFIC_GB=$(prompt DEFAULT_TRAFFIC_GB "Default traffic limit (GB)"   "50")
YOOKASSA_SHOP_ID=$(prompt YOOKASSA_SHOP_ID "YooKassa Shop ID (optional)"       "")
YOOKASSA_SECRET=$(prompt YOOKASSA_SECRET "YooKassa Secret (optional)"          "")
CRYPTO_PAY_TOKEN=$(prompt CRYPTO_PAY_TOKEN "CryptoPay Token (optional)"       "")
CRYPTO_PAY_NET=$(prompt CRYPTO_PAY_NET "CryptoPay Net (mainnet/testnet)"      "mainnet")
PAYMENT_METHOD=$(prompt PAYMENT_METHOD "Payment method (stars/yookassa/cryptopay)" "stars")
USE_TELEGRAM_STARS=$(prompt USE_TELEGRAM_STARS "Use Telegram Stars (true/false)" "true")

cat > "$ENV_FILE" <<EOF
# Auto-generated by install.sh
BOT_TOKEN=${BOT_TOKEN}
ADMIN_IDS=${ADMIN_IDS}
XUI_HOST=${XUI_HOST}
XUI_USERNAME=${XUI_USERNAME}
XUI_PASSWORD=${XUI_PASSWORD}
XUI_INBOUND_ID=${XUI_INBOUND_ID}
DEFAULT_TRAFFIC_GB=${DEFAULT_TRAFFIC_GB}
YOOKASSA_SHOP_ID=${YOOKASSA_SHOP_ID}
YOOKASSA_SECRET=${YOOKASSA_SECRET}
CRYPTO_PAY_TOKEN=${CRYPTO_PAY_TOKEN}
CRYPTO_PAY_NET=${CRYPTO_PAY_NET}
PAYMENT_METHOD=${PAYMENT_METHOD}
USE_TELEGRAM_STARS=${USE_TELEGRAM_STARS}
DB_PATH=${INSTALL_DIR}/bot.db
EOF

chmod 600 "$ENV_FILE"
success ".env file saved."

# ── Step 6: Systemd service ───────────────────────────────────────────────────
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

info "Creating systemd service: ${SERVICE_NAME}..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=mybot — 3x-ui Telegram Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/bot.py
Restart=on-failure
RestartSec=5s
EnvironmentFile=${ENV_FILE}
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
success "Systemd service '${SERVICE_NAME}' enabled and started."

# ── Step 7: Status summary ────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          Installation complete!          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYAN}Bot directory:${NC}  $INSTALL_DIR"
echo -e "  ${CYAN}Config file:${NC}    $ENV_FILE"
echo -e "  ${CYAN}Service name:${NC}   $SERVICE_NAME"
echo ""
echo -e "  ${YELLOW}Useful commands:${NC}"
echo -e "    systemctl status $SERVICE_NAME   — check status"
echo -e "    systemctl stop   $SERVICE_NAME   — stop bot"
echo -e "    systemctl start  $SERVICE_NAME   — start bot"
echo -e "    journalctl -u $SERVICE_NAME -f    — view live logs"
echo ""

# Show live service status
sleep 1
if systemctl is-active --quiet "$SERVICE_NAME"; then
  success "Bot is running!"
else
  warn "Bot service is NOT running. Check logs:"
  echo "    journalctl -u $SERVICE_NAME -n 30 --no-pager"
fi
