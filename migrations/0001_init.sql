create table if not exists users (
    id bigserial primary key,
    tg_id bigint unique not null,
    username text,
    tz text not null default 'Europe/Moscow',
    sex text check (sex in ('male','female')),
    birth_date date,
    height_cm int,
    weight_kg numeric(5,2),
    activity_level text check (activity_level in ('sedentary','light','moderate','high','athlete')),
    tier text not null default 'basic',
    created_at timestamptz not null default now()
);


create index if not exists idx_users_tg_id on users(tg_id);