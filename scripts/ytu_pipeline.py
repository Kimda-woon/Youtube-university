"""
유튜브 대학 파이프라인 모듈
- 입력: (A) 자동 추출 JSON  [{text,start,duration}, ...]
        (B) 수동 복붙 타임스탬프 자막 (5가지 형식)
- 출력: transcripts/<id>.json / transcripts/<id>.js  (자막)
        library.json / library.js                    (분석 누적, 자막 미포함)

핵심 설계:
  * 자막은 Claude가 다시 출력하지 않는다 -> 이 스크립트가 디스크에 직접 쓴다.
  * analysis(엔트리)에는 transcript 필드를 넣지 않는다 -> 출력 토큰 절감.
  * HTML은 정적 템플릿 1개. library.js 를 읽고, 자막은 필요할 때 transcripts/<id>.js 를 늦게 로드.
"""
import re
import os
import json
import datetime

TS_INLINE = re.compile(r'[\(\[]((\d+):(\d{2})(?::(\d{2}))?)\s*[\)\]]\s*(.*)')
TS_PLAIN = re.compile(r'^(\d+:\d{2}(?::\d{2})?)\s{2,}(.*)')
TS_ONLY = re.compile(r'^(\d+:\d{2}(?::\d{2})?)$')
TS_BRACKET_ONLY = re.compile(r'^[\(\[](\d+:\d{2}(?::\d{2})?)[\)\]]$')


def _parse_ts(ts_str):
    parts = ts_str.strip().split(':')
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        return None
    return None


def extract_video_id(url_or_id: str) -> str:
    """youtube.com/watch?v=, youtu.be/, shorts/, embed/ 또는 11자 ID 직접 입력 모두 처리."""
    s = url_or_id.strip()
    m = re.search(r'(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})', s)
    if m:
        return m.group(1)
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', s):
        return s
    raise ValueError(f"video_id를 추출할 수 없습니다: {url_or_id!r}")


def parse_fetched_json(json_text: str) -> list:
    """youtube_transcript_api --format json 출력 파싱 -> [{start:int, text:str}]."""
    data = json.loads(json_text)
    segs = []
    seen = set()
    for item in data:
        txt = (item.get("text") or "").replace("\n", " ").strip()
        start = item.get("start")
        if start is None or not txt:
            continue
        sec = int(round(float(start)))
        if txt in seen:
            continue
        seen.add(txt)
        segs.append({"start": sec, "text": txt})
    return sorted(segs, key=lambda x: x["start"])


def parse_pasted(text: str) -> list:
    """복붙 타임스탬프 자막(형식 A~E) 파싱 -> [{start:int, text:str}]."""
    segments = []
    seen = set()
    lines = text.strip().split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # A/B 인라인: (0:00) 텍스트  /  [0:00] 텍스트
        m = TS_INLINE.match(line)
        if m:
            sec = _parse_ts(m.group(1))
            txt = m.group(5).strip()
            while i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt and not TS_INLINE.match(nxt) and not TS_PLAIN.match(nxt) and not TS_ONLY.match(nxt):
                    txt += ' ' + nxt
                    i += 1
                else:
                    break
            if sec is not None and txt and txt not in seen:
                seen.add(txt)
                segments.append({"start": sec, "text": txt})
            i += 1
            continue

        # C 단독 줄(괄호): [0:00:00] -> 다음 줄(들)이 텍스트
        mb = TS_BRACKET_ONLY.match(line)
        if mb:
            sec = _parse_ts(mb.group(1))
            parts = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt or re.match(r'^[\(\[]\d+:\d{2}', nxt):
                    break
                parts.append(nxt)
                j += 1
            txt = ' '.join(parts).strip()
            if sec is not None and txt and txt not in seen:
                seen.add(txt)
                segments.append({"start": sec, "text": txt})
            i = j
            continue

        # D 공백 구분: 0:00  텍스트
        m = TS_PLAIN.match(line)
        if m:
            sec = _parse_ts(m.group(1))
            txt = m.group(2).strip()
            if sec is not None and txt and txt not in seen:
                seen.add(txt)
                segments.append({"start": sec, "text": txt})
            i += 1
            continue

        # E YouTube 기본 자막 뷰어: 0:00 단독 줄 + 다음 줄(들) 텍스트
        m = TS_ONLY.match(line)
        if m:
            sec = _parse_ts(m.group(1))
            parts = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt or TS_ONLY.match(nxt) or TS_INLINE.match(nxt):
                    break
                parts.append(nxt)
                j += 1
            txt = ' '.join(parts).strip()
            if sec is not None and txt and txt not in seen:
                seen.add(txt)
                segments.append({"start": sec, "text": txt})
            i = j
            continue

        i += 1

    return sorted(segments, key=lambda x: x['start'])


def parse_transcript(raw: str) -> list:
    """입력을 자동 판별: JSON 배열이면 fetched, 아니면 pasted."""
    s = raw.strip()
    if s.startswith('[') and '"start"' in s:
        try:
            return parse_fetched_json(s)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass  # JSON 파싱 실패 시 텍스트 파서로 폴백
    return parse_pasted(s)


def save_transcript(base_dir: str, video_id: str, segments: list):
    """transcripts/<id>.json + transcripts/<id>.js 저장."""
    tdir = os.path.join(base_dir, "transcripts")
    os.makedirs(tdir, exist_ok=True)
    with open(os.path.join(tdir, f"{video_id}.json"), "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    js = (
        "window.YTU_TX=window.YTU_TX||{};\n"
        f"window.YTU_TX[{json.dumps(video_id)}]={json.dumps(segments, ensure_ascii=False)};\n"
    )
    with open(os.path.join(tdir, f"{video_id}.js"), "w", encoding="utf-8") as f:
        f.write(js)


def upsert_library(base_dir: str, entry: dict) -> int:
    """library.json upsert(중복 video_id 갱신) 후 library.js 재생성. 반환: 총 강의 수."""
    lib_path = os.path.join(base_dir, "library.json")
    try:
        with open(lib_path, encoding="utf-8") as f:
            library = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        library = []

    vid = entry["video_id"]
    entry.setdefault("thumbnail", f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg")

    idx = next((k for k, x in enumerate(library) if x.get("video_id") == vid), None)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    if idx is not None:
        entry["addedAt"] = library[idx].get("addedAt", now)
        entry["updatedAt"] = now
        library[idx] = entry
    else:
        entry["addedAt"] = now
        entry["updatedAt"] = now
        library.insert(0, entry)

    with open(lib_path, "w", encoding="utf-8") as f:
        json.dump(library, f, ensure_ascii=False, indent=2)
    with open(os.path.join(base_dir, "library.js"), "w", encoding="utf-8") as f:
        f.write("window.YTU_LIBRARY=" + json.dumps(library, ensure_ascii=False) + ";\n")
    return len(library)
