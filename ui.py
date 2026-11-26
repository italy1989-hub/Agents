import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from langgraph.types import Command

from core import bitrix as bx
from core.links import card_url
from core.env import env_str

st.set_page_config(page_title="CRM-ассистент", layout="wide")


def _gate():
    pw = env_str("UI_PASSWORD")
    if pw and not st.session_state.get("ok"):
        if st.text_input("Пароль", type="password") == pw:
            st.session_state["ok"] = True
            st.rerun()
        st.stop()


@st.cache_resource
def _graph():
    from cards.graph import build_graph
    return build_graph()          # один граф на процесс, чтобы чекпоинты жили между кликами


def cards_tab():
    from cards import tools
    graph = _graph()
    st.subheader("Визитка в CRM")
    user_id = st.number_input("Ваш Bitrix ID (станет ответственным)", min_value=0, step=1, value=0)
    up = st.file_uploader("Фото визитки", type=["jpg", "jpeg", "png", "webp"])

    if up and st.button("Распознать"):
        tools.ALLOWED_DIR.mkdir(parents=True, exist_ok=True)
        path = tools.ALLOWED_DIR / f"{uuid.uuid4().hex}{Path(up.name).suffix.lower()}"
        path.write_bytes(up.getvalue())
        cfg = {"configurable": {"thread_id": uuid.uuid4().hex}}
        try:
            with st.spinner("Распознаю визитку и проверяю базу..."):
                out = graph.invoke({"image_path": str(path), "user_bitrix_id": int(user_id) or None}, cfg)
        finally:
            path.unlink(missing_ok=True)      # фото человека не храним
        st.session_state["cfg"], st.session_state["out"] = cfg, out

    out, cfg = st.session_state.get("out"), st.session_state.get("cfg")
    if not out:
        return
    card = graph.get_state(cfg).values.get("card")
    if card:
        st.caption("Распознано:")
        st.json(card, expanded=False)

    if out.get("__interrupt__"):
        st.warning(out["__interrupt__"][0].value["summary"])
        yes, no = st.columns(2)
        for col, label, answer in ((yes, "Подтвердить", True), (no, "Отклонить", False)):
            if col.button(label, key=label):
                with st.spinner("Выполняю..."):
                    st.session_state["out"] = graph.invoke(Command(resume=answer), cfg)
                st.rerun()
        return

    st.success(out["report"])
    created = out.get("created", {})
    for key, kind, label in (("company_id", "company", "Компания"),
                             ("contact_id", "contact", "Контакт"),
                             ("deal_id", "deal", "Сделка")):
        if created.get(key):
            st.markdown(f"[{label} #{created[key]}]({card_url(kind, created[key])})")
    for d in out.get("plan", {}).get("existing_deals", []):
        st.markdown(f"[Существующая сделка #{d['ID']}]({card_url('deal', d['ID'])})")


def audit_tab():
    from audit.config import AuditConfig
    from audit.db import connect
    from audit.report import build_rows, review_rows, summarize, to_csv_bytes
    st.subheader("Аудит закреплённых компаний (только отчёт, в CRM ничего не меняется)")
    db = connect()
    meta = db.execute("SELECT value FROM meta WHERE key = 'exported_at'").fetchone()
    if not meta:
        st.info("Данные ещё не выгружены: выполните `python app.py audit export`.")
        return
    st.caption(f"Снимок данных Bitrix от {meta['value'][:16]} UTC")

    cfg = AuditConfig()
    if st.toggle("Симуляция: отсчёт начался раньше (для показа)", value=True):
        days = st.slider("Сколько дней назад начался отсчёт", 1, 60, 25)
        cfg.simulate, cfg.launch_date = True, date.today() - timedelta(days=days)
        st.info(f"Условно считаем, что отсчёт стартовал {cfg.launch_date:%d.%m.%Y}. "
                "Реальный старт 01.12.2026, до него в список на проверку никто не попадёт.")

    rows = build_rows(db, cfg, date.today())
    st.dataframe(pd.DataFrame(summarize(rows)), hide_index=True, use_container_width=True)
    review = review_rows(rows)
    st.markdown(f"**Список на проверку: {len(review)}**")
    if review:
        st.dataframe(pd.DataFrame(review), hide_index=True, use_container_width=True,
                     column_config={"Карточка компании": st.column_config.LinkColumn("Карточка")})
        st.download_button("Скачать CSV", to_csv_bytes(review),
                           file_name=f"audit_{date.today():%Y%m%d}.csv", mime="text/csv")


_gate()
if bx.TEST_MODE:
    st.warning("ТЕСТОВЫЙ РЕЖИМ: записи помечаются маркером %s" % bx.TEST_MARKER)
else:
    st.error("БОЕВОЙ РЕЖИМ: записи создаются в рабочей CRM")

tab_cards, tab_audit = st.tabs(["Визитки", "Аудит компаний"])   # здесь же появится вкладка финансов
with tab_cards:
    cards_tab()
with tab_audit:
    audit_tab()
