"""
Собирает profile_links.csv из horeca_italy_social.csv:
колонки name;city;address;website;instagram (разделитель ;)
Только строки, где заполнена ссылка Instagram.
"""
import csv
from pathlib import Path

import pandas as pd


def main() -> None:
    root = Path(__file__).resolve().parent
    src = root / "horeca_italy_social.csv"
    dst = root / "profile_links.csv"

    df = pd.read_csv(src, dtype=str, keep_default_na=False)
    ig = df.get("instagram", pd.Series([""] * len(df))).astype(str).str.strip()
    mask = ig.ne("") & ig.str.lower().ne("nan")
    out = df.loc[mask, ["name", "city", "address", "website", "instagram"]].copy()

    for col in ("name", "city", "address", "website", "instagram"):
        out[col] = out[col].fillna("").astype(str)

    with dst.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow(["name", "city", "address", "website", "instagram"])
        for _, row in out.iterrows():
            w.writerow(
                [
                    row["name"],
                    row["city"],
                    row["address"],
                    row["website"],
                    row["instagram"],
                ]
            )

    print(f"Записано строк: {len(out)} -> {dst}")


if __name__ == "__main__":
    main()
