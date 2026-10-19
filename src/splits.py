"""
splits.py - TIME-BASED train / dev / test split.

Rules (from "Structuring Machine Learning Projects"):
  * split by TIME, never randomly - a random split would let the model peek at the future
  * dev and test are the two most recent blocks, so they come from the same distribution
  * the test set is touched ONCE, at the very end
"""
import pandas as pd

import config as cfg


def assign_split(week_idx, train_weeks=cfg.TRAIN_WEEKS, dev_weeks=cfg.DEV_WEEKS, test_weeks=cfg.TEST_WEEKS):
    """Map week numbers (0-based) to 'train' / 'dev' / 'test'. Weeks beyond the 3 blocks get 'unused'."""
    w = pd.Series(week_idx)
    out = pd.Series("unused", index=w.index, dtype=object)
    out[w < train_weeks] = "train"
    out[(w >= train_weeks) & (w < train_weeks + dev_weeks)] = "dev"
    out[(w >= train_weeks + dev_weeks) & (w < train_weeks + dev_weeks + test_weeks)] = "test"
    return out.to_numpy()


def validate_split(df, split_col="split", week_col="week_idx"):
    """Raise AssertionError if the split is not strictly chronological (train < dev < test)."""
    rng = df.groupby(split_col)[week_col].agg(["min", "max"])
    assert rng.loc["train", "max"] < rng.loc["dev", "min"], "train overlaps dev"
    assert rng.loc["dev", "max"] < rng.loc["test", "min"], "dev overlaps test"
    return rng
