#!/bin/bash

# ─────────────────────────────────────────
# 유튜브 대학 — 원클릭 배포
# 더블클릭하면 자동으로 GitHub에 올라갑니다
# ─────────────────────────────────────────

# 이 파일이 있는 폴더 기준으로 실행
cd "$(dirname "$0")"

echo "📚 유튜브 대학 배포 시작..."
echo ""

# youtube-univ.html 존재 확인
if [ ! -f "youtube-univ.html" ]; then
  echo "❌ youtube-univ.html 파일이 없습니다."
  echo "   Claude가 생성한 파일을 이 폴더에 넣어주세요."
  read -p "엔터를 누르면 닫힙니다..."
  exit 1
fi

# Git 저장소가 없으면 초기화 + 원격 연결
if [ ! -d ".git" ]; then
  echo "🔧 Git 저장소 초기화 중..."
  git init
  git branch -M main
  git remote add origin https://github.com/Kimda-woon/Youtube-university.git
  git fetch origin 2>/dev/null
  git reset --mixed origin/main 2>/dev/null || true
  echo "✅ Git 저장소 초기화 완료"
fi

# youtube-univ.html → index.html 동기화 (GitHub Pages용)
cp youtube-univ.html index.html
echo "📄 index.html 동기화 완료"

# 전체 파일 스테이징 (library.js, transcripts/, youtube-univ.html 등)
git add -A

CHANGED=$(git diff --cached --name-only)
if [ -z "$CHANGED" ]; then
  echo "ℹ️  변경된 내용이 없습니다. 이미 최신 상태입니다."
  read -p "엔터를 누르면 닫힙니다..."
  exit 0
fi

# 커밋 메시지 자동 생성 (날짜 기반)
TIMESTAMP=$(date "+%Y-%m-%d %H:%M")
git commit -m "update: 강의 추가 ($TIMESTAMP)"

echo ""
echo "⬆️  GitHub에 업로드 중..."
git push origin main

if [ $? -eq 0 ]; then
  echo ""
  echo "✅ 배포 완료!"
  echo "🔗 https://kimda-woon.github.io/Youtube-university/"
  echo ""
  echo "   약 30초~1분 후 링크가 갱신됩니다."
  # 링크를 브라우저로 자동 열기
  sleep 2
  open "https://kimda-woon.github.io/Youtube-university/"
else
  echo ""
  echo "❌ 업로드 실패. 아래를 확인해주세요:"
  echo "   1. 인터넷 연결 상태"
  echo "   2. GitHub 인증 설정 (SSH 키 또는 토큰)"
fi

read -p "엔터를 누르면 닫힙니다..."
