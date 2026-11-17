-- Supabase(Postgres) 스키마. SQL Editor에서 실행
create table tiers(
  name text primary key, monthly_tokens int not null,
  max_upload_pages int not null, can_variant boolean not null default false);
insert into tiers values ('free',20,30,false),('basic',200,150,true),('pro',1000,600,true),('admin',999999,9999,true);

create table profiles(
  id uuid primary key references auth.users on delete cascade,
  display_name text, tier text not null default 'free' references tiers(name),
  tokens int not null default 20, created_at timestamptz default now());

create function handle_new_user() returns trigger language plpgsql security definer as $$
begin insert into profiles(id,display_name) values (new.id, split_part(new.email,'@',1)); return new; end $$;
create trigger on_auth_user_created after insert on auth.users for each row execute function handle_new_user();

create table token_ledger(
  id bigserial primary key, user_id uuid references profiles(id) on delete cascade,
  delta int not null, reason text not null, created_at timestamptz default now());

create function spend_tokens(p_user uuid, p_amount int, p_reason text) returns boolean
language plpgsql security definer as $$
begin
  update profiles set tokens = tokens - p_amount where id = p_user and tokens >= p_amount;
  if not found then return false; end if;
  insert into token_ledger(user_id,delta,reason) values (p_user,-p_amount,p_reason);
  return true;
end $$;

-- 교육과정 분류 (과목 > 학년 > 단원 트리)
create table subjects(id serial primary key, name text unique not null,
  kind text not null check (kind in ('math','korean','social','science','english','other')));
create table units(id serial primary key, subject_id int references subjects(id),
  grade int not null, name text not null, parent_id int references units(id),
  keywords text[] not null default '{}');

create table sources(
  id uuid primary key default gen_random_uuid(), owner uuid references profiles(id),
  title text, subject_id int references subjects(id), grade int, year int,
  question_path text, answer_path text, page_count int, created_at timestamptz default now());

create table passages(  -- 국어/영어 지문 묶음
  id uuid primary key default gen_random_uuid(), source_id uuid references sources(id) on delete cascade,
  num_from int, num_to int, text text, image_path text);

create table problems(
  id uuid primary key default gen_random_uuid(),
  source_id uuid references sources(id) on delete cascade,
  owner uuid references profiles(id),
  number int, subject_id int references subjects(id), unit_id int references units(id), grade int,
  qtype text check (qtype in ('mc','short','essay')), difficulty smallint check (difficulty between 1 and 5),
  passage_id uuid references passages(id),
  text text, choices jsonb, image_path text,
  answer text, solution text,
  confidence real, status text not null default 'auto' check (status in ('auto','review','approved')),
  is_variant boolean not null default false, parent_id uuid references problems(id),
  is_public boolean not null default false, created_at timestamptz default now());
create index on problems(subject_id, unit_id, difficulty);

create table exams(
  id uuid primary key default gen_random_uuid(), owner uuid references profiles(id),
  title text, config jsonb, pdf_path text, created_at timestamptz default now());
create table exam_items(exam_id uuid references exams(id) on delete cascade,
  problem_id uuid references problems(id), position int, primary key(exam_id, position));

-- RLS: 읽기는 본인 소유 또는 공개 문제만. 쓰기는 백엔드(service key)만 수행
alter table profiles enable row level security;
alter table problems enable row level security;
alter table exams enable row level security;
alter table token_ledger enable row level security;
create policy p_self on profiles for select using (id = auth.uid());
create policy p_prob on problems for select using (owner = auth.uid() or is_public);
create policy p_exam on exams for select using (owner = auth.uid());
create policy p_ledger on token_ledger for select using (user_id = auth.uid());
alter table subjects enable row level security; alter table units enable row level security;
create policy s_read on subjects for select using (true);
create policy u_read on units for select using (true);
-- Storage: 비공개 버킷 'files' 생성 필요
