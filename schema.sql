-- Схема для поиска позиции КТРУ по текстовому запросу.
-- Храним только то, что нужно для поиска и отдачи кода; остальное из XML сознательно пропущено.

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- Одна строка = одна позиция КТРУ (последняя из загруженных версий).
CREATE TABLE IF NOT EXISTS ktru_position (
    code           TEXT PRIMARY KEY,      -- 31.01.10.000-00000001  <- то, что отдаём пользователю
    version        INTEGER NOT NULL DEFAULT 0,
    version_code   TEXT,
    name           TEXT,                  -- в XML необязательное поле, поэтому без NOT NULL
    okpd2_code     TEXT,
    okpd2_name     TEXT,
    status         TEXT,                  -- ACTIVE / INACTIVE / TERMINATED
    is_template    INTEGER NOT NULL DEFAULT 0,
    publish_date   TEXT,
    update_date    TEXT,
    date_start     TEXT,                  -- applicationDateStart
    date_end       TEXT,                  -- applicationDateEnd
    -- Леммы для FTS (заполняет загрузчик): название отдельно, остальное отдельно,
    -- чтобы совпадение в названии весило больше.
    name_lemmas    TEXT NOT NULL DEFAULT '',
    extra_lemmas   TEXT NOT NULL DEFAULT '',
    values_lemmas  TEXT NOT NULL DEFAULT ''   -- леммы значений характеристик ("чугунный", "20", "сантиметр")
);

CREATE INDEX IF NOT EXISTS idx_position_status ON ktru_position(status);
CREATE INDEX IF NOT EXISTS idx_position_okpd2  ON ktru_position(okpd2_code);

-- Рубрики (например, «Мебель»): помогают найти позицию по общему слову.
CREATE TABLE IF NOT EXISTS ktru_rubric (
    position_code  TEXT NOT NULL REFERENCES ktru_position(code) ON DELETE CASCADE,
    code           TEXT,
    name           TEXT
);
CREATE INDEX IF NOT EXISTS idx_rubric_position ON ktru_rubric(position_code);

-- Характеристики позиции.
CREATE TABLE IF NOT EXISTS ktru_characteristic (
    id             INTEGER PRIMARY KEY,
    position_code  TEXT NOT NULL REFERENCES ktru_position(code) ON DELETE CASCADE,
    code           TEXT,
    name           TEXT,
    type           INTEGER,               -- 1 качественная, 2 количественная
    is_required    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_char_position ON ktru_characteristic(position_code);

-- Допустимые значения характеристик. Одна строка = одно значение:
--   текстовое (quality_description), диапазон (min/max + нотации) или конкретное число.
CREATE TABLE IF NOT EXISTS ktru_char_value (
    characteristic_id   INTEGER NOT NULL REFERENCES ktru_characteristic(id) ON DELETE CASCADE,
    value_code          TEXT,
    quality_description TEXT,
    okei_code           TEXT,
    okei_name           TEXT,
    min_value           REAL,
    min_notation        TEXT,   -- greater / greaterOrEqual
    max_value           REAL,
    max_notation        TEXT,   -- less / lessOrEqual
    concrete_value      REAL
);
CREATE INDEX IF NOT EXISTS idx_value_char ON ktru_char_value(characteristic_id);

-- Полнотекстовый индекс по леммам. Контент берётся из ktru_position (external content),
-- поэтому после загрузки нужен один 'rebuild' (делает load.py).
CREATE VIRTUAL TABLE IF NOT EXISTS ktru_fts USING fts5(
    name_lemmas,
    extra_lemmas,
    values_lemmas,
    content='ktru_position',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);
