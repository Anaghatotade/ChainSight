"""Shared fixtures: a SMALL synthetic dataset (6 SKUs, 30 weeks) so tests run in seconds."""
import pytest

import cleaning
import datagen


@pytest.fixture(scope="session")
def small_clean():
    return datagen.generate_clean(seed=7, n_skus=6, n_suppliers=6, n_days=210)


@pytest.fixture(scope="session")
def small_raw(small_clean):
    return datagen.inject_raw_issues(small_clean, seed=8)


@pytest.fixture(scope="session")
def small_cleaned(small_raw):
    tables, log = cleaning.clean_all(small_raw)
    return tables, log
