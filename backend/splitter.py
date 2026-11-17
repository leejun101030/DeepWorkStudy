"""PDF -> 문제 단위 분할. 2단 편집, 지문 묶음([1~3]), 단/쪽 넘어가는 문제를 처리."""
import io, re
import fitz
from PIL import Image

NUM_RE = re.compile(r'^\s*(\d{1,3})\s*[.\)]\s*\S')
PASSAGE_RE = re.compile(r'\[\s*(\d{1,3})\s*[~∼\-–]\s*(\d{1,3})\s*\]')
ZOOM = 2.0

def _lines(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            if t:
                out.append((t, fitz.Rect(l["bbox"])))
    return sorted(out, key=lambda x: (x[1].y0, x[1].x0))

def _render(doc, clips):
    imgs = []
    for pno, r in clips:
        pix = doc[pno].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=r)
        imgs.append(Image.open(io.BytesIO(pix.tobytes("png"))))
    w, h = max(i.width for i in imgs), sum(i.height for i in imgs)
    canvas, y = Image.new("RGB", (w, h), "white"), 0
    for i in imgs:
        canvas.paste(i, (0, y)); y += i.height
    buf = io.BytesIO(); canvas.save(buf, "PNG")
    return buf.getvalue()

def parse_choices(text):
    parts = re.split(r'(?=[①②③④⑤])', text)
    if len(parts) >= 5:  # 앞부분(발문) + 선지 4개 이상
        return parts[0].strip(), [p.strip() for p in parts[1:]]
    return text.strip(), None

def split_questions(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    problems, passages = {}, []
    expected, current = None, None
    for pno, page in enumerate(doc):
        W, H = page.rect.width, page.rect.height
        lines = [(t, r) for t, r in _lines(page) if H * 0.04 < r.y0 < H * 0.95]
        if not lines:
            continue
        two = sum(1 for _, r in lines if r.x0 > W * 0.5) > 0.2 * len(lines)
        cols = [(0, W / 2), (W / 2, W)] if two else [(0, W)]
        for cx0, cx1 in cols:
            cl = [(t, r) for t, r in lines if cx0 <= r.x0 < cx1]
            if not cl:
                continue
            left = sorted(r.x0 for _, r in cl)[len(cl) // 10]
            top, bottom = min(r.y0 for _, r in cl) - 2, max(r.y1 for _, r in cl) + 2
            items = []
            for t, r in cl:
                m = PASSAGE_RE.search(t)
                if m and r.x0 < left + W * 0.06:
                    items.append(("P", r.y0, (int(m[1]), int(m[2])))); continue
                m = NUM_RE.match(t)
                if m and r.x0 < left + W * 0.04:
                    n = int(m[1])
                    if expected is None or n == expected:  # 번호 연속성으로 오탐 제거
                        items.append(("Q", r.y0, n)); expected = n + 1
            first_y = items[0][1] if items else bottom
            if current is not None and first_y - top > 4:  # 이전 단/쪽에서 이어지는 영역
                rect = fitz.Rect(cx0, top, cx1, first_y - 2)
                current["clips"].append((pno, rect)); current["text"] += "\n" + page.get_text(clip=rect)
            for i, (kind, y, val) in enumerate(items):
                end = items[i + 1][1] if i + 1 < len(items) else bottom
                rect = fitz.Rect(cx0, y - 2, cx1, end - 2)
                obj = {"clips": [(pno, rect)], "text": page.get_text(clip=rect)}
                if kind == "P":
                    obj["range"] = val; passages.append(obj)
                else:
                    obj["number"] = val; problems[val] = obj
                current = obj
    result = []
    for n in sorted(problems):
        p = problems[n]
        stem, choices = parse_choices(p["text"])
        p.update(stem=stem, choices=choices, png=_render(doc, p["clips"]))
        p["passage_idx"] = next((i for i, ps in enumerate(passages) if ps["range"][0] <= n <= ps["range"][1]), None)
        result.append(p)
    for ps in passages:
        ps["png"] = _render(doc, ps["clips"])
    return result, passages, len(doc)

def parse_answers(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = "\n".join(p.get_text() for p in doc)
    ans, sol = {}, {}
    for m in re.finditer(r'(?<!\d)(\d{1,3})\s*[.\):]?\s*(?:정답\s*)?([①②③④⑤])', text):
        ans.setdefault(int(m[1]), m[2])
    for m in re.finditer(r'(?m)^\s*(\d{1,3})\s*[.\):]\s*(\S.{0,100})$', text):
        ans.setdefault(int(m[1]), m[2].strip())
    marks = list(re.finditer(r'(?m)^\s*(\d{1,3})\s*[.\)]', text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        sol.setdefault(int(m[1]), text[m.end():end].strip()[:3000])
    return ans, sol
