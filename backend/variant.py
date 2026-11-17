"""문제 변형: 숫자/상황/선지를 바꾼 새 문제를 LLM으로 생성 (이미지 문제는 비전 입력 사용)."""
import base64, json, os, re
import httpx

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
RULES = {
 "math": "수치와 조건을 바꾸되 풀이 구조와 난이도는 유지. 정답을 직접 다시 계산해 검증.",
 "korean": "지문은 그대로 두고 발문·선지·근거 위치를 바꿔 같은 유형의 새 문항 생성.",
 "social": "사례와 자료를 바꾸되 같은 개념을 묻는다.",
 "science": "수치·상황·자료를 바꾸되 같은 개념과 풀이 구조 유지.",
 "english": "같은 유형으로 새 문항 생성.", "other": "같은 유형으로 새 문항 생성."}

def make_variant(problem, kind, image_bytes=None, passage_text=""):
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key: raise RuntimeError("ANTHROPIC_API_KEY 미설정")
    content = []
    if image_bytes:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                        "data": base64.b64encode(image_bytes).decode()}})
    prompt = (f"원본 문제의 변형 문제를 1개 만드세요. 규칙: {RULES.get(kind, RULES['other'])}\n"
              f"원본 텍스트:\n{problem.get('text') or ''}\n지문:\n{passage_text[:3000]}\n"
              '순수 JSON만 출력: {"text":"발문","choices":["...","..."]|null,"answer":"...","solution":"..."}')
    content.append({"type": "text", "text": prompt})
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=120,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        json={"model": MODEL, "max_tokens": 1500, "messages": [{"role": "user", "content": content}]})
    raw = re.sub(r'```json|```', '', r.json()["content"][0]["text"]).strip()
    return json.loads(raw)
