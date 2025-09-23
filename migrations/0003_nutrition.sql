-- Справочник продуктов
create table if not exists foods (
  id bigserial primary key,
  name text not null,
  name_norm text generated always as (lower(name)) stored,
  kcal_100g numeric(6,2) not null,
  created_at timestamptz not null default now()
);
create unique index if not exists ux_foods_name_norm on foods(name_norm);

-- Приемы пищи по дням
create table if not exists meals (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  at_date date not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_meals_user_date on meals(user_id, at_date);

-- Позиции приема пищи
create table if not exists meal_items (
  id bigserial primary key,
  meal_id bigint not null references meals(id) on delete cascade,
  food_id bigint not null references foods(id),
  grams numeric(6,1) not null,
  kcal numeric(8,2) not null
);
create index if not exists idx_meal_items_meal on meal_items(meal_id);
