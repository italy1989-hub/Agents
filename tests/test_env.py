import pytest
from core.env import env_int, env_str


def test_env_int(monkeypatch):
    monkeypatch.setenv("X", " 42 ")
    assert env_int("X") == 42
    monkeypatch.setenv("X", "")
    assert env_int("X") is None
    monkeypatch.delenv("X")
    assert env_int("X") is None


def test_env_int_garbage_names_the_variable(monkeypatch):
    monkeypatch.setenv("X", "<ID воронки>")
    with pytest.raises(ValueError, match="X"):
        env_int("X")


def test_env_str_rejects_placeholder(monkeypatch):
    monkeypatch.setenv("X", "<пароль>")
    with pytest.raises(ValueError):
        env_str("X")
