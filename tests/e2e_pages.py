"""Browser checks for navigation and every non-chat page (Playwright + Chromium). Not collected by pytest.
Usage: uvicorn server:app --port 8765  (fresh, empty logs/)  then  python tests/e2e_pages.py http://localhost:8765
"""
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
results, errs = [], []


def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def say(pg, text):
    n = pg.locator(".msg.assistant:not(.typing)").count()
    pg.fill("#composer-input", text); pg.press("#composer-input", "Enter")
    pg.wait_for_function(f"document.querySelectorAll('.msg.assistant:not(.typing)').length > {n}")


with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"]); ctx = b.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto(BASE); pg.wait_for_selector(".msg.assistant")

    # navigation
    for key, title in [("transcripts", "Transcripts"), ("evaluation", "Evaluation Lab"), ("analytics", "Analytics"), ("architecture", "System Architecture"), ("settings", "Settings"), ("chat", "Chat")]:
        pg.click(f'.nav[data-page="{key}"]'); pg.wait_for_timeout(250)
        visible = [k for k in ["chat", "transcripts", "evaluation", "analytics", "architecture", "settings"] if pg.is_visible(f"#page-{k}")]
        check(f"nav -> {key}: only that page visible, title + aria-current", visible == [key] and pg.inner_text("#page-title") == title and pg.get_attribute(f'.nav[data-page="{key}"]', "aria-current") == "page", str(visible))

    # empty states (fresh logs, no evaluation yet)
    pg.goto(BASE + "#analytics"); pg.wait_for_selector("#page-analytics .empty")
    check("analytics: empty states for usage and synthetic eval (no invented data)", pg.locator("#page-analytics .empty").count() == 2 and pg.locator("#page-analytics .stat").count() == 0)
    pg.goto(BASE + "#transcripts"); pg.wait_for_selector("#page-transcripts .card .tx")
    check("transcripts: raw log shows only the page-load greeting (no user messages yet)", pg.locator("#page-transcripts .card .tx").count() == 1 and "(greeting" in pg.inner_text("#page-transcripts"), f"cards={pg.locator('#page-transcripts .card .tx').count()} greeting_text={'(greeting' in pg.inner_text('#page-transcripts')}")
    pg.goto(BASE + "#evaluation"); pg.wait_for_selector("#page-evaluation .empty")
    check("evaluation: empty state with Run button", pg.locator("#page-evaluation .empty button").count() == 1)

    # generate real usage through the chat UI
    pg.goto(BASE + "#chat"); pg.wait_for_selector(".msg.assistant")
    for t in ["yes", "What documents might I need?", "purple elephants", "my ssn is 123-45-6789 password: hunter2", "I want to speak to a human"]:
        say(pg, t)
    pg.click('.nav[data-page="transcripts"]'); pg.wait_for_function("document.querySelectorAll('#page-transcripts .card .tx').length >= 6")
    body = pg.inner_text("#page-transcripts")
    check("transcripts: turns shown with real data + real badge", pg.locator("#page-transcripts .card .tx").count() >= 6 and "Application usage" in body)
    check("transcripts: credentials redacted", "123-45-6789" not in body and "hunter2" not in body and "REDACTED" in body)
    check("transcripts: state before -> after shown", "CONSENT → INQUIRY_TYPE" in body)
    pg.fill('#page-transcripts input[type=search]', "documents"); pg.wait_for_timeout(700)
    n_search = pg.locator("#page-transcripts .card .tx").count()
    check("transcripts: search narrows results", 0 < n_search < 6, str(n_search))
    pg.fill('#page-transcripts input[type=search]', ""); pg.wait_for_function("document.querySelectorAll('#page-transcripts .card .tx').length >= 6")
    pg.select_option('#page-transcripts select[aria-label="State"]', "HUMAN_HANDOFF"); pg.wait_for_timeout(500)
    check("transcripts: state filter", 0 < pg.locator("#page-transcripts .card .tx").count() < 6)
    pg.select_option('#page-transcripts select[aria-label="State"]', ""); pg.wait_for_timeout(400)
    pg.select_option('#page-transcripts select[aria-label="Prompt version"]', "B"); pg.wait_for_timeout(500)
    check("transcripts: prompt filter (none on B yet -> filtered empty)", "No turns match" in pg.inner_text("#page-transcripts"))
    pg.select_option('#page-transcripts select[aria-label="Prompt version"]', ""); pg.wait_for_timeout(400)
    sid_opts = pg.locator('#page-transcripts select[aria-label="Session"] option').count()
    pg.select_option('#page-transcripts select[aria-label="Session"]', index=1); pg.wait_for_timeout(400)
    check("transcripts: session filter", sid_opts >= 2 and pg.locator("#page-transcripts .card .tx").count() >= 1)
    with pg.expect_download() as d: pg.click("text=Export CSV")
    csv_text = open(d.value.path(), encoding="utf-8").read()
    check("export CSV downloads real rows, no credentials", csv_text.startswith("session_id,") and "hunter2" not in csv_text and len(csv_text.splitlines()) > 5)
    with pg.expect_download() as d: pg.click("text=Export JSON")
    check("export JSON downloads", open(d.value.path(), encoding="utf-8").read().lstrip().startswith("["))
    pg.once("dialog", lambda dlg: dlg.dismiss()); pg.click("text=Delete logs"); pg.wait_for_timeout(400)
    check("delete: dismissing the confirmation keeps data", pg.locator("#page-transcripts .card .tx").count() >= 1)

    # evaluation
    pg.click('.nav[data-page="evaluation"]'); pg.wait_for_selector("#page-evaluation button:has-text('Run evaluation')"); pg.click("#page-evaluation button:has-text('Run evaluation')"); pg.wait_for_selector("details.scn")
    t = pg.inner_text("#page-evaluation")
    check("evaluation: synthetic label, timestamp, totals", "Synthetic scenarios" in t and "Last run" in t and "scenario runs" in t)
    check("evaluation: includes intent_accuracy criterion + honest A/B note", "intent_accuracy" in t and "by construction" in t)
    pg.locator("details.scn summary").first.click()
    check("evaluation: scenario detail shows expected vs observed intents + transcript", pg.locator("details.scn[open] th", has_text="Observed intent").count() == 1 and pg.locator("details.scn[open] .tx div").count() >= 2)
    pg.select_option('#page-evaluation select[aria-label="Status"]', "fail")
    check("evaluation: failed-only filter (0 failed -> no rows)", pg.locator("details.scn").count() == 0)
    pg.goto(BASE + "#analytics"); pg.wait_for_selector("#page-analytics .stat")
    a = pg.inner_text("#page-analytics")
    check("analytics: real + synthetic sections separately labelled", "Application usage" in a and "Synthetic evaluation" in a and "Last run" in a)
    # eval must not have polluted usage: usage turns == turns from chat only (6 incl greeting)
    check("analytics: evaluation did not add to application usage", pg.locator("#page-analytics .stat b").first.inner_text() == "1", pg.locator("#page-analytics .stat b").first.inner_text())

    # architecture
    pg.goto(BASE + "#architecture"); pg.wait_for_selector(".diagram svg")
    check("architecture: 3 SVG diagrams, with text, not mermaid source", pg.locator(".diagram svg").count() == 3 and "graph TD" not in pg.inner_text("#page-architecture") and pg.locator(".diagram svg text").count() > 40)
    w0 = pg.evaluate("document.querySelector('.diagram svg').getBoundingClientRect().width")
    pg.locator('button[aria-label="Zoom in"]').first.click(); pg.locator('button[aria-label="Zoom in"]').first.click()
    check("architecture: zoom changes diagram size", pg.evaluate("document.querySelector('.diagram svg').getBoundingClientRect().width") > w0)

    # settings
    pg.goto(BASE + "#settings"); pg.wait_for_selector("#page-settings .field")
    pg.select_option('#page-settings select[aria-label="Prompt version"]', "B"); pg.wait_for_timeout(200)
    check("settings: prompt selection reflected in sidebar", pg.inner_text("#prompt-label") == "B")
    pg.click("#btn-new"); pg.goto(BASE + "#chat"); pg.wait_for_selector(".msg.assistant"); say(pg, "yes")
    check("settings: prompt B really used by the backend", pg.evaluate("fetch('/api/transcripts?prompt_version=B').then(r=>r.json()).then(d=>d.count)") is not None and pg.evaluate("fetch('/api/transcripts?prompt_version=B').then(r=>r.json()).then(d=>d.count>0)"))
    pg.goto(BASE + "#settings"); pg.wait_for_selector("#page-settings .field")
    box = pg.locator('#page-settings .field:has-text("Voice input enabled") input')
    if not box.is_disabled():
        box.uncheck(); check("settings: disabling voice input disables the mic button", pg.is_disabled("#btn-mic")); box.check()
    else:
        check("settings: voice input toggle correctly disabled when unsupported", True)
    check("settings: LLM status shows no key, never a key value", "OPENAI_API_KEY" in pg.inner_text("#page-settings") and "sk-" not in pg.inner_text("#page-settings"))
    pg.once("dialog", lambda dlg: dlg.accept()); pg.click("text=Clear history"); pg.wait_for_selector("#page-settings .banner.info")
    pg.goto(BASE + "#transcripts"); pg.wait_for_selector("#page-transcripts .toolbar")
    check("clear history: old transcripts gone", "hunter2" not in pg.inner_text("#page-transcripts") and pg.locator("#page-transcripts .card .tx").count() <= 1)
    pg.goto(BASE + "#evaluation"); pg.wait_for_selector("details.scn")
    check("clear history: evaluation results kept", True)

    # responsive overflow on every page
    for key in ["chat", "transcripts", "evaluation", "analytics", "architecture", "settings"]:
        pg.goto(BASE + "#" + key); pg.wait_for_timeout(500)
        for w in (390, 820):
            pg.set_viewport_size({"width": w, "height": 900}); pg.wait_for_timeout(150)
            ov = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check(f"no page-level horizontal overflow: {key} @ {w}px", ov <= 0, f"overflow={ov}")
        pg.set_viewport_size({"width": 1280, "height": 900})
    b.close()

real = [e for e in errs if "Failed to load resource" not in e]
print("INFO console errors:", errs or "none"); check("no browser console errors", not real, "; ".join(real)[:200])
print(f"\n{sum(results)}/{len(results)} checks passed"); sys.exit(0 if all(results) else 1)
