-- Типы: weight, meal, custom_daily, custom_weekly, oneoff
create table if not exists reminders (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  kind text not null check (kind in ('weight','meal','custom_daily','custom_weekly','oneoff')),
  title text,                    -- для custom_* / oneoff (текст уведомления)
  enabled boolean not null default true,
  tz text not null,              -- freeze TZ на момент создания (обычно users.tz)
  created_at timestamptz not null default now()
);
create index if not exists idx_reminders_user on reminders(user_id);

-- Времена для daily/weekly (много записей на один reminder)
create table if not exists reminder_times (
  id bigserial primary key,
  reminder_id bigint not null references reminders(id) on delete cascade,
  hh smallint not null check (hh between 0 and 23),
  mm smallint not null default 0 check (mm between 0 and 59),
  unique(reminder_id, hh, mm)
);

-- Дни недели для weekly (пн..вс)
create table if not exists reminder_weekdays (
  reminder_id bigint not null references reminders(id) on delete cascade,
  dow smallint not null check (dow between 1 and 7), -- 1=Mon..7=Sun
  primary key (reminder_id, dow)
);

-- Одноразовые
create table if not exists reminder_oneoff (
  reminder_id bigint primary key references reminders(id) on delete cascade,
  run_at timestamptz not null,
  fired boolean not null default false
);

-- Snooze логика: одноразовые и обычные можно снести в эту таблицу на «перенос»
create table if not exists reminder_snoozes (
  id bigserial primary key,
  reminder_id bigint not null references reminders(id) on delete cascade,
  until_at timestamptz not null,     -- до какого времени отложено
  created_at timestamptz not null default now()
);
create index if not exists idx_snooze_until on reminder_snoozes(until_at);

-- Журнал отсылок для дедупликации (идемпотентность)
create table if not exists reminder_logs (
  id bigserial primary key,
  reminder_id bigint not null references reminders(id) on delete cascade,
  fired_at timestamptz not null,
  dedup_key text not null,           -- YYYY-MM-DDThh:mm: <reminder_id> (для daily/weekly)
  unique(reminder_id, dedup_key)
);
