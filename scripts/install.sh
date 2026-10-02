#!/usr/bin/env bash
# ==============================================================================
# Amber SRE Engine — 1-Line Zero-Touch Automated Production Installer
# Usage:
#   curl -fsSL https://ambersre.xyz/install.sh | bash
# ==============================================================================
set -euo pipefail

AMBER_DIR="${HOME}/.amber"
REPO_URL="https://github.com/himanshu-xyz-1/Amber-Backend-under-development.git"

echo "============================================================"
echo "⚡ Installing Amber Autonomous SRE Engine into your VPC..."
echo "============================================================"

# 1. Ensure Docker is present
if ! command -v docker &> /dev/null; then
    echo "📦 Docker not detected. Installing Docker Engine..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER" || true
fi

# 2. Clone or pull Amber repository
if [ -d "$AMBER_DIR" ]; then
    echo "🔄 Updating existing Amber installation..."
    cd "$AMBER_DIR"
    git pull origin main || true
else
    echo "📥 Cloning Amber SRE repository..."
    git clone --depth 1 "$REPO_URL" "$AMBER_DIR"
    cd "$AMBER_DIR"
fi

# 3. Auto-generate .env if missing
if [ ! -f .env ]; then
    echo "🔐 Generating cryptographic cluster keys..."
    cp .env.example .env
    JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || date +%s | sha256sum | base64 | head -c 32)
    sed -i "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${JWT_SECRET}|g" .env
fi

# 4. Single-Command Ignition
echo "🚀 Booting Amber Cluster (PostgreSQL pgvector, Redis 7, Backend, Telegram & WhatsApp)..."
docker compose down 2>/dev/null || true
docker compose up -d

# 5. Readiness verification
echo "⏳ Waiting for cluster readiness..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:8000/api/v1/health/readiness | grep -q "ready"; then
        echo ""
        echo "============================================================"
        echo "✅ AMBER SRE ENGINE IS 100% OPERATIONAL!"
        echo "============================================================"
        echo "• Local API Gateway:   http://localhost:8000"
        echo "• Interactive Swagger: http://localhost:8000/docs"
        echo "• WhatsApp Bridge:     http://localhost:3001"
        echo "• Telegram Bot:        https://t.me/ambersre_alert_bot"
        echo ""
        echo "👉 Open https://t.me/ambersre_alert_bot and tap /start to auto-subscribe."
        echo "============================================================"
        exit 0
    fi
    sleep 1
done

echo "⚠️ Amber started. Check logs: docker compose logs -f"
