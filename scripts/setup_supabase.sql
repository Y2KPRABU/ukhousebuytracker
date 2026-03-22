-- Run this in Supabase SQL Editor once per project.
-- It creates the table used by cloud_storage.py.

create table if not exists public.user_checklists (
  user_id text primary key,
  checklist jsonb not null,
  updated_at timestamptz not null default now()
);

-- Helpful index if you later add non-PK lookups by updated_at.
create index if not exists idx_user_checklists_updated_at
  on public.user_checklists (updated_at desc);
