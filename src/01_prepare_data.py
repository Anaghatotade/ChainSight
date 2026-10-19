"""
Step 1 - check the RAW data layer (the three Kaggle M5 files in data/raw/).

This project uses REAL data: Kaggle "M5 Forecasting - Accuracy" (Walmart). We cannot download it for you (Kaggle needs
your login and you must accept the competition rules), so this step only checks that the files are there, readable and
prints their size + checksum so you can document exactly which files produced your results.

Run:  python src/01_prepare_data.py
"""
import hashlib

import pandas as pd

import config as cfg
import keynums
import panel as pn


def md5(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def main():
    cfg.ensure_dirs()
    keynums.reset()                               # a new run starts with an empty number store
    print("Raw files in data/raw/:")
    rows = []
    for key in cfg.RAW_FILES:
        p = pn.find_raw(key)                      # raises a clear error if a file is missing
        digest = md5(p)
        print(f"  {p.name:<32} {p.stat().st_size / 1e6:>8.1f} MB   md5 {digest}")
        rows.append(dict(file=p.name, size_mb=round(p.stat().st_size / 1e6, 1), md5=digest))
    pd.DataFrame(rows).to_csv(cfg.TABLES / "raw_files.csv", index=False)      # quoted in the README: exactly which files were used
    print("OK - all three raw files found. Next: python src/02_clean_data.py")


if __name__ == "__main__":
    main()
