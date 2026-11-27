import os
import sys
from pathlib import Path

from core import bitrix as bx
from core.env import env_int, env_str
from dotenv import dotenv_values

_shadowed = [k for k, v in dotenv_values(".env").items()
             if v is not None and k in os.environ and os.environ[k] != v]
for k in _shadowed:
    print(f"ВНИМАНИЕ  {k}: значение в терминале отличается от .env и перекрывает его (unset {k})")

CHECKS = [("BITRIX_WEBHOOK", env_str), ("BITRIX_WEBHOOK_READ", env_str),
          ("AUDIT_POOL_USER_ID", env_int), ("BITRIX_DEAL_CATEGORY_ID", env_int),
          ("BITRIX_DEAL_STAGE_ID", env_str), ("BITRIX_SOURCE_ID", env_str),
          ("BITRIX_RETURN_DATE_FIELD", env_str), ("UI_PASSWORD", env_str),
          ("GIGACHAT_CREDENTIALS", env_str), ("LLM_PROVIDER", env_str)]

bad = False
for name, fn in CHECKS:
    try:
        print(("задано   " if fn(name) is not None else "пусто    ") + name)
    except ValueError as e:
        bad = True
        print(f"ОШИБКА   {e}")

print(f"\nTEST_MODE={bx.TEST_MODE}  TEST_MARKER={bx.TEST_MARKER!r}")
cards = Path(os.getenv("CARDS_DIR", "./tests/cards"))
print(f"CARDS_DIR={cards}  {'существует' if cards.is_dir() else 'ПАПКИ НЕТ'}")

hook = os.getenv("BITRIX_WEBHOOK") or ""
if not hook.startswith("https://"):
    bad = True
    print("ОШИБКА   BITRIX_WEBHOOK должен начинаться с https://")
else:
    try:
        me = bx._call_bitrix("profile", {}).get("result", {})
        print(f'Вебхук работает от имени: {me.get("NAME", "")} {me.get("LAST_NAME", "")} (ID {me.get("ID")})')
    except bx.BitrixError as e:
        bad = True
        print(f"ОШИБКА   вебхук не отвечает: {e}")

sys.exit(1 if bad else 0)
