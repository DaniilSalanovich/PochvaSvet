"""Сверка движков Python (бот) и JavaScript (мини-приложение): python compare_engines.py

Генерирует случайные наборы ответов, считает отчёт обоими движками и требует
полного совпадения: сигналов, доз, сочетаний, плана и списка «не покупать».
"""
import json
import random
import subprocess
from dataclasses import asdict
from pathlib import Path

from engine import RULES, build_report

HERE = Path(__file__).parent
N = 5000

choices = {}
for q in RULES["questions"]:
    if q.get("indicator"):
        ind = next(i for i in RULES["indicators"] if i["id"] == q["indicator"])
        choices[q["id"]] = [l["id"] for l in ind["levels"]] + [None]
    else:
        choices[q["id"]] = [o["id"] for o in q["options"]] + ([None] if q["id"] in ("texture", "crop") else [])

rnd = random.Random(7)
cases = []
for _ in range(N):
    ans = {k: rnd.choice(v) for k, v in choices.items()}
    cases.append({"answers": {k: v for k, v in ans.items() if v is not None}, "month": rnd.randint(1, 12)})


def norm_py(rep):
    d = asdict(rep)
    return {
        "overall": d["overall"],
        "cards": [[c["indicator"], c["level_title"], c["light"], c["actions"], c["dose_lines"]] for c in d["cards"]],
        "combos": [[c["id"], c["light"]] for c in d["combos"]],
        "plan": d["plan"], "skip": d["skip_buy"], "warnings": d["warnings"],
    }


js = r"""
const { makeEngine } = require(process.argv[1]);
const E = makeEngine(require(process.argv[2]));
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = cases.map(c => {
  const r = E.buildReport(c.answers, c.month);
  return { overall: r.overall,
    cards: r.cards.map(x => [x.indicator, x.levelTitle, x.light, x.actions, x.doseLines]),
    combos: r.combos.map(x => [x.id, x.light]), plan: r.plan, skip: r.skipBuy, warnings: r.warnings };
});
process.stdout.write(JSON.stringify(out));
"""
res = subprocess.run(["node", "-e", js, str(HERE / "webapp" / "engine.js"), str(HERE / "rules.json")],
                     input=json.dumps(cases), capture_output=True, text=True, check=True)
js_out = json.loads(res.stdout)

bad = 0
for case, j in zip(cases, js_out):
    p = norm_py(build_report(case["answers"], case["month"]))
    if p != j:
        bad += 1
        if bad <= 3:
            print("РАСХОЖДЕНИЕ", case)
            for k in p:
                if p[k] != j[k]:
                    print("  ", k, "\n   py:", p[k], "\n   js:", j[k])
print(f"{N - bad} из {N} отчётов совпали полностью")
raise SystemExit(1 if bad else 0)
