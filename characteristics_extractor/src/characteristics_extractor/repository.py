"""Read the supplied KTRU positions in one SQLite snapshot; never write data."""

from contextlib import closing
import os
from pathlib import Path
import sqlite3
from typing import Sequence

from pydantic import Field, ValidationError

from .schemas import ContractModel, NonEmpty, Number


class KtruValue(ContractModel):
    id: int
    characteristic_id: int
    value_code: str | None
    quality_description: str | None
    okei_code: str | None
    okei_name: str | None
    value_format: str | None
    min_value: Number | None
    max_value: Number | None
    min_notation: str | None
    max_notation: str | None
    concrete_value: Number | None


class KtruCharacteristic(ContractModel):
    id: int
    position_code: NonEmpty
    code: str | None
    name: NonEmpty
    type: int | None
    kind: int | None
    is_required: int
    choice_type: int | None
    values: list[KtruValue] = Field(default_factory=list)


class KtruPosition(ContractModel):
    code: NonEmpty
    name: NonEmpty
    okpd2_code: str | None
    characteristics: list[KtruCharacteristic] = Field(default_factory=list)


class LoadedCatalog(ContractModel):
    positions: list[KtruPosition]
    missing_codes: list[str]


class CatalogUnavailableError(RuntimeError):
    """Missing/unreadable database, incompatible schema or invalid typed data."""


class KtruRepository:
    # Three bounded queries per batch, not one query for every characteristic.
    BATCH_SIZE = 400

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser().resolve()

    @classmethod
    def from_env(cls) -> "KtruRepository":
        # The source-layout default works in this checkout regardless of cwd.
        # An installed package outside the checkout needs KTRU_DB_PATH explicitly.
        configured = os.environ.get("KTRU_DB_PATH")
        if configured:
            return cls(configured)
        for parent in Path(__file__).resolve().parents:
            if parent.name == "characteristics_extractor" and (parent / "pyproject.toml").is_file():
                return cls(parent.parent / "ktru.db")
        raise CatalogUnavailableError("Укажите KTRU_DB_PATH для установленного пакета")

    def load_positions(self, codes: Sequence[str]) -> LoadedCatalog:
        if isinstance(codes, (str, bytes)) or any(not isinstance(code, str) or not code.strip() for code in codes):
            raise ValueError("codes должен содержать непустые строки кодов КТРУ")
        ordered_codes = list(dict.fromkeys(codes))
        if not ordered_codes:
            return LoadedCatalog(positions=[], missing_codes=[])

        try:
            uri = self.db_path.as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA query_only = ON")
                connection.execute("BEGIN")
                positions: dict[str, KtruPosition] = {}
                for offset in range(0, len(ordered_codes), self.BATCH_SIZE):
                    batch = ordered_codes[offset:offset + self.BATCH_SIZE]
                    placeholders = ",".join("?" for _ in batch)
                    for row in connection.execute(
                        f"SELECT code, name, okpd2_code FROM ktru_position WHERE code IN ({placeholders})",
                        batch,
                    ):
                        position = KtruPosition.model_validate(dict(row))
                        positions[position.code] = position

                    characteristics: dict[int, KtruCharacteristic] = {}
                    for row in connection.execute(
                        f"""SELECT id, position_code, code, name, type, kind, is_required, choice_type
                            FROM ktru_characteristic WHERE position_code IN ({placeholders}) ORDER BY id""",
                        batch,
                    ):
                        characteristic = KtruCharacteristic.model_validate(dict(row))
                        if characteristic.position_code not in positions:
                            raise CatalogUnavailableError("Нарушена связь характеристики с позицией КТРУ")
                        positions[characteristic.position_code].characteristics.append(characteristic)
                        characteristics[characteristic.id] = characteristic

                    for row in connection.execute(
                        f"""SELECT v.id, v.characteristic_id, v.value_code, v.quality_description,
                                   v.okei_code, v.okei_name, v.value_format, v.min_value, v.max_value,
                                   v.min_notation, v.max_notation, v.concrete_value
                            FROM ktru_characteristic_value v
                            JOIN ktru_characteristic c ON c.id = v.characteristic_id
                            WHERE c.position_code IN ({placeholders}) ORDER BY v.id""",
                        batch,
                    ):
                        value = KtruValue.model_validate(dict(row))
                        characteristics[value.characteristic_id].values.append(value)
                return LoadedCatalog(
                    positions=[positions[code] for code in ordered_codes if code in positions],
                    missing_codes=[code for code in ordered_codes if code not in positions],
                )
        except (sqlite3.Error, ValidationError) as error:
            raise CatalogUnavailableError("Не удалось прочитать справочник КТРУ") from error
