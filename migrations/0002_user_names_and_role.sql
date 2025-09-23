alter table users
  add column if not exists first_name  text,
  add column if not exists last_name   text,
  add column if not exists display_name text,
  add column if not exists role text not null default 'basic'
    check (role in ('admin','basic','advanced'));

-- На старые записи можно поставить display_name по username
update users
set display_name = coalesce(display_name, username, 'пользователь')
where display_name is null;