"""Загрузка выгрузки КТРУ (nsiKTRUNew) из XML в SQLite.

Запуск:  python load.py <папка_или_файл_с_xml> [ktru.db]
Повторный запуск безопасен: позиция заменяется только более новой версией,
дочерние строки при замене удаляются и вставляются заново.
"""
import sqlite3
import sys
from pathlib import Path

from lxml import etree

SCHEMA = Path(__file__).with_name("schema.sql")


def text(el, path):
    """Текст вложенного элемента или None. Namespace игнорируем через {*}."""
    found = el.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip() or None


def to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def to_flag(v):
    return 1 if v is not None and v.lower() in ("true", "1") else 0


def to_float(v):
    try:
        return float(v.replace(",", "."))
    except (AttributeError, ValueError):
        return None


def parse_values(ch) -> list[dict]:
    """Значения одной характеристики. Диапазонов и конкретных значений может быть несколько."""
    out = []
    for val in ch.findall("{*}values/{*}value"):
        base = {
            "value_code": text(val, "{*}valueCode") or text(val, "{*}valueСode"),  # во 2-м — кириллическая «С»
            "okei_code": text(val, "{*}OKEI/{*}code"),
            "okei_name": text(val, "{*}OKEI/{*}name"),
        }
        q = text(val, "{*}qualityDescription")
        if q:
            out.append({**base, "quality_description": q})
        for vr in val.findall("{*}rangeSet/{*}valueRange"):
            out.append({**base,
                        "min_value": to_float(text(vr, "{*}min")),
                        "min_notation": text(vr, "{*}minMathNotation"),
                        "max_value": to_float(text(vr, "{*}max")),
                        "max_notation": text(vr, "{*}maxMathNotation")})
        for cv in val.findall("{*}valueSet/{*}concreteValue"):
            out.append({**base, "concrete_value": to_float(cv.text)})
    return out


def parse_position(pos) -> dict | None:
    """Чистый разбор XML -> dict, без обращений к БД."""
    data = pos.find("{*}data")
    if data is None:
        return None
    code = text(data, "{*}code")
    if not code:
        return None

    rubrics = [
        (text(r, "{*}code"), text(r, "{*}name"))
        for r in data.findall("{*}rubricators/{*}rubricatorInfo")
    ]
    # Только прямые потомки data: характеристики внутри products сюда не попадают.
    chars = [
        {"code": text(c, "{*}code"), "name": text(c, "{*}name"),
         "type": to_int(text(c, "{*}type")), "is_required": to_flag(text(c, "{*}isRequired")),
         "values": parse_values(c)}
        for c in data.findall("{*}characteristics/{*}characteristic")
    ]

    name = text(data, "{*}name")
    okpd2_name = text(data, "{*}OKPD2/{*}name")
    return {
        "code": code,
        "version": to_int(text(data, "{*}version")) or 0,
        "version_code": text(data, "{*}versionCode"),
        "name": name,
        "okpd2_code": text(data, "{*}OKPD2/{*}code"),
        "okpd2_name": okpd2_name,
        "status": text(data, "{*}status"),
        "is_template": to_flag(text(data, "{*}isTemplate")),
        "publish_date": text(data, "{*}publishDate"),
        "update_date": text(data, "{*}updateDate"),
        "date_start": text(data, "{*}applicationDateStart"),
        "date_end": text(data, "{*}applicationDateEnd"),
        "rubrics": rubrics,
        "chars": chars,
    }


def store(cur, p: dict) -> str:
    """Записать позицию. Возвращает 'new' | 'updated' | 'skipped'."""
    row = cur.execute("SELECT version FROM ktru_position WHERE code = ?", (p["code"],)).fetchone()
    if row is not None:
        if row[0] >= p["version"]:
            return "skipped"  # в базе уже эта версия или новее
        cur.execute("DELETE FROM ktru_position WHERE code = ?", (p["code"],))  # CASCADE уберёт детей
        result = "updated"
    else:
        result = "new"

    cur.execute(
        """INSERT INTO ktru_position
           (code, version, version_code, name, okpd2_code, okpd2_name, status, is_template,
            publish_date, update_date, date_start, date_end)
           VALUES (:code, :version, :version_code, :name, :okpd2_code, :okpd2_name, :status,
                   :is_template, :publish_date, :update_date, :date_start, :date_end)""",
        p,
    )
    cur.executemany(
        "INSERT INTO ktru_rubric (position_code, code, name) VALUES (?, ?, ?)",
        [(p["code"], c, n) for c, n in p["rubrics"]],
    )
    for c in p["chars"]:
        cur.execute(
            "INSERT INTO ktru_characteristic (position_code, code, name, type, is_required) "
            "VALUES (?, ?, ?, ?, ?)",
            (p["code"], c["code"], c["name"], c["type"], c["is_required"]),
        )
        char_id = cur.lastrowid
        cur.executemany(
            """INSERT INTO ktru_char_value
               (characteristic_id, value_code, quality_description, okei_code, okei_name,
                min_value, min_notation, max_value, max_notation, concrete_value)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(char_id, v.get("value_code"), v.get("quality_description"), v.get("okei_code"),
              v.get("okei_name"), v.get("min_value"), v.get("min_notation"),
              v.get("max_value"), v.get("max_notation"), v.get("concrete_value"))
             for v in c["values"]],
        )
    return result


def load_file(conn, xml_path: Path, stats: dict):
    cur = conn.cursor()
    # recover=True: усечённый/битый файл не роняет загрузку, берём всё, что успели прочитать.
    context = etree.iterparse(str(xml_path), events=("end",), tag="{*}position",
                              huge_tree=True, recover=True)
    for _, pos in context:
        try:
            p = parse_position(pos)
            if p is None:
                stats["bad"] += 1
            else:
                stats[store(cur, p)] += 1
        except Exception as e:  # одна плохая позиция не должна ронять файл
            stats["bad"] += 1
            print(f"  ! ошибка в позиции: {e}")
        # освобождаем память: очищаем элемент и уже обработанных соседей
        pos.clear()
        while pos.getprevious() is not None:
            del pos.getparent()[0]


def main(src: str, db_path: str = "ktru.db"):
    src_path = Path(src)
    files = [src_path] if src_path.is_file() else sorted(
        p for p in src_path.rglob("*.xml") if not p.name.startswith("."))
    if not files:
        sys.exit(f"XML-файлы не найдены: {src}")

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    stats = {"new": 0, "updated": 0, "skipped": 0, "bad": 0}

    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {f}")
        load_file(conn, f, stats)
        conn.commit()  # один коммит на файл
        print("  ", stats)

    conn.close()
    print("Готово:", stats)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python load.py <папка_или_файл> [ktru.db]")
    main(*sys.argv[1:3])
