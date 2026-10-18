"""Обход всех экранов бота без Telegram: python test_screens.py

Проверяет, что каждая кнопка ведёт на существующий экран, callback_data не длиннее
64 байт (лимит Telegram), а тексты не превышают 4096 символов и проходят как HTML.
"""
import itertools
import random
from html.parser import HTMLParser

import screens as S

ALLOWED_TAGS = {"b", "i"}


class TagCheck(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []

    def handle_starttag(self, tag, attrs):
        assert tag in ALLOWED_TAGS, tag
        self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack.pop() == tag, tag


def check_text(text):
    assert len(text) <= 4096, len(text)
    p = TagCheck()
    p.feed(text)
    assert not p.stack, p.stack


def route(data):
    """Повторяет маршрутизацию bot.py для экранов без состояния."""
    if data == "m":
        return S.main_menu("https://example.org/app")
    if data == "b":
        return S.brochure_root()
    if data == "bc":
        return S.combos_list()
    for prefix, fn in (("bi:", S.brochure_indicator), ("bl:", S.brochure_level), ("bo:", S.brochure_organics),
                       ("bk:", S.combo_card), ("bx:", S.extra), ("cf:", S.calc_ask_dose)):
        if data.startswith(prefix):
            return fn(data[len(prefix):])
    if data == "c:start":
        return S.calc_ferts()
    if data.startswith("cd:"):
        _, f, d = data.split(":")
        return S.calc_ask_area(f, float(d))
    if data.startswith("ca:"):
        _, f, d, a = data.split(":")
        return S.calc_result(f, float(d), float(a))
    return None  # мастер и прочее — проверяются отдельно


def test_all_static_screens():
    seen, queue = set(), ["m"]
    while queue:
        data = queue.pop()
        if data in seen:
            continue
        seen.add(data)
        scr = route(data)
        if scr is None:
            assert data.startswith(("w:", "wk:")), data
            continue
        check_text(scr.text)
        for row in scr.buttons:
            assert len(row) <= 8
            for text, action in row:
                if isinstance(action, dict):
                    continue
                assert len(action.encode()) <= 64, action
                queue.append(action)
    print(f"ok  обойдено экранов: {len(seen)}")


def test_wizard_screens_and_random_reports():
    for i in range(len(S.QUESTIONS)):
        scr = S.question_screen(i, {"texture": "loam", "crop": "potato"})
        check_text(scr.text)
        for row in scr.buttons:
            for _, action in row:
                assert len(action.encode()) <= 64
    rnd = random.Random(1)
    choices = {}
    for q in S.QUESTIONS:
        if q.get("indicator"):
            choices[q["id"]] = [l["id"] for l in S.INDICATORS[q["indicator"]]["levels"]] + [None]
        else:
            choices[q["id"]] = [o["id"] for o in q["options"]]
    hit = set()
    for _ in range(3000):
        ans = {k: rnd.choice(v) for k, v in choices.items()}
        ans = {k: v for k, v in ans.items() if v is not None}
        msgs, buttons = S.run_report(ans, rnd.randint(1, 12))
        for m in msgs:
            check_text(m)
        for row in buttons:
            for _, action in row:
                assert len(action.encode()) <= 64
        hit |= {a[len("wk:"):] for row in buttons for _, a in row if a.startswith("wk:")}
    missing = set(S.COMBOS) - hit
    print(f"ok  3000 случайных отчётов; сработали сочетания: {len(hit)} из {len(S.COMBOS)}"
          + (f", не встретились: {sorted(missing)}" if missing else ""))


if __name__ == "__main__":
    test_all_static_screens()
    test_wizard_screens_and_random_reports()
    msgs, _ = S.run_report({"texture": "sand", "crop": "potato", "ph": "ph2", "carb": "carb0", "n": "n2",
                            "p": "p2", "k": "k2", "org_color": "c1", "org_foam": "f2", "org_worms": "w1",
                            "manure": "no", "area": "600"}, 4)
    print("\n--- пример отчёта (%d сообщ.) ---" % len(msgs))
    print(msgs[0][:1800])
