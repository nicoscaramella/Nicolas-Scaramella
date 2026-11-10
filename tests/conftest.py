from pathlib import Path

import pytest
import yaml

from sistema.parser import Parser

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def planta_def() -> dict:
    return yaml.safe_load((RAIZ / "datos" / "planta.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def parser(planta_def) -> Parser:
    return Parser(planta_def)
