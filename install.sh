#!/usr/bin/env bash
# EinkPi installer for Raspberry Pi OS (Bookworm)
set -e

CURRENT_USER=$(whoami)
INSTALL_DIR="$HOME/einkpi"
REPO_URL="https://github.com/neoblast-cz/eink-custom-build.git"

echo "=== EinkPi Installer ==="
echo ""

# 1. System packages
echo "[1/6] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3-pip python3-venv python3-dev \
    libjpeg-dev libopenjp2-7 libopenblas-dev \
    fonts-dejavu-core \
    spi-tools git

# 2. Enable SPI
echo "[2/6] Enabling SPI..."
BOOT_CONFIG="/boot/firmware/config.txt"
if [ ! -f "$BOOT_CONFIG" ]; then
    BOOT_CONFIG="/boot/config.txt"
fi
if ! grep -q "^dtparam=spi=on" "$BOOT_CONFIG" 2>/dev/null; then
    echo "dtparam=spi=on" | sudo tee -a "$BOOT_CONFIG"
    echo "  SPI enabled (reboot required after install)"
    NEED_REBOOT=1
fi

# 3. Clone or update repo
echo "[3/6] Setting up project..."
if [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR"
    git pull
else
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 4. Python venv + dependencies
echo "[4/6] Setting up Python environment..."
python3 -m venv venv
./venv/bin/pip install --quiet -r requirements.txt
./venv/bin/pip install --quiet RPi.GPIO spidev gpiozero

# 5. Waveshare EPD drivers (download only needed files, not the huge repo)
echo "[5/6] Installing Waveshare display drivers..."
if [ ! -d "./waveshare_epd" ]; then
    mkdir -p waveshare_epd
    WAVESHARE_BASE="https://raw.githubusercontent.com/waveshareteam/e-Paper/master/RaspberryPi_JetsonNano/python/lib/waveshare_epd"
    curl -sL "$WAVESHARE_BASE/epdconfig.py" -o waveshare_epd/epdconfig.py
    curl -sL "$WAVESHARE_BASE/epd7in5_V2.py" -o waveshare_epd/epd7in5_V2.py
    curl -sL "$WAVESHARE_BASE/__init__.py" -o waveshare_epd/__init__.py
    echo "  Downloaded EPD driver files"
fi

# Create initial config if missing
if [ ! -f config.json ]; then
    cp config.example.json config.json
fi

# Create uploads directory
mkdir -p uploads

# 6. Systemd service (generate with correct user/paths)
echo "[6/6] Installing systemd service..."
cat > /tmp/einkpi.service <<SVCEOF
[Unit]
Description=EinkPi Display Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python app.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF
sudo cp /tmp/einkpi.service /etc/systemd/system/
rm /tmp/einkpi.service
sudo systemctl daemon-reload
sudo systemctl enable einkpi
sudo systemctl start einkpi

echo ""
echo "=== Installation complete! ==="
IP=$(hostname -I | awk '{print $1}')
echo "Web UI: http://${IP}:8080"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status einkpi    # Check status"
echo "  sudo systemctl restart einkpi   # Restart"
echo "  sudo journalctl -u einkpi -f    # View logs"
echo ""
if [ "${NEED_REBOOT:-0}" = "1" ]; then
    echo "NOTE: Reboot required for SPI. Run: sudo reboot"
fi
