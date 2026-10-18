"""Движок рекомендаций «ПочваСвет».

Читает rules.json (единый источник для бота и мини-приложения) и по ответам
фермера строит отчёт: сигнал по каждому тесту, дозы, сработавшие сочетания
(К1–К18), план по приоритетам и список того, что не нужно покупать.

Модуль не зависит от Telegram и тестируется отдельно (см. test_engine.py).
"""
from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).with_name("rules.json")
RANK = {"green": 0, "yellow": 1, "red": 2}
MAIN_INDICATORS = ("ph", "carb", "n", "p", "k")
ORG_PARTS = ("org_color", "org_foam", "org_worms")


def load_rules(path: Path = RULES_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


RULES = load_rules()
INDICATORS = {ind["id"]: ind for ind in RULES["indicators"]}
LEVELS = {lvl["id"]: (ind["id"], lvl) for ind in RULES["indicators"] for lvl in ind["levels"]}
FERTS = {f["id"]: f for f in RULES["fertilizers"]}


# ---------- форматирование чисел ----------

def rnd(x: float, nd: int = 0) -> float:
    """Округление «половина вверх» (как Math.round в мини-приложении)."""
    return float(Decimal(repr(x)).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP))


def num(x: float) -> str:
    """Число по-русски: без лишних нулей, запятая как разделитель."""
    if abs(x - rnd(x)) < 1e-9:
        return str(int(rnd(x)))
    return f"{x:.1f}".replace(".", ",")


def rng(a: float, b: float) -> str:
    return num(a) if abs(a - b) < 1e-9 else f"{num(a)}–{num(b)}"


def worst(*lights: str | None) -> str | None:
    present = [l for l in lights if l]
    return max(present, key=lambda l: RANK[l]) if present else None


# ---------- условия ----------

def match_when(when: dict, ctx: dict) -> bool:
    for key, allowed in when.items():
        if key == "any":
            if not any(match_when(sub, ctx) for sub in allowed):
                return False
        elif key == "all_green":
            if bool(ctx.get("_all_green")) != bool(allowed):
                return False
        else:
            if ctx.get(key) not in allowed:
                return False
    return True


def apply_light_rules(base: str, rules: list | None, ctx: dict) -> str:
    for rule in rules or []:
        if match_when(rule["when"], ctx):
            return rule["light"]
    return base


def level_light(level_id: str, ctx: dict) -> str:
    _, lvl = LEVELS[level_id]
    return apply_light_rules(lvl["light"], lvl.get("light_rules"), ctx)


def organics_light(answers: dict) -> str | None:
    lights = [level_light(answers[p], answers) for p in ORG_PARTS if answers.get(p)]
    if not lights:
        return None
    if len(lights) == 1:
        return lights[0]
    reds, greens = lights.count("red"), lights.count("green")
    if reds >= 2:
        return "red"
    if greens >= 2 and reds == 0:
        return "green"
    return "yellow"


# ---------- дозы ----------

@dataclass
class Dose:
    nutrient: str                  # "N", "P", "K", "lime"
    low: float                     # кг д. в./га (для извести — т/га)
    high: float
    fertilizer: dict | None = None
    note: str = ""

    def lines(self, area_m2: float) -> list[str]:
        if self.nutrient == "lime":
            out = [f"Доломитовая мука: {rng(self.low, self.high)} т/га "
                   f"({rng(self.low * 100, self.high * 100)} г/м²)"]
            if area_m2:
                mid = (self.low + self.high) / 2
                out.append(f"На ваш участок ≈ {num(rnd(mid * area_m2 / 10))} кг")
            return out
        if self.high <= 0:
            return ["Не вносить"]
        label = {"N": "азот, кг N/га", "P": "фосфор, кг P₂O₅/га", "K": "калий, кг K₂O/га"}[self.nutrient]
        out = [f"Доза: {rng(self.low, self.high)} ({label})"]
        if self.fertilizer:
            pct = self.fertilizer["pct"]
            lo, hi = self.low * 100 / pct, self.high * 100 / pct
            out.append(f"{self.fertilizer['name']}: {rng(rnd(lo), rnd(hi))} кг/га "
                       f"({rng(rnd(lo / 10, 1), rnd(hi / 10, 1))} г/м²)")
            if area_m2:
                mid = (lo + hi) / 2 / 10  # г/м²
                kg = mid * area_m2 / 1000
                out.append(f"На ваш участок ≈ {num(rnd(kg, 1))} кг")
        if self.note:
            out.append(self.note)
        return out


def fertilizer_for(nutrient: str, crop: str | None) -> dict:
    default = RULES["default_fertilizer"][nutrient]
    if isinstance(default, dict):
        default = default.get(crop or "grain", "kcl")
    return FERTS[default]


def lime_suppressed(answers: dict) -> bool:
    return answers.get("carb") in ("carb1", "carb2")


def dose_for(indicator: str, answers: dict) -> Dose | None:
    level_id = answers.get(indicator)
    if not level_id:
        return None
    _, lvl = LEVELS[level_id]
    crop, texture = answers.get("crop"), answers.get("texture")

    if indicator == "ph":
        lime = lvl.get("lime")
        if not lime or lime_suppressed(answers) or texture not in lime:
            return None
        if level_id == "ph4" and crop == "potato":
            return None  # поддерживающее известкование — только под требовательные культуры
        lo, hi = lime[texture]
        return Dose("lime", lo, hi)

    if indicator == "n":
        full = RULES["n_full"].get(crop or "grain")
        lo, hi = full["range"]
        mode = lvl.get("n_mode")
        if mode == "full":
            return Dose("N", lo, hi, fertilizer_for("N", crop), full["note"])
        if mode == "minus_reserve":
            r = lvl.get("reserve", 0)
            return Dose("N", max(0, lo - r), max(0, hi - r), fertilizer_for("N", crop),
                        f"Уже учтён запас в почве ≈{r} кг N/га.")
        return Dose("N", 0, 0)

    if indicator in ("p", "k"):
        d = lvl.get("dose", {}).get(crop or "grain")
        if not d:
            return None
        nutrient = indicator.upper()
        return Dose(nutrient, d[0], d[1], fertilizer_for(nutrient, crop))
    return None


# ---------- отчёт ----------

@dataclass
class Card:
    indicator: str
    name: str
    level_title: str
    light: str
    meaning: str
    actions: list[str]
    dose_lines: list[str] = field(default_factory=list)


@dataclass
class Report:
    overall: str | None
    cards: list[Card]
    combos: list[dict]
    plan: list[str]
    skip_buy: list[str]
    warnings: list[str]


def build_context(answers: dict, month: int | None = None) -> dict:
    ctx = dict(answers)
    ctx["org"] = organics_light(answers)
    if month:
        ctx["month"] = month
    lights = [level_light(answers[i], ctx) for i in MAIN_INDICATORS if answers.get(i)]
    if ctx["org"]:
        lights.append(ctx["org"])
    ctx["_lights"] = lights
    ctx["_all_green"] = bool(lights) and all(l == "green" for l in lights) and len(lights) >= 3
    return ctx


def combo_light(combo: dict, ctx: dict) -> str:
    return apply_light_rules(combo["light"], combo.get("light_rules"), ctx)


def matched_combos(ctx: dict) -> list[dict]:
    out = []
    for combo in RULES["combos"]:
        if match_when(combo["when"], ctx):
            c = dict(combo)
            c["light"] = combo_light(combo, ctx)
            out.append(c)
    out.sort(key=lambda c: (c["priority"], -RANK[c["light"]]))
    return out


def build_report(answers: dict, month: int | None = None) -> Report:
    ctx = build_context(answers, month)
    area = float(answers.get("area") or 0)
    cards: list[Card] = []
    warnings: list[str] = []

    for ind_id in MAIN_INDICATORS:
        level_id = answers.get(ind_id)
        if not level_id:
            continue
        ind = INDICATORS[ind_id]
        _, lvl = LEVELS[level_id]
        card = Card(ind_id, ind["name"], lvl["title"], level_light(level_id, ctx),
                    lvl["meaning"], list(lvl["actions"]))
        dose = dose_for(ind_id, answers)
        if ind_id == "ph" and lvl.get("lime") and lime_suppressed(answers):
            card.actions.append("Тест с уксусом показал шипение — известь сейчас не вносить.")
        if dose:
            card.dose_lines = dose.lines(area)
        cards.append(card)

    if ctx["org"]:
        org = RULES["organics"]["levels"][ctx["org"]]
        parts = [LEVELS[answers[p]][1]["title"] for p in ORG_PARTS if answers.get(p)]
        cards.append(Card("org", RULES["organics"]["name"], f"{org['title']} ({'; '.join(parts)})",
                          ctx["org"], org["meaning"], list(org["actions"])))

    combos = matched_combos(ctx)

    if answers.get("manure") == "yes" and answers.get("k"):
        warnings.append("Калийный тест сделан вскоре после навоза или аммонийных удобрений — результат может быть завышен.")
    if not cards:
        warnings.append("Не введён ни один результат теста.")

    overall = worst(*[c.light for c in cards], *[c["light"] for c in combos if c["id"] != "K18"])
    return Report(overall, cards, combos, build_plan(answers, ctx), skip_list(answers), warnings)


def build_plan(answers: dict, ctx: dict) -> list[str]:
    """План по приоритетам бюджета (раздел 8 брошюры)."""
    plan: list[str] = []
    ph, n, p, k = (answers.get(x) for x in ("ph", "n", "p", "k"))
    light = lambda lv: level_light(lv, ctx) if lv else None  # noqa: E731

    if ph in ("ph1", "ph2") and not lime_suppressed(answers):
        plan.append("Известкование этой осенью — главный приоритет: без него удобрения работают вполсилы.")
    if light(n) == "red":
        plan.append("Азот под текущую культуру — полная доза в рекомендованные сроки.")
    if light(p) == "red":
        plan.append("Фосфор — полная доза, на кислой почве только локально в рядки или лунки.")
    if light(k) == "red":
        plan.append("Калий — полная доза (на песке и супеси — весной в два приёма).")
    if ph == "ph3" and not lime_suppressed(answers):
        plan.append("Известкование в течение 1–2 лет (pH 5,1–5,5).")
    if n == "n2":
        plan.append("Азот — уменьшенная доза с учётом запаса в почве.")
    if light(p) == "yellow" and p != "p6":
        plan.append("Фосфор — доза по III группе.")
    if light(k) == "yellow" and k != "k6":
        plan.append("Калий — доза по группе.")
    if ctx.get("org") in ("red", "yellow"):
        plan.append("Органика: навоз или компост и сидераты (раздел 6).")
    if not plan:
        plan.append("Срочных действий нет: поддерживающие дозы и повторные тесты по графику.")
    return plan


def skip_list(answers: dict) -> list[str]:
    out = []
    ph, carb, n, p, k = (answers.get(x) for x in ("ph", "carb", "n", "p", "k"))
    tex, crop = answers.get("texture"), answers.get("crop")
    if ph in ("ph5", "ph6") or carb in ("carb1", "carb2") or (ph == "ph4" and tex != "loam"):
        out.append("Известь")
    if p in ("p5", "p6"):
        out.append("Фосфорные удобрения (кроме небольшой стартовой дозы в V группе)" if p == "p5" else "Фосфорные удобрения")
    if k == "k6" or (k == "k5" and crop == "grain"):
        out.append("Калийные удобрения")
    if n in ("n3", "n4"):
        out.append("Азот на ближайшую подкормку")
    return out


# ---------- калькулятор ----------

def convert(dose_kg_ai_per_ha: float, fert_id: str, area_m2: float = 0) -> dict:
    fert = FERTS[fert_id]
    kg_ha = dose_kg_ai_per_ha * 100 / fert["pct"]
    g_m2 = kg_ha / 10
    return {
        "fertilizer": fert["name"],
        "kg_per_ha": rnd(kg_ha, 1),
        "g_per_m2": rnd(g_m2, 1),
        "kg_for_area": rnd(g_m2 * area_m2 / 1000, 2) if area_m2 else None,
        "tablespoons_per_m2": rnd(g_m2 / 17.5, 1),
    }
