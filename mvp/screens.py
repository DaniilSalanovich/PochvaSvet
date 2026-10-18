"""Экраны бота: текст (HTML для Telegram) + кнопки.

Модуль не зависит от aiogram: каждый экран — это Screen(text, buttons),
где buttons — строки кнопок вида (подпись, callback_data) или
(подпись, {"web_app": url}). bot.py превращает их в клавиатуры Telegram.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from engine import INDICATORS, LEVELS, RULES, Report, build_report, convert, level_light

LIGHT = RULES["lights"]
QUESTIONS = RULES["questions"]
Q_BY_ID = {q["id"]: q for q in QUESTIONS}
COMBOS = {c["id"]: c for c in RULES["combos"]}
MAX_MSG = 3800  # запас до лимита Telegram в 4096 символов

Button = tuple  # (text, callback_data | {"web_app": url})


@dataclass
class Screen:
    text: str
    buttons: list[list[Button]] = field(default_factory=list)


def e(s: str) -> str:
    return escape(s, quote=False)


def dot(light: str | None) -> str:
    return LIGHT[light]["emoji"] if light else "⚪"


BACK_MAIN = [("⬅️ В главное меню", "m")]


# ---------- главное меню ----------

def main_menu(webapp_url: str | None = None) -> Screen:
    rows: list[list[Button]] = [
        [("🧪 Разобрать мои результаты", "w:start")],
        [("📖 Брошюра: что значит каждый результат", "b")],
        [("🔗 Сочетания результатов (К1–К18)", "bc")],
        [("🧮 Пересчёт дозы в удобрение", "c:start")],
    ]
    if webapp_url:
        rows.append([("📱 Интерактивная брошюра", {"web_app": webapp_url})])
    text = (
        "<b>ПочваСвет — что делать по результатам тестов</b>\n\n"
        "🟢 в норме · 🟡 обрати внимание · 🔴 действуй сейчас\n\n"
        "• <b>Разобрать мои результаты</b> — отвечаете на вопросы по каждому тесту, "
        "бот выдаёт сигнал, дозы, сочетания и план по приоритетам.\n"
        "• <b>Брошюра</b> — все уровни каждого теста с объяснениями.\n"
        "• <b>Пересчёт дозы</b> — килограммы действующего вещества в мешки, граммы и ложки."
    )
    return Screen(text, rows)


# ---------- брошюра ----------

BROCHURE_ORDER = ["ph", "carb", "n", "p", "k", "org"]


def brochure_root() -> Screen:
    rows = []
    for ind_id in BROCHURE_ORDER:
        name = RULES["organics"]["name"] if ind_id == "org" else INDICATORS[ind_id]["name"]
        rows.append([(name, f"bi:{ind_id}")])
    rows += [
        [("🔗 Сочетания результатов", "bc")],
        [("💰 Если бюджет ограничен", "bx:budget"), ("📅 Календарь", "bx:calendar")],
        [("⚠️ Безопасность", "bx:safety")],
        BACK_MAIN,
    ]
    text = ("<b>Брошюра ПочваСвет</b>\n\nЧитайте результаты по порядку: сначала кислотность, "
            "потом фосфор и калий, затем азот и органика. Выберите тест:")
    return Screen(text, rows)


def brochure_indicator(ind_id: str) -> Screen:
    if ind_id == "org":
        org = RULES["organics"]
        lines = [f"<b>{e(org['name'])}</b>", "", e(org["rule"]), ""]
        for part in ("org_color", "org_foam", "org_worms"):
            ind = INDICATORS[part]
            lines.append(f"<b>{e(ind['name'])}</b>")
            for lvl in ind["levels"]:
                lines.append(f"{dot(lvl['light'])} {e(lvl['title'])}")
            lines.append("")
        rows = [[(f"{dot(l)} {org['levels'][l]['title']}", f"bo:{l}")] for l in ("red", "yellow", "green")]
        rows.append([("⬅️ К списку тестов", "b")])
        return Screen("\n".join(lines).strip(), rows)

    ind = INDICATORS[ind_id]
    text = f"<b>{e(ind['name'])}</b>\n\n{e(ind.get('intro', ''))}\n\nВыберите свой результат:"
    rows = [[(f"{dot(l['light'])} {l['button']}", f"bl:{l['id']}")] for l in ind["levels"]]
    rows.append([("⬅️ К списку тестов", "b")])
    return Screen(text, rows)


def _dose_table(lvl: dict) -> list[str]:
    out = []
    if "lime" in lvl:
        names = {"sand": "песок", "sandy_loam": "супесь", "loam": "суглинок"}
        parts = [f"{names[t]} {a}–{b} т/га" for t, (a, b) in lvl["lime"].items()]
        out.append("<b>Доломитовая мука:</b> " + "; ".join(parts))
    if "dose" in lvl:
        names = {"grain": "зерновые", "potato": "картофель", "veg": "овощи"}
        parts = []
        for c, (a, b) in lvl["dose"].items():
            parts.append(f"{names[c]} {'не вносить' if b == 0 else (f'{a}–{b}' if a != b else str(a))}")
        out.append("<b>Доза, кг д. в./га:</b> " + "; ".join(parts))
    return out


def brochure_level(level_id: str) -> Screen:
    ind_id, lvl = LEVELS[level_id]
    lines = [f"{dot(lvl['light'])} <b>{e(lvl['title'])}</b>", f"<i>{e(INDICATORS[ind_id]['name'])}</i>", ""]
    if lvl.get("light_rules"):
        lines.append("Сигнал может меняться в зависимости от почвы и культуры — мастер учтёт это сам.")
    lines += [e(lvl["meaning"]), ""]
    if lvl["actions"]:
        lines.append("<b>Что делать:</b>")
        lines += [f"• {e(a)}" for a in lvl["actions"]]
    lines += _dose_table(lvl)
    if ind_id == "n":
        lines.append("")
        lines.append("<b>Полная доза азота за сезон:</b>")
        names = {"grain": "Зерновые", "potato": "Картофель", "veg": "Овощи"}
        for crop, d in RULES["n_full"].items():
            lines.append(f"• {names[crop]}: {d['range'][0]}–{d['range'][1]} кг N/га. {e(d['note'])}")
    related = [c for c in RULES["combos"] if level_id in _levels_in(c["when"])]
    rows = []
    if related:
        lines += ["", "<b>Проверьте сочетания:</b> " + ", ".join(c["id"] for c in related)]
        rows.append([(f"{c['id']}", f"bk:{c['id']}") for c in related[:5]])
    rows.append([("⬅️ Назад", f"bi:{ind_id}"), ("🏠 Меню", "m")])
    return Screen("\n".join(lines), rows)


def brochure_organics(light: str) -> Screen:
    lv = RULES["organics"]["levels"][light]
    lines = [f"{dot(light)} <b>{e(lv['title'])}</b>", "", e(lv["meaning"]), "", "<b>Что делать:</b>"]
    lines += [f"• {e(a)}" for a in lv["actions"]]
    return Screen("\n".join(lines), [[("⬅️ Назад", "bi:org"), ("🏠 Меню", "m")]])


def _levels_in(when: dict) -> set[str]:
    out: set[str] = set()
    for key, val in when.items():
        if key == "any":
            for sub in val:
                out |= _levels_in(sub)
        elif isinstance(val, list):
            out |= {v for v in val if isinstance(v, str)}
    return out


def combos_list() -> Screen:
    lines = ["<b>Сочетания результатов</b>", "",
             "Если ваши результаты совпали с сочетанием, его рекомендация главнее отдельных советов."]
    rows, group = [], None
    for c in RULES["combos"]:
        if c["group"] != group:
            group = c["group"]
            lines.append(f"\n<b>{e(group)}</b>")
        lines.append(f"{dot(c['light'])} {c['id']}. {e(c['title'])}")
    ids = [c["id"] for c in RULES["combos"]]
    for i in range(0, len(ids), 6):
        rows.append([(cid, f"bk:{cid}") for cid in ids[i:i + 6]])
    rows.append(BACK_MAIN)
    return Screen("\n".join(lines), rows)


def describe_when(when: dict) -> str:
    names = {"texture": {"sand": "песок", "sandy_loam": "супесь", "loam": "суглинок"},
             "crop": {"grain": "зерновые", "potato": "картофель", "veg": "овощи"},
             "org": {"red": "органика 🔴", "yellow": "органика 🟡", "green": "органика 🟢"},
             "manure": {"yes": "недавно вносили навоз", "no": "без навоза"}}
    parts = []
    for key, val in when.items():
        if key == "any":
            parts.append("(" + " или ".join(describe_when(s) for s in val) + ")")
        elif key == "all_green":
            parts.append("все показатели зелёные")
        elif key == "month":
            parts.append("ранняя весна (март–апрель)")
        elif key in names:
            parts.append(" / ".join(names[key][v] for v in val))
        else:
            parts.append(" / ".join(LEVELS[v][1]["title"].split(" — ")[0].split(":")[0] for v in val))
    return " + ".join(parts)


def combo_card(cid: str, back: str = "bc") -> Screen:
    c = COMBOS[cid]
    lines = [f"{dot(c['light'])} <b>{c['id']}. {e(c['title'])}</b>", "",
             f"<b>Когда:</b> {e(describe_when(c['when']))}", "",
             f"<b>Почему:</b> {e(c['why'])}", "", "<b>Что делать:</b>"]
    lines += [f"• {e(a)}" for a in c["actions"]]
    return Screen("\n".join(lines), [[("⬅️ Назад", back), ("🏠 Меню", "m")]])


def extra(kind: str) -> Screen:
    if kind == "budget":
        lines = ["<b>💰 Если денег или удобрений не хватает</b>", "", "Тратьте в таком порядке:"]
        lines += [f"{i}. {e(s)}" for i, s in enumerate(RULES["budget"], 1)]
        lines += ["", "<b>Сразу вычеркните из закупки:</b> фосфор и калий на полях V–VI группы, "
                  "известь при pH выше 6,0 (на песке и супеси — выше 5,5) и при шипении с уксусом."]
    elif kind == "calendar":
        lines = ["<b>📅 Сезонный календарь</b>", ""]
        for row in RULES["calendar"]:
            lines += [f"<b>{e(row['period'])}</b>", f"Тесты: {e(row['tests'])}", f"Работы: {e(row['work'])}", ""]
    else:
        lines = ["<b>⚠️ Безопасность и когда звать агронома</b>", ""]
        lines += [f"• {e(s)}" for s in RULES["safety"]]
    return Screen("\n".join(lines).strip(), [[("⬅️ Назад", "b"), ("🏠 Меню", "m")]])


# ---------- мастер «мои результаты» ----------

def question_screen(index: int, answers: dict) -> Screen:
    q = QUESTIONS[index]
    total = len(QUESTIONS)
    header = f"<b>Шаг {index + 1} из {total}</b>\n{e(q['text'])}"
    rows: list[list[Button]] = []
    if q.get("indicator"):
        ind = INDICATORS[q["indicator"]]
        for lvl in ind["levels"]:
            light = level_light(lvl["id"], answers)
            rows.append([(f"{dot(light)} {lvl['button']}", f"w:{q['id']}:{lvl['id']}")])
        rows.append([("⏭ Не делал(а) этот тест", f"w:{q['id']}:-")])
    else:
        opts = q["options"]
        per_row = 2 if q["id"] == "area" else 1
        for i in range(0, len(opts), per_row):
            rows.append([(o["label"], f"w:{q['id']}:{o['id']}") for o in opts[i:i + per_row]])
    nav = [("✖️ Отмена", "m")]
    if index > 0:
        nav.insert(0, ("⬅️ Назад", "w:back"))
    rows.append(nav)
    return Screen(header, rows)


def report_messages(report: Report) -> list[str]:
    """Отчёт, разбитый на сообщения не длиннее лимита Telegram."""
    blocks: list[str] = []
    head = [f"{dot(report.overall)} <b>Итог по полю: {LIGHT[report.overall]['name'].lower() if report.overall else 'нет данных'}</b>"]
    for w in report.warnings:
        head.append(f"⚠️ {e(w)}")
    blocks.append("\n".join(head))

    if report.plan:
        blocks.append("<b>План по приоритетам</b>\n" + "\n".join(f"{i}. {e(s)}" for i, s in enumerate(report.plan, 1)))
    if report.skip_buy:
        blocks.append("<b>💰 Не покупать в этом сезоне:</b> " + e(", ".join(report.skip_buy)))

    for card in report.cards:
        lines = [f"{dot(card.light)} <b>{e(card.name)}</b>", e(card.level_title), f"<i>{e(card.meaning)}</i>"]
        lines += [f"• {e(a)}" for a in card.actions]
        lines += [f"   ▸ {e(d)}" for d in card.dose_lines]
        blocks.append("\n".join(lines))

    if report.combos:
        cb = ["<b>🔗 Сочетания, которые совпали с вашими результатами</b>",
              "Их рекомендации главнее советов по отдельным тестам."]
        for c in report.combos:
            cb.append(f"\n{dot(c['light'])} <b>{c['id']}. {e(c['title'])}</b>\n<i>{e(c['why'])}</i>")
            cb += [f"• {e(a)}" for a in c["actions"]]
        blocks.append("\n".join(cb))

    blocks.append(f"<i>{e(RULES['meta']['disclaimer'])}</i>")

    messages, cur = [], ""
    for b in blocks:
        if cur and len(cur) + len(b) + 2 > MAX_MSG:
            messages.append(cur)
            cur = b
        else:
            cur = f"{cur}\n\n{b}" if cur else b
    if cur:
        messages.append(cur)
    return messages


def report_buttons(report: Report) -> list[list[Button]]:
    rows = []
    ids = [c["id"] for c in report.combos]
    for i in range(0, len(ids), 3):
        rows.append([(f"Подробнее {cid}", f"wk:{cid}") for cid in ids[i:i + 3]])
    rows += [[("🔁 Новый разбор", "w:start"), ("🏠 Меню", "m")]]
    return rows


def run_report(answers: dict, month: int) -> tuple[list[str], list[list[Button]]]:
    rep = build_report(answers, month)
    return report_messages(rep), report_buttons(rep)


# ---------- калькулятор ----------

def calc_ferts() -> Screen:
    rows = [[(f"{f['name']} ({f['pct']}%)", f"cf:{f['id']}")] for f in RULES["fertilizers"]]
    rows.append(BACK_MAIN)
    return Screen("<b>🧮 Пересчёт дозы</b>\n\nВыберите удобрение:", rows)


def calc_ask_dose(fert_id: str) -> Screen:
    f = next(x for x in RULES["fertilizers"] if x["id"] == fert_id)
    text = (f"<b>{e(f['name'])}</b>, {f['pct']}% д. в.\n\n"
            "Напишите дозу в <b>кг действующего вещества на гектар</b> числом (например, 60) "
            "или выберите:")
    rows = [[(str(v), f"cd:{fert_id}:{v}") for v in (30, 45, 60)],
            [(str(v), f"cd:{fert_id}:{v}") for v in (90, 120, 150)],
            [("⬅️ Назад", "c:start")]]
    return Screen(text, rows)


def calc_ask_area(fert_id: str, dose: float) -> Screen:
    area_q = Q_BY_ID["area"]
    rows = []
    opts = area_q["options"]
    for i in range(0, len(opts), 2):
        rows.append([(o["label"], f"ca:{fert_id}:{dose:g}:{o['id']}") for o in opts[i:i + 2]])
    return Screen(f"Доза {dose:g} кг д. в./га. Для какой площади посчитать?", rows)


def calc_result(fert_id: str, dose: float, area_m2: float) -> Screen:
    r = convert(dose, fert_id, area_m2)
    fmt = lambda x: f"{x:g}".replace(".", ",")  # noqa: E731
    lines = [f"<b>{e(r['fertilizer'])}</b> при дозе {fmt(dose)} кг д. в./га:", "",
             f"• {fmt(r['kg_per_ha'])} кг/га",
             f"• {fmt(r['g_per_m2'])} г/м² (≈ {fmt(r['tablespoons_per_m2'])} ст. ложки на м²)"]
    if r["kg_for_area"]:
        lines.append(f"• на {fmt(area_m2)} м²: {fmt(r['kg_for_area'])} кг")
    lines += ["", "<i>Столовая ложка гранул ≈ 15–20 г; взвесьте свою ложку один раз для точности.</i>"]
    return Screen("\n".join(lines), [[("🧮 Ещё расчёт", "c:start"), ("🏠 Меню", "m")]])
