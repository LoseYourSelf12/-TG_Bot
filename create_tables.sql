-- =========================================================
-- Nutrition Telegram Bot (MVP) - PostgreSQL schema
-- =========================================================
-- Рекомендуется выполнять под пользователем с правами CREATE EXTENSION/SCHEMA.

BEGIN;

-- 1) Schema
CREATE SCHEMA IF NOT EXISTS nutrition_bot;

-- 2) Extensions (внутри текущей БД)
-- pgcrypto: gen_random_uuid()
-- citext: case-insensitive text
-- pg_trgm: trigram similarity for fuzzy search
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 3) Helper: updated_at trigger
CREATE OR REPLACE FUNCTION nutrition_bot.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

-- =========================================================
-- USERS
-- =========================================================

CREATE TABLE IF NOT EXISTS nutrition_bot.users (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tg_user_id       bigint NOT NULL UNIQUE,      -- Telegram numeric user id
  username         text,
  first_name       text,
  last_name        text,
  language_code    text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON nutrition_bot.users
FOR EACH ROW
EXECUTE FUNCTION nutrition_bot.set_updated_at();

-- Профиль: пока минимум, но с местом под расширение
CREATE TABLE IF NOT EXISTS nutrition_bot.user_profile (
  user_id            uuid PRIMARY KEY REFERENCES nutrition_bot.users(id) ON DELETE CASCADE,
  timezone_iana      text NOT NULL DEFAULT 'Europe/Moscow', -- по умолчанию МСК
  utc_offset_minutes integer NOT NULL DEFAULT 180,          -- UTC+3
  -- будущие поля:
  sex                text,
  age                integer,
  height_cm          numeric(6,2),
  weight_kg          numeric(6,2),
  goal               text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_user_profile_updated_at
BEFORE UPDATE ON nutrition_bot.user_profile
FOR EACH ROW
EXECUTE FUNCTION nutrition_bot.set_updated_at();

-- =========================================================
-- PRODUCT REFERENCE (справочник) + synonyms + user products
-- =========================================================

-- Справочник продуктов
CREATE TABLE IF NOT EXISTS nutrition_bot.products_ref (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name            citext NOT NULL,               -- "Макароны из твердых сортов"
  brand           citext,                        -- опционально
  kcal_per_100g   numeric(8,2) NOT NULL CHECK (kcal_per_100g >= 0),
  protein_100g    numeric(8,2) CHECK (protein_100g >= 0),
  fat_100g        numeric(8,2) CHECK (fat_100g >= 0),
  carbs_100g      numeric(8,2) CHECK (carbs_100g >= 0),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),

  -- На MVP можно сделать уникальность по name+brand (brand NULL допускается)
  CONSTRAINT uq_products_ref_name_brand UNIQUE (name, brand)
);

CREATE TRIGGER trg_products_ref_updated_at
BEFORE UPDATE ON nutrition_bot.products_ref
FOR EACH ROW
EXECUTE FUNCTION nutrition_bot.set_updated_at();

-- Синонимы к справочнику (например, "спагетти" -> продукт "макароны ...")
CREATE TABLE IF NOT EXISTS nutrition_bot.product_synonyms (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_ref_id  uuid NOT NULL REFERENCES nutrition_bot.products_ref(id) ON DELETE CASCADE,
  synonym         citext NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT uq_product_synonyms UNIQUE (product_ref_id, synonym)
);

-- Пользовательские продукты (если человек вводит свое название, маппинг можно проставить позже)
CREATE TABLE IF NOT EXISTS nutrition_bot.products_user (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             uuid NOT NULL REFERENCES nutrition_bot.users(id) ON DELETE CASCADE,
  name                citext NOT NULL,
  mapped_product_ref_id uuid REFERENCES nutrition_bot.products_ref(id) ON DELETE SET NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT uq_products_user UNIQUE (user_id, name)
);

CREATE TRIGGER trg_products_user_updated_at
BEFORE UPDATE ON nutrition_bot.products_user
FOR EACH ROW
EXECUTE FUNCTION nutrition_bot.set_updated_at();

-- Индексы для "похожего поиска" (вывод топ-10 совпадений / синонимов)
-- Требует pg_trgm
CREATE INDEX IF NOT EXISTS idx_products_ref_name_trgm
  ON nutrition_bot.products_ref USING gin (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_product_synonyms_synonym_trgm
  ON nutrition_bot.product_synonyms USING gin (synonym gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_products_user_name_trgm
  ON nutrition_bot.products_user USING gin (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_product_synonyms_product_ref_id
  ON nutrition_bot.product_synonyms (product_ref_id);

CREATE INDEX IF NOT EXISTS idx_products_user_user_id
  ON nutrition_bot.products_user (user_id);

-- =========================================================
-- MEALS + ITEMS + PHOTOS
-- =========================================================

-- Прием пищи: храните date+time отдельно — так проще строить календарь/статистику.
CREATE TABLE IF NOT EXISTS nutrition_bot.meals (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES nutrition_bot.users(id) ON DELETE CASCADE,
  meal_date   date NOT NULL,
  meal_time   time NOT NULL,
  note        text,                               -- произвольное описание (можно дублировать items_raw)
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_meals_updated_at
BEFORE UPDATE ON nutrition_bot.meals
FOR EACH ROW
EXECUTE FUNCTION nutrition_bot.set_updated_at();

CREATE INDEX IF NOT EXISTS idx_meals_user_date
  ON nutrition_bot.meals (user_id, meal_date);

CREATE INDEX IF NOT EXISTS idx_meals_user_datetime
  ON nutrition_bot.meals (user_id, meal_date, meal_time);

-- Позиции внутри приема пищи
-- raw_name: то, что ввел пользователь ("макароны")
-- product_ref_id: выбранный элемент справочника (если выбрал)
-- user_product_id: выбранный кастомный продукт пользователя (если завели)
CREATE TABLE IF NOT EXISTS nutrition_bot.meal_items (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  meal_id         uuid NOT NULL REFERENCES nutrition_bot.meals(id) ON DELETE CASCADE,
  position        integer NOT NULL CHECK (position > 0),
  raw_name        text NOT NULL,
  product_ref_id  uuid REFERENCES nutrition_bot.products_ref(id) ON DELETE SET NULL,
  user_product_id uuid REFERENCES nutrition_bot.products_user(id) ON DELETE SET NULL,
  grams           numeric(10,2) CHECK (grams > 0),
  kcal_total      numeric(12,2) CHECK (kcal_total >= 0),

  created_at      timestamptz NOT NULL DEFAULT now(),

  -- Чтобы не было двойной привязки одновременно.
  CONSTRAINT chk_meal_items_single_mapping
    CHECK (NOT (product_ref_id IS NOT NULL AND user_product_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_meal_items_meal_id
  ON nutrition_bot.meal_items (meal_id);

CREATE INDEX IF NOT EXISTS idx_meal_items_product_ref_id
  ON nutrition_bot.meal_items (product_ref_id);

CREATE INDEX IF NOT EXISTS idx_meal_items_user_product_id
  ON nutrition_bot.meal_items (user_product_id);

-- Фото приема пищи
-- tg_file_id: для скачивания файла через Bot API в моменте
-- tg_file_unique_id: стабильный идентификатор файла (удобно для дедупликации)
CREATE TABLE IF NOT EXISTS nutrition_bot.meal_photos (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  meal_id            uuid NOT NULL REFERENCES nutrition_bot.meals(id) ON DELETE CASCADE,
  tg_file_id         text NOT NULL,
  tg_file_unique_id  text,
  local_path         text,          -- например: /data/photos/<user>/<date>/<uuid>.jpg
  mime_type          text,
  width              integer CHECK (width >= 0),
  height             integer CHECK (height >= 0),
  file_size_bytes    integer CHECK (file_size_bytes >= 0),
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_meal_photos_meal_id
  ON nutrition_bot.meal_photos (meal_id);

CREATE INDEX IF NOT EXISTS idx_meal_photos_unique_id
  ON nutrition_bot.meal_photos (tg_file_unique_id);

-- Часто полезно запрещать дубли для одного приема (если unique_id есть)
-- (если tg_file_unique_id NULL, уникальность не проверится)
CREATE UNIQUE INDEX IF NOT EXISTS uq_meal_photos_meal_unique_file
  ON nutrition_bot.meal_photos (meal_id, tg_file_unique_id)
  WHERE tg_file_unique_id IS NOT NULL;

-- =========================================================
-- Optional: VIEW for daily stats (удобно для "Статистики по дню")
-- =========================================================
CREATE OR REPLACE VIEW nutrition_bot.v_day_stats AS
SELECT
  m.user_id,
  m.meal_date,
  COUNT(DISTINCT m.id) AS meals_count,
  COALESCE(SUM(mi.kcal_total), 0) AS kcal_total,
  COUNT(mp.id) AS photos_count
FROM nutrition_bot.meals m
LEFT JOIN nutrition_bot.meal_items mi ON mi.meal_id = m.id
LEFT JOIN nutrition_bot.meal_photos mp ON mp.meal_id = m.id
GROUP BY m.user_id, m.meal_date;

COMMIT;
