#!/bin/bash

# AI Trading Bot Service Installation Script
# macOS에서는 launchd를 사용하고, Linux에서는 systemd를 사용

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🚀 Installing AI Trading Bot Daemon Service..."

# OS 감지
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - launchd 사용
    echo "📱 Detected macOS - Using launchd"
    
    # launchd plist 파일 생성
    PLIST_FILE="$HOME/Library/LaunchAgents/com.ai-trading-bot.plist"
    
    cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ai-trading-bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$PROJECT_DIR/scripts/start_daemon.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/launchd.out</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/launchd.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$PROJECT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>PYTHONPATH</key>
        <string>$PROJECT_DIR</string>
    </dict>
</dict>
</plist>
EOF

    echo "✅ Created launchd plist: $PLIST_FILE"
    
    # 서비스 로드
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    launchctl load "$PLIST_FILE"
    
    echo "✅ Service loaded into launchd"
    echo ""
    echo "🔧 macOS Management Commands:"
    echo "  Start:  launchctl start com.ai-trading-bot"
    echo "  Stop:   launchctl stop com.ai-trading-bot"  
    echo "  Status: launchctl list | grep ai-trading-bot"
    echo "  Logs:   tail -f $PROJECT_DIR/logs/launchd.{out,err}"
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux - systemd 사용
    echo "🐧 Detected Linux - Using systemd"
    
    # systemd 서비스 파일 복사
    sudo cp "$SCRIPT_DIR/systemd/ai-trading-bot.service" /etc/systemd/system/
    
    # systemd 리로드 및 서비스 활성화
    sudo systemctl daemon-reload
    sudo systemctl enable ai-trading-bot.service
    
    echo "✅ Service installed to systemd"
    echo ""
    echo "🔧 Linux Management Commands:"
    echo "  Start:  sudo systemctl start ai-trading-bot"
    echo "  Stop:   sudo systemctl stop ai-trading-bot"
    echo "  Status: sudo systemctl status ai-trading-bot"
    echo "  Logs:   journalctl -u ai-trading-bot -f"
    
else
    echo "❌ Unsupported OS: $OSTYPE"
    exit 1
fi

echo ""
echo "🎉 AI Trading Bot daemon service installed successfully!"
echo ""
echo "📊 Features:"
echo "  • Automatic startup on system boot"
echo "  • Automatic restart on crash"
echo "  • Real-time BTC-USDT-SWAP data collection"
echo "  • 5m, 15m, 1h, 4h, 1d timeframes"
echo "  • PostgreSQL data storage"
echo "  • Redis queue management"
echo ""