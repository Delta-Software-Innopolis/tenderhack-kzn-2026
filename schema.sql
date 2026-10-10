PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = OFF;

-- Позиции КТРУ
CREATE TABLE IF NOT EXISTS ktru_position (
    code                     TEXT PRIMARY KEY,
    name                     TEXT NOT NULL,
    okpd2_code               TEXT,
    okpd2_name               TEXT,
    status                   TEXT,
    actual                   INTEGER DEFAULT 1,
    is_template              INTEGER DEFAULT 0,
    application_date_start   TEXT,
    application_date_end     TEXT
);

-- Характеристики
CREATE TABLE IF NOT EXISTS ktru_characteristic (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    position_code   TEXT NOT NULL,
    code            TEXT,
    name            TEXT NOT NULL,
    type            INTEGER,
    kind            INTEGER,
    is_required     INTEGER DEFAULT 0,
    choice_type     INTEGER,
    FOREIGN KEY (position_code) REFERENCES ktru_position(code) ON DELETE CASCADE
);

-- Значения характеристик
CREATE TABLE IF NOT EXISTS ktru_characteristic_value (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    characteristic_id   INTEGER NOT NULL,
    value_code          TEXT,
    quality_description TEXT,
    okei_code           TEXT,
    okei_name           TEXT,
    value_format        TEXT,
    min_value           REAL,
    max_value           REAL,
    min_notation        TEXT,
    max_notation        TEXT,
    concrete_value      REAL,
    FOREIGN KEY (characteristic_id) REFERENCES ktru_characteristic(id) ON DELETE CASCADE
);

-- Товары (products) — оставляем, они есть в позиции
CREATE TABLE IF NOT EXISTS ktru_product (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    position_code   TEXT NOT NULL,
    trade_name      TEXT,
    manufacturer    TEXT,
    country_code    TEXT,
    country_name    TEXT,
    price           REAL,
    FOREIGN KEY (position_code) REFERENCES ktru_position(code) ON DELETE CASCADE
);

-- Рубрикаторы
CREATE TABLE IF NOT EXISTS ktru_rubricator (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    position_code   TEXT NOT NULL,
    code            TEXT,
    name            TEXT,
    FOREIGN KEY (position_code) REFERENCES ktru_position(code) ON DELETE CASCADE
);

-- FTS5
CREATE VIRTUAL TABLE IF NOT EXISTS ktru_position_fts USING fts5(
    name,
    content='ktru_position',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_char_position  ON ktru_characteristic(position_code);
CREATE INDEX IF NOT EXISTS idx_char_name      ON ktru_characteristic(name);
CREATE INDEX IF NOT EXISTS idx_val_char       ON ktru_characteristic_value(characteristic_id);
CREATE INDEX IF NOT EXISTS idx_val_quality    ON ktru_characteristic_value(quality_description);
CREATE INDEX IF NOT EXISTS idx_prod_position  ON ktru_product(position_code);
CREATE INDEX IF NOT EXISTS idx_rub_position   ON ktru_rubricator(position_code);
