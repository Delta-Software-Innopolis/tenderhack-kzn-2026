-- Основная схема БД КТРУ.
-- Поисковые производные таблицы создаются здесь, а их содержимое
-- заполняется main.py и search.py после загрузки XML.

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- Одна строка = одна позиция КТРУ.
CREATE TABLE IF NOT EXISTS ktru_position (
    code                   TEXT PRIMARY KEY,
    name                   TEXT NOT NULL,
    okpd2_code             TEXT,
    okpd2_name             TEXT,
    status                 TEXT,
    actual                 INTEGER NOT NULL DEFAULT 1,
    is_template            INTEGER NOT NULL DEFAULT 0,
    application_date_start TEXT,
    application_date_end   TEXT
);

CREATE INDEX IF NOT EXISTS idx_position_status
    ON ktru_position(status);
CREATE INDEX IF NOT EXISTS idx_position_okpd2
    ON ktru_position(okpd2_code);

-- Характеристики позиции.
CREATE TABLE IF NOT EXISTS ktru_characteristic (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    position_code TEXT NOT NULL,
    code         TEXT,
    name         TEXT NOT NULL,
    type         INTEGER,
    kind         INTEGER,
    is_required  INTEGER NOT NULL DEFAULT 0,
    choice_type  INTEGER,
    FOREIGN KEY (position_code) REFERENCES ktru_position(code) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_char_position
    ON ktru_characteristic(position_code);
CREATE INDEX IF NOT EXISTS idx_char_name
    ON ktru_characteristic(name);

-- Допустимые значения характеристик.
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
    FOREIGN KEY (characteristic_id)
        REFERENCES ktru_characteristic(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_val_char
    ON ktru_characteristic_value(characteristic_id);
CREATE INDEX IF NOT EXISTS idx_val_quality
    ON ktru_characteristic_value(quality_description);

-- Товары, связанные с позицией КТРУ.
CREATE TABLE IF NOT EXISTS ktru_product (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    position_code  TEXT NOT NULL,
    trade_name     TEXT,
    manufacturer   TEXT,
    country_code   TEXT,
    country_name   TEXT,
    price          REAL,
    FOREIGN KEY (position_code) REFERENCES ktru_position(code) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_prod_position
    ON ktru_product(position_code);

-- Рубрикаторы позиции.
CREATE TABLE IF NOT EXISTS ktru_rubricator (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    position_code  TEXT NOT NULL,
    code           TEXT,
    name           TEXT,
    FOREIGN KEY (position_code) REFERENCES ktru_position(code) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rub_position
    ON ktru_rubricator(position_code);

-- Подготовленный поисковый текст позиции.
CREATE TABLE IF NOT EXISTS ktru_position_search (
    position_code    TEXT PRIMARY KEY,
    raw_text         TEXT NOT NULL,
    normalized_text  TEXT NOT NULL,
    lemmatized_text  TEXT NOT NULL,
    tokens_json      TEXT NOT NULL,
    FOREIGN KEY (position_code) REFERENCES ktru_position(code) ON DELETE CASCADE
);

-- Эмбеддинги с версией модели.
CREATE TABLE IF NOT EXISTS ktru_position_embedding (
    position_code  TEXT PRIMARY KEY,
    model_name     TEXT NOT NULL,
    model_version  TEXT NOT NULL,
    embedding      BLOB NOT NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (position_code) REFERENCES ktru_position(code) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_emb_model
    ON ktru_position_embedding(model_name, model_version);

-- FTS5-индекс является производным от ktru_position_search.
CREATE VIRTUAL TABLE IF NOT EXISTS ktru_position_fts USING fts5(
    lemmatized_text,
    content='ktru_position_search',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);
