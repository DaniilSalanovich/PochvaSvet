"""Проверки движка: python test_engine.py (или pytest)."""
from engine import RULES, build_report, convert, LEVELS


def ids(report):
    return [c["id"] for c in report.combos]


def test_rules_consistency():
    level_ids = set(LEVELS)
    for combo in RULES["combos"]:
        def walk(when):
            for key, val in when.items():
                if key == "any":
                    for sub in val:
                        walk(sub)
                elif key in ("ph", "carb", "n", "p", "k"):
                    for v in val:
                        assert v in level_ids, (combo["id"], v)
        walk(combo["when"])
    assert len(RULES["combos"]) == 18


def test_acid_low_p_cabbage():
    r = build_report({"texture": "sand", "crop": "veg", "ph": "ph2", "p": "p1", "k": "k2",
                      "manure": "no", "area": "600"})
    assert r.overall == "red"
    for cid in ("K1", "K3", "K4", "K16"):
        assert cid in ids(r), cid
    assert r.plan[0].startswith("Известкование")


def test_overfed_field():
    r = build_report({"texture": "loam", "crop": "grain", "ph": "ph5", "n": "n3", "p": "p5", "k": "k5",
                      "org_color": "c3", "org_foam": "f3", "manure": "no", "area": "10000"})
    assert "K12" in ids(r) and "K13" in ids(r)
    assert "Известь" in r.skip_buy
    assert r.overall == "green"


def test_carbonates_suppress_lime_and_potato_scab():
    r = build_report({"texture": "loam", "crop": "potato", "ph": "ph3", "carb": "carb2", "manure": "no"})
    ph_card = next(c for c in r.cards if c.indicator == "ph")
    assert not ph_card.dose_lines
    assert "K14" in ids(r) and "K15" in ids(r)


def test_potato_sand_k2_is_red():
    r = build_report({"texture": "sand", "crop": "potato", "k": "k2", "manure": "no"})
    assert next(c for c in r.cards if c.indicator == "k").light == "red"


def test_manure_k_warning():
    r = build_report({"texture": "loam", "crop": "potato", "k": "k5", "manure": "yes"})
    assert "K18" in ids(r) and r.warnings


def test_spring_n_with_good_organics():
    ans = {"texture": "loam", "crop": "grain", "n": "n2", "org_color": "c3", "org_worms": "w3", "manure": "no"}
    assert "K8" in ids(build_report(ans, month=4))
    assert "K8" not in ids(build_report(ans, month=7))


def test_n_minus_reserve():
    r = build_report({"texture": "loam", "crop": "potato", "n": "n2", "manure": "no", "area": "600"})
    lines = next(c for c in r.cards if c.indicator == "n").dose_lines
    assert lines[0].startswith("Доза: 45–75")


def test_convert():
    c = convert(120, "k2so4", 600)
    assert c["kg_per_ha"] == 240 and c["g_per_m2"] == 24 and c["kg_for_area"] == 14.4


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
    r = build_report({"texture": "sand", "crop": "veg", "ph": "ph2", "carb": "carb0", "n": "n1", "p": "p1",
                      "k": "k2", "org_color": "c1", "org_foam": "f1", "manure": "no", "area": "600"}, month=4)
    print("\nОбщий сигнал:", r.overall)
    for c in r.cards:
        print(f"- [{c.light}] {c.name}: {c.level_title}")
        for line in c.dose_lines:
            print("    ", line)
    print("Сочетания:", ", ".join(f"{c['id']} {c['title']}" for c in r.combos))
    print("План:", *r.plan, sep="\n  ")
    print("Не покупать:", r.skip_buy)
