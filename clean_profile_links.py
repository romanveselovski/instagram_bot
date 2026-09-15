"""
Очищает instagram-ссылки в profile_links.csv:
- убирает query params (?...) и fragment (#...)
- сохраняет структуру файла (разделитель ;)

Запуск:
  python clean_profile_links.py
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pandas as pd


PROFILE_LINKS_CSV = Path(__file__).resolve().parent / "profile_links.csv"


def strip_query_and_fragment(url: str) -> str:
    s = (url or "").strip()
    if not s:
        return s
    parts = urlsplit(s)
    # scheme/netloc/path остаются, query/fragment выкидываем
    cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return cleaned


def main() -> None:
    if not PROFILE_LINKS_CSV.exists():
        raise SystemExit(f"Файл не найден: {PROFILE_LINKS_CSV}")

    df = pd.read_csv(PROFILE_LINKS_CSV, sep=";", dtype=str, keep_default_na=False)
    if "instagram" not in df.columns:
        raise SystemExit("В profile_links.csv нет колонки 'instagram'.")

    before = df["instagram"].astype(str)
    after = before.map(strip_query_and_fragment)
    changed = int((before != after).sum())

    df["instagram"] = after
    df.to_csv(PROFILE_LINKS_CSV, sep=";", index=False, encoding="utf-8")

    print(f"Готово. Обновлено ссылок: {changed}")


if __name__ == "__main__":
    main()

