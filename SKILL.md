---
name: youtube-univ
description: |
  유튜브 강의를 "구조화된 개인 지식"으로 바꾸는 스킬. 자막 확보(자동 추출 또는 복붙) → 파싱 → 강의 분석(한 줄 핵심·요약·해설·핵심 개념·논리 흐름·챕터·핵심 구간·인사이트·핵심 정리·복습 질문) → 자동 분류 → 단일 HTML 서재에 누적(임베드 플레이어·복습·용어사전·진도 저장·검색) → GitHub Pages 자동 배포까지 한 흐름으로 처리한다.

  반드시 이 스킬을 사용해야 하는 상황: 사용자가 유튜브 링크(youtube.com/watch, youtu.be, shorts 등)를 주면서 "정리해줘 / 요약해줘 / 분석해줘 / 학습 페이지 만들어줘 / 강의 정리 / 지식 축적 / 유튜브 대학에 넣어줘"를 요청할 때. 또는 "유튜브 대학", "강의 정리 시스템", "영상 지식화"를 언급할 때. 자막은 자동 추출을 먼저 시도하고, 막히면 사용자에게 타임스탬프 자막 붙여넣기를 요청한다.
---

# 유튜브 대학 강의 → 개인 지식 시스템

유튜브 강의를 **영상 소비 → 지식 축적 → 공개 가능한 정보**로 바꾸는 파이프라인이다.

## 핵심 설계 원칙 (토큰 절감)

1. **자막을 Claude가 다시 출력하지 않는다.** 파싱 스크립트가 자막을 디스크에 직접 쓴다. analysis(라이브러리 엔트리)에는 `transcript` 필드를 절대 넣지 않는다. → 1시간 강의에서 수천~만 단위 출력 토큰 절감.
2. **HTML은 정적 템플릿 1개.** 영상마다 HTML을 재생성하지 않는다. `youtube-univ.html`은 한 번만 만들고, 새 강의는 `library.js` + `transcripts/<id>.js` 데이터 파일만 추가한다.
3. **분석 1회 읽기만 입력 토큰을 쓴다.** 자막은 분석할 때 한 번만 컨텍스트에 들어온다.

## 전체 흐름

```
링크 입력
  → [STEP 1] 자막 확보(자동 추출 우선 / 실패 시 복붙) → 파싱 → transcripts/<id>.js 저장
  → [STEP 2] Claude 분석 (transcript 필드 없음)
  → [STEP 3] 분류
  → [STEP 4] library.js upsert + 정적 HTML 확인 + 로컬 백업 + GitHub 배포
```

## 저장소 레이아웃

```
/Users/dawoonkim/Desktop/Youtube-university/
├── youtube-univ.html        # 정적 서재 (템플릿 1개, 처음 1회만 생성/갱신)
├── library.js               # window.YTU_LIBRARY = [...]  (자동 생성)
├── library.json             # 분석 누적 원본 (자동 생성)
├── transcripts/
│   ├── <video_id>.js        # window.YTU_TX[...] = [...]  (HTML이 늦게 로드)
│   └── <video_id>.json      # 자막 원본
├── scripts/ytu_pipeline.py  # 파싱·저장·누적 모듈 (이 스킬에 동봉)
└── backups/                 # 이전 HTML 백업
```

> `scripts/ytu_pipeline.py` 와 `youtube-univ.html` 은 이 스킬 번들에 포함되어 있다. 저장소에 없으면 STEP 1 / STEP 4의 코드로 복원한다.

---

## STEP 0: 입력 확인

사용자 메시지에서 **YouTube 링크 1개**(또는 video_id)를 확인한다. `youtube.com/watch?v=`, `youtu.be/`, `shorts/`, `embed/`, 또는 11자 ID 모두 인식.

자막은 STEP 1에서 자동 추출을 먼저 시도한다. 자동 추출이 막히면 그때 사용자에게 복붙을 요청한다.

---

## STEP 1: 자막 확보 + 파싱

먼저 파이프라인 모듈이 저장소에 있는지 확인하고, 없으면 동봉본을 복원한다(전체 소스는 이 문서 맨 아래 부록 참조).

자막 확보는 **방식 A(자동) → 방식 B(복붙)** 순서로 시도한다.

### 방식 A — 자동 추출 (로컬 Mac, 권장)

`youtube-transcript-api`를 쓴다. **실행 파일 이름은 하이픈이 아니라 언더스코어**이며, PATH 문제를 피하려면 `python3 -m` 형태가 가장 안전하다.

```bash
pip install youtube-transcript-api --quiet

VIDEO_ID="<video_id>"
python3 -m youtube_transcript_api "$VIDEO_ID" --languages ko en --format json > /tmp/ytu_raw.json
```

- 자막 언어 우선순위는 `--languages ko en` (한국어 → 없으면 영어). 다른 언어는 `--list-transcripts`로 확인.
- 출력은 `[{"text","start","duration"}, ...]` 형식 JSON.
- **주의:** 이 방식은 **개인/집 IP**에서 잘 작동한다. AWS·GCP 등 **클라우드 IP는 유튜브가 차단**하므로 서버 환경에서는 실패할 수 있다. 자막이 비활성화된 영상도 실패한다.
- 실패하면(에러·빈 출력) 방식 B로 넘어간다.

### 방식 B — 복붙 (자동 추출이 막힐 때)

사용자에게 요청:

> "자동 추출이 막혔어요. YouTube 영상 페이지에서 '자막 보기(Show transcript)'를 열고 전체를 복사해 붙여넣어 주세요.
> `(0:00) 텍스트`, `[0:00] 텍스트`, `0:00  텍스트`, 또는 YouTube 자막 패널 형식 모두 인식합니다."

붙여넣은 텍스트를 `/tmp/ytu_raw.txt`로 저장한다.

### 파싱 + 저장 (공통)

`parse_transcript()`는 입력이 JSON이면 자동 추출로, 아니면 복붙으로 자동 판별한다.

```python
import sys
sys.path.insert(0, "/Users/dawoonkim/Desktop/Youtube-university/scripts")
import ytu_pipeline as P

BASE = "/Users/dawoonkim/Desktop/Youtube-university"
raw = open("/tmp/ytu_raw.json", encoding="utf-8").read()   # 방식 B면 /tmp/ytu_raw.txt
video_id = P.extract_video_id("<링크 또는 ID>")

segments = P.parse_transcript(raw)
if not segments:
    raise RuntimeError("자막을 인식하지 못했습니다. 형식을 확인하거나 복붙을 요청하세요.")

P.save_transcript(BASE, video_id, segments)   # transcripts/<id>.json + <id>.js 생성
print(f"자막 {len(segments)}줄 저장 완료: {video_id}")
```

파싱 성공 → STEP 2.

---

## STEP 2: 강의 분석 (Claude가 직접 — 이해시키는 글)

`transcripts/<video_id>.json`을 읽고 아래 스키마의 분석 객체를 만든다.
목표: **사용자가 영상을 안 봐도 핵심을 이해·흡수**하게 돕는 것.

**중요: `transcript` 필드는 절대 넣지 않는다.** 자막은 이미 STEP 1에서 디스크에 저장됐고, HTML이 직접 읽는다. Claude가 자막을 다시 쓰면 토큰이 크게 낭비된다.

```json
{
  "video_id": "...", "url": "https://www.youtube.com/watch?v=...",
  "title": "...", "channel": "채널명(있으면)",
  "category": "AI / 개발 / 생산성 / 마케팅 / 디자인 / 자기계발 / 비즈니스 / 기타",
  "tags": ["3~7개"],
  "oneLiner": "영상 전체를 한 문장으로 압축한 핵심",
  "summary": "구조적 요약 5~8문장 (무엇을→어떻게→결과)",
  "explainer": "처음 보는 사람도 이해하도록 풀어 쓴 해설. \\n\\n으로 단락 구분. 영상이 당연하게 전제하는 배경지식·용어·'왜 그런지'를 채워 영상을 안 봐도 논리가 잡히게 쓴다. 요약 반복이 아니라 '가르치는 글'이어야 한다.",
  "keyConcepts": [{"term": "핵심 용어", "explain": "1~3문장 풀이"}],
  "logicFlow": ["영상 논리 전개 4~8단계. 'A이므로 B' 인과 형식."],
  "chapters": [{"time": 초정수, "title": "", "desc": "이 구간에서 무엇을 가르치는지 2~3문장"}],
  "highlights": [{"time": 초정수, "text": "핵심 한 문장", "reason": "왜 중요한지"}],
  "insight": "핵심 통찰 2~3문장",
  "takeaways": ["꼭 기억할 핵심 정리 4~7개"],
  "reviewQuestions": ["스스로 답하며 이해를 점검하는 질문 4~6개"]
}
```

**품질 기준:**
- `explainer`가 핵심. 단순 요약 반복 금지. 용어 풀이 + 이유 설명 + 비유/예시로 '이해'를 만든다.
- `time`은 `transcripts/<id>.json`의 **실제 start 값(초)**만 사용. 추측·보간 금지.
- 영상에 실제로 나온 숫자·도구명·고유명사를 담는다. 막연한 일반론 금지.
- 1시간 이상: 챕터 10~16개, 하이라이트 8~12개, 핵심 개념 6~10개.

---

## STEP 3: 자동 분류

`category` 하나 + `tags` 3~7개를 STEP 2 객체에 포함한다. 태그는 다른 강의와 공유될 때 "연결된 강의"·"용어사전"이 작동하므로, 일관된 용어로 단다.

---

## STEP 4: 라이브러리 누적 + 정적 HTML + 배포

### library 누적 (자막 미포함)

```python
entry = { ... STEP 2~3에서 만든 분석 객체 ... }   # transcript 필드 없음

n = P.upsert_library(BASE, entry)   # library.json + library.js 갱신, 중복 video_id는 갱신
print(f"라이브러리 누적: {n}편")
```

### 정적 HTML 확인 (재생성 아님)

`youtube-univ.html`이 저장소에 없을 때만 동봉 템플릿을 복사한다. **이미 있으면 건드리지 않는다.**

```bash
HTML="/Users/dawoonkim/Desktop/Youtube-university/youtube-univ.html"
[ -f "$HTML" ] || cp "<스킬 번들의 youtube-univ.html>" "$HTML"
```

HTML은 `library.js`를 읽고, 자막은 사용자가 [스크립트] 탭을 열 때 `transcripts/<id>.js`를 늦게 로드한다. 그래서 **새 강의가 추가돼도 HTML 자체는 바뀌지 않는다.** (템플릿 자체를 개선할 때만 교체)

### 로컬 백업 + GitHub Pages 배포

```bash
REPO="/Users/dawoonkim/Desktop/Youtube-university"
cd "$REPO"

# HTML 템플릿을 교체한 경우에만 직전 버전 백업
if git diff --quiet -- youtube-univ.html; then :; else
  mkdir -p backups
  cp youtube-univ.html "backups/youtube-univ_$(date +%Y%m%d_%H%M%S).html" 2>/dev/null || true
fi

git add -A
git commit -m "Add: <영상 제목> (<video_id>)"
git push origin main
```

> 로컬에서 바로 열어 확인할 수도 있다(데이터를 `<script src>`로 로드하므로 `file://`에서도 서재·학습이 동작; 임베드 영상은 인터넷 필요). 공개 링크는 GitHub Pages.

---

## 출력 요약 (사용자 보고)

| 항목 | 내용 |
|---|---|
| 영상 제목 | ... |
| 자막 확보 | 자동 추출 / 복붙 (N줄) |
| 카테고리·태그 | ... |
| 라이브러리 누적 | N편 |
| 공개 링크 | https://kimda-woon.github.io/Youtube-university/ |

---

## 절대 금지 사항

1. **analysis에 `transcript` 필드 넣기 금지.** 자막 재출력은 가장 큰 토큰 낭비다. 자막은 STEP 1 스크립트만 디스크에 쓴다.
2. **영상마다 HTML 재생성 금지.** HTML은 정적 데이터 구동형. 새 강의는 `library.js` + `transcripts/<id>.js`만 추가.
3. **타임스탬프 추측 금지.** `transcripts/<id>.json`의 실제 start 값만 사용.
4. **자막 없이 분석 금지.** 자동 추출·복붙 모두 실패하면 분석하지 않고 사용자에게 알린다. 웹 검색/설명란으로 대체 금지.
5. **upsert 순서 준수:** 자막 저장 → 분석 → library upsert → HTML 확인 → 배포.

---

## 부록: scripts/ytu_pipeline.py (저장소에 없을 때 복원용)

저장소 `scripts/ytu_pipeline.py`가 없으면 **이 스킬 번들에 동봉된 `ytu_pipeline.py`**를 그 경로에 복사한다. 번들도 없는 예외 상황에서만 동봉 소스로 재작성한다. 모듈이 제공하는 함수:

- `extract_video_id(url_or_id)` → 11자 video_id
- `parse_transcript(raw)` → 입력 자동 판별(자동추출 JSON / 복붙 5형식) → `[{start:int, text:str}]`
- `save_transcript(base, video_id, segments)` → `transcripts/<id>.json` + `<id>.js`
- `upsert_library(base, entry)` → `library.json` + `library.js` 갱신, 총 강의 수 반환 (중복 video_id는 갱신, thumbnail 자동 부여)
