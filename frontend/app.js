const sb = supabase.createClient(CFG.SUPABASE_URL, CFG.SUPABASE_ANON_KEY);
const $ = id => document.getElementById(id);
const say = t => $("msg").textContent = t || "";
async function token() { return (await sb.auth.getSession()).data.session?.access_token; }
async function api(path, opt = {}) {
  const r = await fetch(CFG.API_URL + path, { ...opt, headers: { ...(opt.headers || {}), Authorization: "Bearer " + await token() } });
  const j = await r.json(); if (!r.ok) throw new Error(j.detail || "오류"); return j;
}
async function signup() { const { error } = await sb.auth.signUp({ email: $("email").value, password: $("pw").value }); say(error?.message || "가입 완료. 이메일 인증 후 로그인하세요."); }
async function login() { const { error } = await sb.auth.signInWithPassword({ email: $("email").value, password: $("pw").value }); say(error?.message); init(); }
async function logout() { await sb.auth.signOut(); init(); }
async function init() {
  const { data: { session } } = await sb.auth.getSession();
  $("auth").hidden = !!session; $("app").hidden = !session; if (!session) return;
  const { data: p } = await sb.from("profiles").select("*").single();
  $("me").textContent = `${p.display_name} · ${p.tier} · 토큰 ${p.tokens}`;
  const { data: s } = await sb.from("subjects").select("*");
  $("subj").innerHTML = s.map(x => `<option value="${x.id}">${x.name}</option>`).join(""); loadUnits();
}
async function loadUnits() {
  const { data } = await sb.from("units").select("*").eq("subject_id", $("subj").value);
  $("units").innerHTML = data.map(u => `<label><input type="checkbox" value="${u.id}" style="width:auto"> ${u.grade}학년 ${u.name}</label><br>`).join("");
}
async function upload() {
  try {
    say("처리 중..."); const f = new FormData();
    f.append("question", $("qf").files[0]); if ($("af").files[0]) f.append("answer", $("af").files[0]);
    f.append("title", $("title").value); f.append("subject_id", $("subj").value); f.append("grade", $("grade").value);
    const r = await api("/ingest", { method: "POST", body: f });
    say(`문제 ${r.problems}개 저장 (답 매칭 ${r.answers_matched}, 검수 필요 ${r.needs_review})`); init();
  } catch (e) { say(e.message); }
}
async function build() {
  try {
    const unit_ids = [...document.querySelectorAll("#units input:checked")].map(x => +x.value);
    const r = await api("/exams/build", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: $("etitle").value || "문제지", subject_id: +$("subj").value, unit_ids,
        count: +$("count").value, include_variants: $("vari").checked }) });
    $("result").innerHTML = `<a href="${r.url}" target="_blank">PDF 열기 (${r.count}문항)</a>`; say(""); init();
  } catch (e) { say(e.message); }
}
init();
