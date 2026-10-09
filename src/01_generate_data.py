"""
Step 1 - generate the RAW data layer.

Creates data/raw/*.csv. The data is synthetic (see datagen.py) and deliberately messy
(duplicates, mixed date formats, impossible values...) so that step 2 (cleaning) has real work.

Run:  python src/01_generate_data.py
"""
import config as cfg
import datagen


def main():
    cfg.ensure_dirs()
    clean = datagen.generate_clean()
    raw = datagen.inject_raw_issues(clean)
    datagen.write_raw(raw)
    for name, df in raw.items():
        print(f"data/raw/{name}.csv  rows={len(df):>8,}  cols={df.shape[1]}")


if __name__ == "__main__":
    main()
