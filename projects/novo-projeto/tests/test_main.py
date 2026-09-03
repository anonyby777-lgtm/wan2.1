import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.main import saudacao


def test_saudacao():
    assert saudacao("Arena") == "Olá, Arena!"
