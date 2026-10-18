/* Движок рекомендаций «ПочваСвет» для мини-приложения.
   Точная копия логики engine.py; сверяется с ним скриптом compare_engines.py. */
function makeEngine(RULES) {
  const RANK = { green: 0, yellow: 1, red: 2 };
  const MAIN = ["ph", "carb", "n", "p", "k"];
  const ORG_PARTS = ["org_color", "org_foam", "org_worms"];
  const INDICATORS = {}, LEVELS = {}, FERTS = {};
  for (const ind of RULES.indicators) {
    INDICATORS[ind.id] = ind;
    for (const lvl of ind.levels) LEVELS[lvl.id] = [ind.id, lvl];
  }
  for (const f of RULES.fertilizers) FERTS[f.id] = f;

  const rnd = (x, nd = 0) => Number(Math.round(Number(x + "e" + nd)) + "e-" + nd);
  const num = x => Math.abs(x - rnd(x)) < 1e-9 ? String(rnd(x)) : x.toFixed(1).replace(".", ",");
  const rng = (a, b) => Math.abs(a - b) < 1e-9 ? num(a) : `${num(a)}–${num(b)}`;
  const worst = lights => {
    const p = lights.filter(Boolean);
    return p.length ? p.reduce((a, b) => (RANK[b] > RANK[a] ? b : a)) : null;
  };

  function matchWhen(when, ctx) {
    for (const [key, allowed] of Object.entries(when)) {
      if (key === "any") { if (!allowed.some(s => matchWhen(s, ctx))) return false; }
      else if (key === "all_green") { if (Boolean(ctx._all_green) !== Boolean(allowed)) return false; }
      else if (!allowed.includes(ctx[key])) return false;
    }
    return true;
  }
  function applyLightRules(base, rules, ctx) {
    for (const r of rules || []) if (matchWhen(r.when, ctx)) return r.light;
    return base;
  }
  const levelLight = (id, ctx) => applyLightRules(LEVELS[id][1].light, LEVELS[id][1].light_rules, ctx);

  function organicsLight(a) {
    const lights = ORG_PARTS.filter(p => a[p]).map(p => levelLight(a[p], a));
    if (!lights.length) return null;
    if (lights.length === 1) return lights[0];
    const reds = lights.filter(l => l === "red").length, greens = lights.filter(l => l === "green").length;
    if (reds >= 2) return "red";
    if (greens >= 2 && reds === 0) return "green";
    return "yellow";
  }

  function fertilizerFor(nutrient, crop) {
    let d = RULES.default_fertilizer[nutrient];
    if (typeof d === "object") d = d[crop || "grain"] || "kcl";
    return FERTS[d];
  }
  const limeSuppressed = a => a.carb === "carb1" || a.carb === "carb2";

  function doseLines(d, area) {
    if (d.nutrient === "lime") {
      const out = [`Доломитовая мука: ${rng(d.low, d.high)} т/га (${rng(d.low * 100, d.high * 100)} г/м²)`];
      if (area) out.push(`На ваш участок ≈ ${num(rnd((d.low + d.high) / 2 * area / 10))} кг`);
      return out;
    }
    if (d.high <= 0) return ["Не вносить"];
    const label = { N: "азот, кг N/га", P: "фосфор, кг P₂O₅/га", K: "калий, кг K₂O/га" }[d.nutrient];
    const out = [`Доза: ${rng(d.low, d.high)} (${label})`];
    if (d.fertilizer) {
      const pct = d.fertilizer.pct, lo = d.low * 100 / pct, hi = d.high * 100 / pct;
      out.push(`${d.fertilizer.name}: ${rng(rnd(lo), rnd(hi))} кг/га (${rng(rnd(lo / 10, 1), rnd(hi / 10, 1))} г/м²)`);
      if (area) out.push(`На ваш участок ≈ ${num(rnd((lo + hi) / 2 / 10 * area / 1000, 1))} кг`);
    }
    if (d.note) out.push(d.note);
    return out;
  }

  function doseFor(ind, a) {
    const id = a[ind];
    if (!id) return null;
    const lvl = LEVELS[id][1], crop = a.crop, tex = a.texture;
    if (ind === "ph") {
      const lime = lvl.lime;
      if (!lime || limeSuppressed(a) || !(tex in lime)) return null;
      if (id === "ph4" && crop === "potato") return null;
      return { nutrient: "lime", low: lime[tex][0], high: lime[tex][1] };
    }
    if (ind === "n") {
      const full = RULES.n_full[crop || "grain"], [lo, hi] = full.range;
      if (lvl.n_mode === "full") return { nutrient: "N", low: lo, high: hi, fertilizer: fertilizerFor("N", crop), note: full.note };
      if (lvl.n_mode === "minus_reserve") {
        const r = lvl.reserve || 0;
        return { nutrient: "N", low: Math.max(0, lo - r), high: Math.max(0, hi - r), fertilizer: fertilizerFor("N", crop),
                 note: `Уже учтён запас в почве ≈${r} кг N/га.` };
      }
      return { nutrient: "N", low: 0, high: 0 };
    }
    if (ind === "p" || ind === "k") {
      const d = (lvl.dose || {})[crop || "grain"];
      if (!d) return null;
      const n = ind.toUpperCase();
      return { nutrient: n, low: d[0], high: d[1], fertilizer: fertilizerFor(n, crop) };
    }
    return null;
  }

  function buildContext(a, month) {
    const ctx = Object.assign({}, a);
    ctx.org = organicsLight(a);
    if (month) ctx.month = month;
    const lights = MAIN.filter(i => a[i]).map(i => levelLight(a[i], ctx));
    if (ctx.org) lights.push(ctx.org);
    ctx._all_green = lights.length >= 3 && lights.every(l => l === "green");
    return ctx;
  }

  function matchedCombos(ctx) {
    return RULES.combos.filter(c => matchWhen(c.when, ctx))
      .map(c => Object.assign({}, c, { light: applyLightRules(c.light, c.light_rules, ctx) }))
      .map((c, i) => [c, i])
      .sort((x, y) => (x[0].priority - y[0].priority) || (RANK[y[0].light] - RANK[x[0].light]) || (x[1] - y[1]))
      .map(x => x[0]);
  }

  function buildPlan(a, ctx) {
    const plan = [], light = id => id ? levelLight(id, ctx) : null;
    if ((a.ph === "ph1" || a.ph === "ph2") && !limeSuppressed(a)) plan.push("Известкование этой осенью — главный приоритет: без него удобрения работают вполсилы.");
    if (light(a.n) === "red") plan.push("Азот под текущую культуру — полная доза в рекомендованные сроки.");
    if (light(a.p) === "red") plan.push("Фосфор — полная доза, на кислой почве только локально в рядки или лунки.");
    if (light(a.k) === "red") plan.push("Калий — полная доза (на песке и супеси — весной в два приёма).");
    if (a.ph === "ph3" && !limeSuppressed(a)) plan.push("Известкование в течение 1–2 лет (pH 5,1–5,5).");
    if (a.n === "n2") plan.push("Азот — уменьшенная доза с учётом запаса в почве.");
    if (light(a.p) === "yellow" && a.p !== "p6") plan.push("Фосфор — доза по III группе.");
    if (light(a.k) === "yellow" && a.k !== "k6") plan.push("Калий — доза по группе.");
    if (ctx.org === "red" || ctx.org === "yellow") plan.push("Органика: навоз или компост и сидераты (раздел 6).");
    if (!plan.length) plan.push("Срочных действий нет: поддерживающие дозы и повторные тесты по графику.");
    return plan;
  }

  function skipList(a) {
    const out = [];
    if (a.ph === "ph5" || a.ph === "ph6" || limeSuppressed(a) || (a.ph === "ph4" && a.texture !== "loam")) out.push("Известь");
    if (a.p === "p5" || a.p === "p6") out.push(a.p === "p5" ? "Фосфорные удобрения (кроме небольшой стартовой дозы в V группе)" : "Фосфорные удобрения");
    if (a.k === "k6" || (a.k === "k5" && a.crop === "grain")) out.push("Калийные удобрения");
    if (a.n === "n3" || a.n === "n4") out.push("Азот на ближайшую подкормку");
    return out;
  }

  function buildReport(a, month) {
    const ctx = buildContext(a, month), area = Number(a.area || 0), cards = [], warnings = [];
    for (const ind of MAIN) {
      const id = a[ind];
      if (!id) continue;
      const lvl = LEVELS[id][1];
      const card = { indicator: ind, name: INDICATORS[ind].name, levelTitle: lvl.title, light: levelLight(id, ctx),
                     meaning: lvl.meaning, actions: lvl.actions.slice(), doseLines: [] };
      const d = doseFor(ind, a);
      if (ind === "ph" && lvl.lime && limeSuppressed(a)) card.actions.push("Тест с уксусом показал шипение — известь сейчас не вносить.");
      if (d) card.doseLines = doseLines(d, area);
      cards.push(card);
    }
    if (ctx.org) {
      const org = RULES.organics.levels[ctx.org];
      const parts = ORG_PARTS.filter(p => a[p]).map(p => LEVELS[a[p]][1].title);
      cards.push({ indicator: "org", name: RULES.organics.name, levelTitle: `${org.title} (${parts.join("; ")})`,
                   light: ctx.org, meaning: org.meaning, actions: org.actions.slice(), doseLines: [] });
    }
    const combos = matchedCombos(ctx);
    if (a.manure === "yes" && a.k) warnings.push("Калийный тест сделан вскоре после навоза или аммонийных удобрений — результат может быть завышен.");
    if (!cards.length) warnings.push("Не введён ни один результат теста.");
    const overall = worst(cards.map(c => c.light).concat(combos.filter(c => c.id !== "K18").map(c => c.light)));
    return { overall, cards, combos, plan: buildPlan(a, ctx), skipBuy: skipList(a), warnings };
  }

  function convert(dose, fertId, area) {
    const f = FERTS[fertId], kgHa = dose * 100 / f.pct, gM2 = kgHa / 10;
    return { fertilizer: f.name, kg_per_ha: rnd(kgHa, 1), g_per_m2: rnd(gM2, 1),
             kg_for_area: area ? rnd(gM2 * area / 1000, 2) : null, tablespoons_per_m2: rnd(gM2 / 17.5, 1) };
  }

  return { buildReport, convert, levelLight, INDICATORS, LEVELS, RANK, num };
}
if (typeof module !== "undefined") module.exports = { makeEngine };
