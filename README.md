# 문제은행 (족보닷컴형)

## 구조
```
GitHub Pages (frontend/)  ──JWT──▶  FastAPI (backend/, Render·Fly 등)
        │                                  │  PDF 분할·분류·변형·PDF 조판
        └────────── Supabase ◀─────────────┘  Auth · Postgres · Storage
```
## 처리 흐름
1. 업로드: 토큰 선차감(쪽수×1) → 등급별 쪽수 한도 확인
2. 분할: 2단 감지 → 문항번호 연속성 검사 → 지문 `[a~b]` 묶음 → 단·쪽 이어짐 병합 → PNG 저장
3. 답지: `N ③` 표, `N. 값` 줄, 번호별 해설 구간 파싱 → 번호 매칭
4. 분류: 키워드 점수(과목·학년의 단원) → 신뢰도<0.55면 LLM → 그래도 낮으면 `review` 상태
5. 문제지: 단원 균등 할당 → 난이도 필터 → 지문 묶음 통째 선택 → 2단 PDF + 정답지
6. 변형: 과목 종류(kind)별 규칙 프롬프트, 이미지 문제는 비전 입력, 원본과 `parent_id`로 연결

## 설정
1. Supabase 프로젝트 생성 → `db/schema.sql`, `db/seed.sql` 실행 → Storage에 비공개 버킷 `files` 생성
2. 백엔드 환경변수: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `ANTHROPIC_API_KEY`, `ALLOW_ORIGINS`(Pages 주소)
   실행: `cd backend && pip install -r requirements.txt && uvicorn main:app`
3. `frontend/config.js` 값 입력 → GitHub Pages(Settings > Pages > GitHub Actions) 배포

## 알려진 한계
- 스캔본(이미지 PDF)은 텍스트가 없어 분할 불가 → OCR 단계 추가 필요
- 문제지 PDF에서 문제 이미지 안의 원래 번호가 그대로 보임 (정답지에 원본 번호 병기)
- 저작권이 있는 시험지는 공개 설정(`is_public`) 시 주의
