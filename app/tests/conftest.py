from pathlib import Path
import os
import tempfile
import pytest

# AppTest tworzy własny katalog tymczasowy przy imporcie. Także on należy do app/.
RUNTIME = Path(__file__).resolve().parent.parent / '.test_runtime'
RUNTIME.mkdir(exist_ok=True)
os.environ['TMPDIR'] = str(RUNTIME)
tempfile.tempdir = str(RUNTIME)

from lab.data import read_table, dictionary

FIXTURE = Path(__file__).resolve().parent / 'fixtures'

@pytest.fixture
def fixture_dir():
    return FIXTURE

@pytest.fixture
def definitions(fixture_dir):
    return dictionary(fixture_dir)

@pytest.fixture
def dirty(fixture_dir):
    return read_table(fixture_dir / 'rejestr_brudny.xlsx')

@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(FIXTURE))
    monkeypatch.setenv('LOG_DIR', str(tmp_path / 'logs'))
    monkeypatch.setenv('CACHE_DIR', str(tmp_path / 'cache'))
    for variable in ('ORNITH_API_KEY', 'ORNITH_API_KEY_FILE', 'QWEN_API_KEY', 'QWEN_API_KEY_FILE', 'ORNITH_BASE_URLS', 'ORNITH_MAX_CONCURRENCY_PER_SERVER'):
        monkeypatch.delenv(variable, raising=False)
