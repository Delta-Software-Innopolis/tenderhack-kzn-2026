import sqlite3
from pathlib import Path
import sys
from lxml import etree
from search import ensure_search_schema, rebuild_search_documents

DB_PATH = Path("ktru.db")
SCHEMA_PATH = Path("schema.sql")


def connect(db_path: Path | str = DB_PATH, init: bool = False) -> sqlite3.Connection:
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if init:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema)
        conn.commit()

    return conn


def rebuild_fts(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        INSERT INTO ktru_position_fts(ktru_position_fts) VALUES('rebuild');
    """)
    conn.commit()


def text(elem, path, default=None):
    if elem is None:
        return default
    found = elem.find(path)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def to_bool(v):
    return 1 if v == "true" else 0


def find_xml_files(root: Path) -> list[Path]:
    files = []
    for p in root.rglob("*.xml"):
        if p.name.startswith("._") or p.name.startswith("."):
            continue
        files.append(p)
    return sorted(files)


def parse_one_file(xml_path: Path, conn, counters: dict):
    cur = conn.cursor()

    context = etree.iterparse(
        str(xml_path), events=("end",),
        tag="{*}position",
        huge_tree=True,
    )

    for _, pos in context:
        data = pos.find("{*}data")
        if data is None:
            pos.clear()
            continue

        code = text(data, "{*}code")
        if not code:
            pos.clear()
            continue

        cur.execute("""
            INSERT OR REPLACE INTO ktru_position
            (code, name, okpd2_code, okpd2_name, status, actual, is_template,
             application_date_start, application_date_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            code,
            text(data, "{*}name"),
            text(data, "{*}OKPD2/{*}code"),
            text(data, "{*}OKPD2/{*}name"),
            text(data, "{*}status"),
            1,
            to_bool(text(data, "{*}isTemplate")),
            text(data, "{*}applicationDateStart"),
            text(data, "{*}applicationDateEnd"),
        ))

        for ch in data.findall("{*}characteristics/{*}characteristic"):
            cur.execute("""
                INSERT INTO ktru_characteristic
                (position_code, code, name, type, kind, is_required, choice_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                code,
                text(ch, "{*}code"),
                text(ch, "{*}name"),
                to_int(text(ch, "{*}type")),
                to_int(text(ch, "{*}kind")),
                to_bool(text(ch, "{*}isRequired")),
                to_int(text(ch, "{*}choiceType")),
            ))
            char_id = cur.lastrowid

            for val in ch.findall("{*}values/{*}value"):
                min_v = max_v = None
                min_n = max_n = None
                range_set = val.find("{*}rangeSet")
                if range_set is not None:
                    vr = range_set.find("{*}valueRange")
                    if vr is not None:
                        min_v = to_float(text(vr, "{*}min"))
                        max_v = to_float(text(vr, "{*}max"))
                        min_n = text(vr, "{*}minMathNotation")
                        max_n = text(vr, "{*}maxMathNotation")

                concrete = None
                value_set = val.find("{*}valueSet")
                if value_set is not None:
                    concrete = to_float(text(value_set, "{*}concreteValue"))

                cur.execute("""
                    INSERT INTO ktru_characteristic_value
                    (characteristic_id, value_code, quality_description,
                     okei_code, okei_name, value_format,
                     min_value, max_value, min_notation, max_notation,
                     concrete_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    char_id,
                    text(val, "{*}valueCode"),
                    text(val, "{*}qualityDescription"),
                    text(val, "{*}OKEI/{*}code"),
                    text(val, "{*}OKEI/{*}name"),
                    text(val, "{*}valueFormat"),
                    min_v, max_v, min_n, max_n, concrete,
                ))

        for prod in data.findall("{*}products/{*}product"):
            cur.execute("""
                INSERT INTO ktru_product
                (position_code, trade_name, manufacturer,
                 country_code, country_name, price)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                code,
                text(prod, "{*}tradeName"),
                text(prod, "{*}manufacturer"),
                text(prod, "{*}placeOfOrigin/{*}countryCode"),
                text(prod, "{*}placeOfOrigin/{*}countryFullName"),
                to_float(text(prod, "{*}price")),
            ))

        for rub in data.findall("{*}rubricators/{*}rubricatorInfo"):
            cur.execute("""
                INSERT INTO ktru_rubricator (position_code, code, name)
                VALUES (?, ?, ?)
            """, (code, text(rub, "{*}code"), text(rub, "{*}name")))

        counters["positions"] += 1

        pos.clear()
        while pos.getprevious() is not None:
            del pos.getparent()[0]


def main(root_dir: str, db_path: str = "ktru.db"):
    root = Path(root_dir)
    if not root.exists():
        print(f"Папка не найдена: {root}")
        sys.exit(1)

    xml_files = find_xml_files(root)
    print(f"Найдено XML-файлов: {len(xml_files)}")

    conn = connect(db_path, init=True)
    ensure_search_schema(conn)
    counters = {"positions": 0}

    for i, xml_path in enumerate(xml_files, 1):
        rel = xml_path.relative_to(root)
        print(f"[{i}/{len(xml_files)}] {rel}")

        try:
            parse_one_file(xml_path, conn, counters)
            conn.commit()
        except Exception as e:
            print(f"  ⚠️  Ошибка: {e}")
            conn.rollback()
            continue

        print(f"  позиций={counters['positions']}")

    print("Строим FTS-индексы...")
    rebuild_fts(conn)
    print("Строим гибридный поисковый индекс...")
    indexed = rebuild_search_documents(conn)

    print(f"Итого позиций: {counters['positions']}; в поисковом индексе: {indexed}")
    conn.close()
    print("Готово.")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "raw_data"
    main(root)
