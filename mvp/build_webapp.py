"""Сборка мини-приложения из rules.json и webapp/engine.js: python build_webapp.py

webapp/index.html   — для Telegram (подключает telegram-web-app.js); его адрес — WEBAPP_URL.
webapp/preview.html — та же страница без скрипта Telegram, для просмотра в браузере.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
tpl = (HERE / "webapp" / "template.html").read_text(encoding="utf-8")
rules = json.loads((HERE / "rules.json").read_text(encoding="utf-8"))
engine = (HERE / "webapp" / "engine.js").read_text(encoding="utf-8")

page = tpl.replace("/*__ENGINE__*/", engine).replace(
    "/*__RULES__*/null", json.dumps(rules, ensure_ascii=False).replace("</", "<\\/"))
tg = '<script src="https://telegram.org/js/telegram-web-app.js"></script>'
body = page.replace("<!--TG_SCRIPT-->\n", "")

(HERE / "webapp" / "preview.html").write_text(body, encoding="utf-8")
(HERE / "webapp" / "index.html").write_text(
    '<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    + tg + "\n" + page.replace("<!--TG_SCRIPT-->\n", "").replace("<title>", "<title>", 1)
    .replace("<style>", "<style>\n:root { color-scheme: light; padding-top: env(safe-area-inset-top, 0px); }\n"
             "body { margin: 0; } [hidden] { display: none !important; } img { max-width: 100%; }\n", 1)
    .replace("<div class=\"wrap\">", "</head>\n<body>\n<div class=\"wrap\">", 1)
    + "</body>\n</html>\n", encoding="utf-8")
print("ok: webapp/index.html, webapp/preview.html")
