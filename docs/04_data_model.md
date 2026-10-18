# Модель данных

## 1. Схема БД (PostgreSQL 16)

Эталон — DDL ниже; SQLAlchemy-модели в `app/db/models.py` повторяют его, миграции создаёт Alembic.
Все времена — `timestamptz` в UTC; даты событий пользователя (внесение, урожай) — `date`.

```sql
-- Справочник районов (заполняется миграцией из data/districts.csv)
CREATE TABLE districts (
    code        text PRIMARY KEY,                -- 'minsk-borisov'
    region      text NOT NULL,                   -- 'Минская'
    name        text NOT NULL,                   -- 'Борисовский'
    lat         double precision,                -- центр района, для погоды
    lon         double precision
);

CREATE TABLE users (
    id                bigserial PRIMARY KEY,
    tg_id             bigint UNIQUE NOT NULL,
    first_name        text,
    role              text NOT NULL DEFAULT 'farmer' CHECK (role IN ('farmer','agronomist','admin')),
    district_code     text REFERENCES districts(code),
    farm_type         text CHECK (farm_type IN ('kfh','lph','other')),
    tz                text NOT NULL DEFAULT 'Europe/Minsk',
    consent_at        timestamptz,               -- согласие на обработку ПД (NULL = не дано)
    stats_consent     boolean NOT NULL DEFAULT false,  -- обезличенная статистика
    dataset_consent   boolean NOT NULL DEFAULT false,  -- фото для калибровки
    is_active         boolean NOT NULL DEFAULT true,   -- false, если заблокировал бота
    created_at        timestamptz NOT NULL DEFAULT now(),
    last_seen_at      timestamptz
);

CREATE TABLE fields (
    id            bigserial PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 40),
    area_m2       numeric(12,1) NOT NULL CHECK (area_m2 > 0),
    texture       text NOT NULL CHECK (texture IN ('sand','sandy_loam','loam')),
    crop          text NOT NULL CHECK (crop IN ('grain','potato','veg')),
    predecessor   text,
    lat           double precision,
    lon           double precision,
    archived_at   timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON fields (user_id) WHERE archived_at IS NULL;

-- Разбор: ответы + снимок отчёта. Отчёт хранится целиком, чтобы смена правил не меняла историю.
CREATE TABLE analyses (
    id              bigserial PRIMARY KEY,
    user_id         bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    field_id        bigint REFERENCES fields(id) ON DELETE SET NULL,   -- NULL: разбор без поля
    answers         jsonb NOT NULL,          -- {"texture":"sand","ph":"ph2",...}
    report          jsonb NOT NULL,          -- результат core.engine.build_report (asdict)
    overall         text CHECK (overall IN ('green','yellow','red')),
    rules_version   text NOT NULL,           -- rules.json → meta.version
    source          text NOT NULL DEFAULT 'buttons' CHECK (source IN ('buttons','photo','webapp')),
    saved           boolean NOT NULL DEFAULT false,   -- сохранён в дневник
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON analyses (field_id, created_at DESC);

-- Распознавание фото (v2)
CREATE TABLE photo_analyses (
    id              bigserial PRIMARY KEY,
    user_id         bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    field_id        bigint REFERENCES fields(id) ON DELETE SET NULL,
    analysis_id     bigint REFERENCES analyses(id) ON DELETE SET NULL,
    tg_file_id      text NOT NULL,
    storage_path    text,                    -- только при dataset_consent
    card_batch      text,                    -- партия карты из QR
    quality         jsonb NOT NULL,          -- {"blur":..,"exposure":..,"glare":..,"ok":true,"problems":[]}
    readings        jsonb NOT NULL,          -- {"ph":{"level":"ph2","confidence":0.82,"value":4.8,"lab":[..]},...}
    confirmed       jsonb,                   -- уровни после подтверждения пользователем
    pipeline_version text NOT NULL,
    duration_ms     integer,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE diary_entries (
    id          bigserial PRIMARY KEY,
    field_id    bigint NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('analysis','application','sowing','harvest','note')),
    event_date  date NOT NULL,
    analysis_id bigint REFERENCES analyses(id) ON DELETE SET NULL,
    data        jsonb NOT NULL DEFAULT '{}',
    -- application: {"fertilizer_id":"map","fertilizer_name":"Аммофос 12-52","amount_kg":12.0,
    --               "nutrient":"P","ai_kg_per_ha":104,"from_analysis":123}
    -- sowing:      {"crop":"potato","variety":"Скарб"}
    -- harvest:     {"amount_kg":1450, "yield_c_ha":241.7}
    -- note:        {"text":"...", "tg_file_ids":["..."]}
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON diary_entries (field_id, event_date DESC);

CREATE TABLE reminders (
    id          bigserial PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    field_id    bigint REFERENCES fields(id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('action','retest','timer','custom')),
    code        text NOT NULL,           -- 'lime','n_test','pk_retest','timer_p',...
    text        text NOT NULL,           -- готовый текст сообщения
    payload     jsonb NOT NULL DEFAULT '{}',
    due_at      timestamptz NOT NULL,
    status      text NOT NULL DEFAULT 'scheduled'
                CHECK (status IN ('scheduled','sent','done','snoozed','cancelled','failed')),
    sent_at     timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (field_id, code, due_at)      -- защита от дублей при повторном создании
);
CREATE INDEX ON reminders (due_at) WHERE status = 'scheduled';

-- Агрономы и обращения (v2)
CREATE TABLE agronomists (
    user_id        bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    district_code  text REFERENCES districts(code),   -- NULL = общий
    chat_id        bigint NOT NULL,                     -- куда слать обращения
    active         boolean NOT NULL DEFAULT true
);

CREATE TABLE tickets (
    id              bigserial PRIMARY KEY,
    user_id         bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    analysis_id     bigint REFERENCES analyses(id) ON DELETE SET NULL,
    agronomist_id   bigint REFERENCES users(id),
    question        text NOT NULL,
    status          text NOT NULL DEFAULT 'new' CHECK (status IN ('new','in_progress','closed')),
    agro_chat_id    bigint,
    agro_message_id bigint,           -- сообщение-карточка у агронома: reply на него = ответ
    created_at      timestamptz NOT NULL DEFAULT now(),
    closed_at       timestamptz
);

CREATE TABLE ticket_messages (
    id          bigserial PRIMARY KEY,
    ticket_id   bigint NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    author      text NOT NULL CHECK (author IN ('farmer','agronomist')),
    text        text NOT NULL,
    tg_file_ids text[] NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Версии правил (v2: загрузка без перезапуска)
CREATE TABLE rules_versions (
    version      text PRIMARY KEY,         -- meta.version
    content      jsonb NOT NULL,
    uploaded_by  bigint REFERENCES users(id),
    is_active    boolean NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ON rules_versions (is_active) WHERE is_active;
```

Удаление пользователя по `/privacy` → `DELETE FROM users WHERE id = …` (каскад удаляет всё) +
удаление файлов фото из `PHOTO_STORAGE_DIR`.

## 2. Правила (`rules/rules.json`)

Формальная схема — `rules/rules.schema.json` (JSON Schema draft 2020-12). Кратко:

| Ключ | Тип | Содержимое |
| --- | --- | --- |
| `meta` | объект | `title`, `version` (строка, меняется при каждой правке), `disclaimer` |
| `lights` | объект | `green`/`yellow`/`red` → `emoji`, `name`, `rank`, `hint` |
| `questions` | массив | Шаги мастера: `id`, `text`, `indicator` (для тестов) или `options` (для почвы, культуры, навоза, площади) |
| `indicators` | массив | Тесты: `id`, `name`, `intro`, `levels[]` |
| `indicators[].levels[]` | объект | `id`, `button`, `title`, `light`, `meaning`, `actions[]`, необязательно: `light_rules`, `lime` (т/га по почве), `dose` (кг д. в./га по культуре), `n_mode`, `reserve` |
| `organics` | объект | Правило сложения трёх признаков и тексты для итоговых уровней |
| `n_full` | объект | Полная доза азота по культуре: `range`, `note` |
| `combos` | массив | Сочетания: `id`, `group`, `title`, `light`, `priority` (1 — важнее), `when`, `light_rules`, `why`, `actions[]` |
| `budget`, `calendar`, `safety` | массивы | Тексты разделов брошюры |
| `fertilizers` | массив | `id`, `name`, `nutrient`, `pct` |
| `default_fertilizer` | объект | Удобрение по умолчанию для пересчёта: N, P — строкой; K — по культуре |

### Условия `when`

```json
{"ph": ["ph1", "ph2"], "p": ["p1", "p2"]}                       // И по ключам, ИЛИ внутри списка
{"any": [{"ph": ["ph6"]}, {"carb": ["carb2"]}], "p": ["p5","p6"]} // any — хотя бы одно из
{"all_green": true}                                               // все введённые показатели зелёные (≥ 3)
{"org": ["red"], "month": [3, 4]}                                 // производные ключи
```

Допустимые ключи: `ph`, `carb`, `n`, `p`, `k`, `org_color`, `org_foam`, `org_worms`, `texture`, `crop`,
`manure`, `org` (итог органики), `month`, `any`, `all_green`.

## 3. Структуры в коде

```python
# app/core/engine.py
@dataclass
class Card:            # карточка теста в отчёте
    indicator: str; name: str; level_title: str; light: Light
    meaning: str; actions: list[str]; dose_lines: list[str]

@dataclass
class Report:
    overall: Light | None
    cards: list[Card]
    combos: list[dict]      # копии сочетаний из rules.json с вычисленным light
    plan: list[str]
    skip_buy: list[str]
    warnings: list[str]

# app/cv/pipeline.py (v2)
@dataclass
class Reading:
    test: str               # 'ph','n','p','k','org_color'
    level: str | None       # id уровня или None
    confidence: float       # 0..1
    value: float | None     # pH или мг/кг, если оценивается
    status: Literal['ok','uncertain','boundary','not_found']

@dataclass
class RecognitionResult:
    ok: bool
    problems: list[str]     # коды проблем качества: 'no_markers','blur','dark','overexposed','glare','too_small'
    card_batch: str | None
    readings: dict[str, Reading]
    debug: dict             # промежуточные значения, только в логах уровня DEBUG
```
