"""분류: 1) 규칙(키워드 점수) -> 2) 신뢰도 낮으면 LLM -> 3) 그래도 낮으면 검수 대기(review)."""
import os, re
import httpx

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
REVIEW_THRESHOLD = 0.55

def guess_qtype(stem, choices):
    if choices: return "mc"
    if re.search(r'서술|논하시오|설명하시오|풀이 과정', stem): return "essay"
    return "short"

def guess_difficulty(stem, qtype):
    d = 3
    if len(stem) > 300: d += 1
    if len(stem) < 80: d -= 1
    if qtype == "essay": d += 1
    if re.search(r'<보기>|ㄱ\.|ㄴ\.|ㄷ\.', stem): d += 1
    if '[4점]' in stem: d += 1
    if '[2점]' in stem: d -= 1
    return max(1, min(5, d))

def rule_classify(text, units):
    t, scores = text.lower(), []
    for u in units:
        s = 0.0
        for kw in (u.get("keywords") or []):
            c = t.count(kw.lower())
            if c: s += (1 + 0.5 * (c - 1)) * (1 + len(kw) / 6)
        scores.append((s, u))
    scores.sort(key=lambda x: -x[0])
    if not scores or scores[0][0] == 0: return None, 0.0
    top, second = scores[0][0], scores[1][0] if len(scores) > 1 else 0
    conf = 0.5 * ((top - second) / (top + 1)) + 0.5 * min(top, 4) / 4
    return scores[0][1], round(conf, 3)

def llm_classify(text, units):
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key: return None
    menu = "\n".join(f'{u["id"]}: {u["name"]}' for u in units)
    prompt = f"다음 문제가 속한 단원 id 하나만 숫자로 답하세요.\n[단원]\n{menu}\n[문제]\n{text[:1500]}"
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=60,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        json={"model": MODEL, "max_tokens": 10, "messages": [{"role": "user", "content": prompt}]})
    m = re.search(r'\d+', r.json()["content"][0]["text"])
    return int(m[0]) if m else None

def classify(text, units, passage_text=""):
    unit, conf = rule_classify(text + "\n" + passage_text, units)
    if conf < REVIEW_THRESHOLD:
        uid = llm_classify(text + "\n" + passage_text, units)
        if uid and any(u["id"] == uid for u in units):
            unit, conf = next(u for u in units if u["id"] == uid), max(conf, 0.7)
    status = "auto" if unit and conf >= REVIEW_THRESHOLD else "review"
    return (unit["id"] if unit else None), conf, status
