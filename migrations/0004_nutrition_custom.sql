-- Разрешим кастомные позиции без связки на foods
alter table meal_items
  alter column food_id drop not null;

-- Храним имя и удельную калорийность для кастомной позиции
alter table meal_items
  add column if not exists food_name text,
  add column if not exists kcal_100g numeric(6,2);

-- Гарантия: должна быть либо ссылка на foods, либо пара (food_name, kcal_100g)
do $$
begin
  if not exists (
    select 1
    from information_schema.table_constraints
    where table_name = 'meal_items' and constraint_type = 'CHECK' and constraint_name = 'meal_items_food_check'
  ) then
    alter table meal_items
      add constraint meal_items_food_check
      check (
        food_id is not null
        or (food_name is not null and kcal_100g is not null)
      );
  end if;
end$$;
