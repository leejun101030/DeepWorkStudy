"""문제지 구성(선택 알고리즘) + PDF 조판."""
import random
import fitz

def select(problems, unit_ids, count, difficulties=None):
    """단원별 균등 할당 -> 난이도 필터 -> 지문 묶음은 통째로 선택 -> 부족분 보충."""
    pool = [p for p in problems if not difficulties or p["difficulty"] in difficulties]
    by_unit = {u: [] for u in unit_ids}
    for p in pool:
        if p["unit_id"] in by_unit: by_unit[p["unit_id"]].append(p)
    quota = {u: count // len(unit_ids) for u in unit_ids}
    for u in list(unit_ids)[: count % len(unit_ids)]: quota[u] += 1
    chosen, used = [], set()
    for u in unit_ids:
        random.shuffle(by_unit[u]); seen, n = set(), 0
        for p in by_unit[u]:
            key = p["passage_id"] or p["id"]
            if key in seen or n >= quota[u]: continue
            grp = [p] if not p["passage_id"] else [q for q in by_unit[u] if q["passage_id"] == p["passage_id"]]
            if n + len(grp) > quota[u] and n > 0: continue
            seen.add(key)
            for q in sorted(grp, key=lambda x: x["number"] or 0):
                chosen.append(q); used.add(q["id"])
            n += len(grp)
    if len(chosen) < count:
        rest = [p for p in pool if p["id"] not in used and not p["passage_id"] and p["unit_id"] in by_unit]
        random.shuffle(rest); chosen += rest[: count - len(chosen)]
    return chosen

def compose_pdf(title, items, answer_key):
    """items: [{'kind':'img'|'text','data':bytes|str}], answer_key: [(pos, orig_no, answer)]"""
    doc = fitz.open(); A4 = fitz.paper_rect("a4"); M, GAP = 36, 14
    colw = (A4.width - 2 * M - 20) / 2; top, bottom = M + 30, A4.height - M
    st = {"page": None, "col": 0, "y": top}
    def new_page(head=True):
        st["page"] = doc.new_page(width=A4.width, height=A4.height)
        if head: st["page"].insert_text((M, M + 10), title, fontsize=14, fontname="korea")
        st["col"], st["y"] = 0, top
    new_page()
    for it in items:
        if it["kind"] == "img":
            pix = fitz.Pixmap(it["data"]); h = pix.height * colw / pix.width
        else:
            h = 14 * (len(it["data"]) / (colw / 7) + it["data"].count("\n") + 2)
        if st["y"] + h > bottom:
            st["col"] += 1; st["y"] = top
            if st["col"] > 1: new_page()
        x = M + st["col"] * (colw + 20); rect = fitz.Rect(x, st["y"], x + colw, st["y"] + h)
        if it["kind"] == "img": st["page"].insert_image(rect, stream=it["data"])
        else: st["page"].insert_textbox(rect, it["data"], fontsize=10, fontname="korea")
        st["y"] += h + GAP
    new_page(head=False)
    st["page"].insert_text((M, M + 10), "정답 (순번 / 원본 번호)", fontsize=13, fontname="korea")
    y = top
    for pos, no, ans in answer_key:
        st["page"].insert_text((M, y), f"{pos}번 (원본 {no}번): {ans or '-'}", fontsize=10, fontname="korea"); y += 16
        if y > bottom: new_page(head=False); y = top
    return doc.tobytes()
