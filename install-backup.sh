#!/bin/bash
# 매일 data.json 을 백업 폴더에 복사하도록 등록합니다. (맥미니에서 한 번만 실행)
# 사용: bash install-backup.sh "/백업/폴더/경로" [몇 시(0~23, 기본 3)]
set -e
DEST="$1"
HOUR="${2:-3}"
if [ -z "$DEST" ] || [ ! -d "$DEST" ]; then
  echo "사용법: bash install-backup.sh \"/백업/폴더/경로\" [몇 시]"
  echo "백업 폴더가 있어야 해요: $DEST"
  exit 1
fi
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3)"
LABEL="com.mytodo.backup"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$DIR/backup.py</string><string>$DEST</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$DIR/backup.log</string>
  <key>StandardErrorPath</key><string>$DIR/backup.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "등록 완료. 매일 ${HOUR}시에 $DEST 로 백업합니다. (로그: $DIR/backup.log)"
