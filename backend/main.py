import math, os, uuid
from typing import Optional
import fitz
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client

import builder, classifier, splitter, variant

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("ALLOW_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])
COST = {"ingest_page": 1, "variant": 3, "exam": 2}
BUCKET = "files"

def auth(h: str):
    u = sb.auth.get_user(h.removeprefix("Bearer ").strip())
    if not u or not u.user: raise HTTPException(401, "로그인이 필요합니다")
    prof = sb.table("profiles").select("*, tiers(*)").eq("id", u.user.id).single().execute().data
    return u.user.id, prof

def spend(uid, amount, reason):
    if not sb.rpc("spend_tokens", {"p_user": uid, "p_amount": amount, "p_reason": reason}).execute().data:
        raise HTTPException(402, f"토큰이 부족합니다 (필요 {amount})")

def put(path, data, ctype):
    sb.storage.from_(BUCKET).upload(path, data, {"content-type": ctype}); return path

def get(path): return sb.storage.from_(BUCKET).download(path)

@app.post("/ingest")
def ingest(question: UploadFile = File(...), answer: Optional[UploadFile] = File(None),
           title: str = Form(...), subject_id: int = Form(...), grade: int = Form(...),
           year: Optional[int] = Form(None), authorization: str = Header(...)):
    uid, prof = auth(authorization)
    qbytes = question.file.read()
    abytes = answer.file.read() if answer else None
    pages = len(fitz.open(stream=qbytes, filetype="pdf"))
    if pages > prof["tiers"]["max_upload_pages"]:
        raise HTTPException(403, f"등급 한도 초과 (최대 {prof['tiers']['max_upload_pages']}쪽)")
    spend(uid, pages * COST["ingest_page"], "ingest")
    subj = sb.table("subjects").select("*").eq("id", subject_id).single().execute().data
    units = sb.table("units").select("*").eq("subject_id", subject_id).eq("grade", grade).execute().data
    probs, passages, _ = splitter.split_questions(qbytes)
    ans, sol = splitter.parse_answers(abytes) if abytes else ({}, {})
    sid = str(uuid.uuid4())
    src = {"id": sid, "owner": uid, "title": title, "subject_id": subject_id, "grade": grade, "year": year,
           "page_count": pages, "question_path": put(f"{uid}/{sid}/question.pdf", qbytes, "application/pdf")}
    if abytes: src["answer_path"] = put(f"{uid}/{sid}/answer.pdf", abytes, "application/pdf")
    sb.table("sources").insert(src).execute()
    pid = []
    for i, ps in enumerate(passages):
        row = {"id": str(uuid.uuid4()), "source_id": sid, "num_from": ps["range"][0], "num_to": ps["range"][1],
               "text": ps["text"], "image_path": put(f"{uid}/{sid}/passage_{i}.png", ps["png"], "image/png")}
        sb.table("passages").insert(row).execute(); pid.append((row["id"], ps["text"]))
    rows, review = [], 0
    for p in probs:
        ptext = pid[p["passage_idx"]][1] if p["passage_idx"] is not None else ""
        qtype = classifier.guess_qtype(p["stem"], p["choices"])
        unit_id, conf, status = classifier.classify(p["text"], units, ptext)
        review += status == "review"
        rows.append({"source_id": sid, "owner": uid, "number": p["number"], "subject_id": subject_id,
            "unit_id": unit_id, "grade": grade, "qtype": qtype, "difficulty": classifier.guess_difficulty(p["stem"], qtype),
            "passage_id": pid[p["passage_idx"]][0] if p["passage_idx"] is not None else None,
            "text": p["stem"], "choices": p["choices"], "answer": ans.get(p["number"]), "solution": sol.get(p["number"]),
            "image_path": put(f"{uid}/{sid}/q_{p['number']}.png", p["png"], "image/png"),
            "confidence": conf, "status": status})
    if rows: sb.table("problems").insert(rows).execute()
    return {"source_id": sid, "problems": len(rows), "passages": len(pid), "needs_review": review,
            "answers_matched": sum(1 for r in rows if r["answer"])}

class ExamReq(BaseModel):
    title: str
    subject_id: int
    unit_ids: list[int]
    count: int = 20
    difficulties: Optional[list[int]] = None
    include_variants: bool = False

@app.post("/exams/build")
def build_exam(req: ExamReq, authorization: str = Header(...)):
    uid, _ = auth(authorization)
    q = (sb.table("problems").select("*").eq("subject_id", req.subject_id).in_("unit_id", req.unit_ids)
         .neq("status", "review").or_(f"owner.eq.{uid},is_public.eq.true"))
    if not req.include_variants: q = q.eq("is_variant", False)
    chosen = builder.select(q.execute().data, req.unit_ids, req.count, req.difficulties)
    if not chosen: raise HTTPException(404, "조건에 맞는 문제가 없습니다")
    spend(uid, COST["exam"], "exam")
    items, key, shown = [], [], set()
    for pos, p in enumerate(chosen, 1):
        if p["passage_id"] and p["passage_id"] not in shown:
            shown.add(p["passage_id"])
            ps = sb.table("passages").select("image_path").eq("id", p["passage_id"]).single().execute().data
            items.append({"kind": "img", "data": get(ps["image_path"])})
        items.append({"kind": "img", "data": get(p["image_path"])} if p["image_path"]
                     else {"kind": "text", "data": f"{pos}. {p['text']}\n" + "\n".join(p["choices"] or [])})
        key.append((pos, p["number"], p["answer"]))
    pdf = builder.compose_pdf(req.title, items, key)
    eid = str(uuid.uuid4()); path = put(f"{uid}/exams/{eid}.pdf", pdf, "application/pdf")
    sb.table("exams").insert({"id": eid, "owner": uid, "title": req.title, "config": req.model_dump(), "pdf_path": path}).execute()
    sb.table("exam_items").insert([{"exam_id": eid, "problem_id": p["id"], "position": i} for i, p in enumerate(chosen, 1)]).execute()
    url = sb.storage.from_(BUCKET).create_signed_url(path, 3600)["signedURL"]
    return {"exam_id": eid, "count": len(chosen), "url": url}

@app.post("/problems/{problem_id}/variant")
def make_variant(problem_id: str, authorization: str = Header(...)):
    uid, prof = auth(authorization)
    if not prof["tiers"]["can_variant"]: raise HTTPException(403, "변형 기능은 상위 등급에서 사용 가능합니다")
    p = sb.table("problems").select("*").eq("id", problem_id).single().execute().data
    if p["owner"] != uid and not p["is_public"]: raise HTTPException(403)
    spend(uid, COST["variant"], "variant")
    kind = sb.table("subjects").select("kind").eq("id", p["subject_id"]).single().execute().data["kind"]
    ptext = sb.table("passages").select("text").eq("id", p["passage_id"]).single().execute().data["text"] if p["passage_id"] else ""
    v = variant.make_variant(p, kind, get(p["image_path"]) if p["image_path"] else None, ptext)
    new = {k: p[k] for k in ("source_id", "subject_id", "unit_id", "grade", "qtype", "difficulty", "passage_id", "number")}
    new.update(owner=uid, text=v["text"], choices=v.get("choices"), answer=v.get("answer"), solution=v.get("solution"),
               is_variant=True, parent_id=p["id"], status="auto", confidence=p["confidence"])
    return sb.table("problems").insert(new).execute().data[0]
