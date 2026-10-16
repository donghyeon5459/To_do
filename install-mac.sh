#!/bin/bash
# 맥미니에서 한 번만 실행하세요. 로그인하면 서버가 자동으로 켜지고, 꺼져도 다시 살아납니다.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "python3가 없어요. 터미널에서 'xcode-select --install' 을 먼저 실행해 주세요."
  exit 1
fi
PORT="${PORT:-8787}"                 # 이미 쓰는 포트면 PORT=8790 bash install-mac.sh 처럼 바꿔서 실행
BIND="${BIND:-127.0.0.1}"            # 다른 기기에서 쓰려면 이 맥의 Tailscale IP (tailscale ip -4)
ALLOWED_LOGINS="${ALLOWED_LOGINS:-}" # 접속 허용 Tailscale 계정 (예: you@github). 비우면 제한 없음
CERT_DOMAIN="${CERT_DOMAIN:-}"       # 이 맥의 Tailscale 도메인(xxx.tailXXXX.ts.net)을 넣으면 https 로 열림
LABEL="com.mytodo.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$DIR/server.py</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>EnvironmentVariables</key><dict>
    <key>PORT</key><string>$PORT</string>
    <key>BIND</key><string>$BIND</string>
    <key>CERT_DOMAIN</key><string>$CERT_DOMAIN</string>
    <key>ALLOWED_LOGINS</key><string>$ALLOWED_LOGINS</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$DIR/server.log</string>
  <key>StandardErrorPath</key><string>$DIR/server.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
if [ -n "$CERT_DOMAIN" ]; then URL="https://$CERT_DOMAIN:$PORT"; else URL="http://$BIND:$PORT"; fi
echo "설치 완료. $URL 로 열어 보세요."
