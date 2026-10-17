"""Browser end-to-end check (Playwright + Chromium). Not collected by pytest.

Usage: start the server (uvicorn server:app --port 8765), then
       python tests/e2e_browser.py http://localhost:8765
Drives the real UI against the real backend and prints PASS/FAIL per check.
"""
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
results, console_errors = [], []


def check(name, cond, detail=""):
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def last_assistant(page):
    return page.locator(".msg.assistant:not(.typing)").last.inner_text()


def send(page, text):
    n = page.locator(".msg.assistant:not(.typing)").count()
    page.fill("#composer-input", text); page.press("#composer-input", "Enter")
    page.wait_for_function(f"document.querySelectorAll('.msg.assistant:not(.typing)').length > {n}")


with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, permissions=[])
    page = ctx.new_page()
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    page.goto(BASE); page.wait_for_selector(".msg.assistant")

    check("greeting rendered from backend", "VoiceBridge" in last_assistant(page))
    check("mode label shown", page.inner_text("#mode-label") in ("Local demo mode", "LLM mode"))
    sid = page.inner_text("#chip-session")
    check("welcome + 9 example prompts visible", page.locator("#examples button").count() == 9 and page.is_visible("#welcome"))

    # 1. send a message, state advances, same session
    send(page, "Yes, let's get started.")
    check("send -> INQUIRY_TYPE", "INQUIRY_TYPE" in page.inner_text("#chip-state"))
    check("session id stable across messages", page.inner_text("#chip-session") == sid)
    # 2. specific question gets specific answer
    send(page, "What documents might I need for a loan inquiry?")
    check("relevant (document-specific) answer", "proof of identity" in last_assistant(page).lower(), last_assistant(page)[:60])
    # 3. unclear answer -> clarification
    send(page, "Can you explain the next steps?")
    check("'next steps' question not treated as skip", "skip" not in last_assistant(page).lower())
    page.click("#btn-restart"); page.wait_for_function("document.querySelectorAll('.msg').length===1")
    send(page, "yes")
    send(page, "purple elephants")
    check("unclear answer -> CLARIFICATION tag", "CLARIFICATION" in page.inner_text("#chip-state") and page.locator(".tag.warn", has_text="clarification").count() >= 1)
    # 4. example prompt goes through the API
    page.click("#btn-restart"); page.wait_for_function("document.querySelectorAll('.msg').length===1")
    n = page.locator(".msg.assistant:not(.typing)").count()
    page.click("#examples button:has-text('speak to a human')")
    page.wait_for_function(f"document.querySelectorAll('.msg.assistant:not(.typing)').length > {n}")
    check("example prompt -> HUMAN_HANDOFF via backend", "HUMAN_HANDOFF" in page.inner_text("#chip-state") and "cannot transfer" in last_assistant(page))
    # 5. restart gives new session; end disables input
    old = page.inner_text("#chip-session"); page.click("#btn-restart"); page.wait_for_function("document.querySelectorAll('.msg').length===1")
    check("restart -> new session id", page.inner_text("#chip-session") != old)
    page.click("#btn-end"); page.wait_for_function("document.getElementById('composer-input').disabled")
    check("end -> composer disabled", "ended" in page.inner_text("#chip-state"))
    # 6. XSS: user text must not render as HTML
    page.click("#btn-restart"); page.wait_for_function("document.querySelectorAll('.msg').length===1")
    send(page, "<img src=x onerror=window.__xss=1> loan")
    check("user HTML is escaped", page.evaluate("window.__xss") is None and page.locator(".msg.user img").count() == 0)
    # 7. empty / whitespace send ignored
    c = page.locator(".msg").count(); page.fill("#composer-input", "   "); page.click("#btn-send")
    check("empty send ignored", page.locator(".msg").count() == c)

    # voice capability probes (real browser, real APIs)
    caps = page.evaluate("""() => ({sr: !!(window.SpeechRecognition||window.webkitSpeechRecognition),
        synth: !!window.speechSynthesis, voices: speechSynthesis.getVoices().length, secure: isSecureContext})""")
    print("INFO voice capabilities in this headless Chromium:", caps)
    check("voice chip reflects support honestly (never green before use)", "working" not in page.inner_text("#chip-voice"))
    if caps["sr"]:
        page.click("#btn-mic"); page.wait_for_timeout(9000)
        print("INFO mic click result -> banner:", page.inner_text("#banner")[:120] or "(none)", "| status:", page.inner_text("#voice-status"))
        check("mic failure surfaces a visible message, not silence", page.inner_text("#banner").strip() != "" or page.inner_text("#voice-status") == "Listening…")

    # responsive: no horizontal overflow
    for w, h in [(1280, 800), (820, 1000), (390, 800)]:
        page.set_viewport_size({"width": w, "height": h}); page.wait_for_timeout(150)
        ov = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(f"no horizontal overflow at {w}px", ov <= 0, f"overflow={ov}")
    page.screenshot(path="/tmp/ui_mobile.png"); page.set_viewport_size({"width": 1280, "height": 800}); page.screenshot(path="/tmp/ui_desktop.png")

    # backend down -> useful error
    page.route("**/api/conversations/*/messages", lambda r: r.abort())
    page.click("#btn-restart"); page.wait_for_function("document.querySelectorAll('.msg').length===1")
    send_n = page.locator(".msg").count(); page.fill("#composer-input", "hello loan"); page.press("#composer-input", "Enter")
    page.wait_for_selector(".msg.error")
    check("network failure shows readable error", "Cannot reach the backend" in page.inner_text(".msg.error"))
    b.close()

real_errors = [e for e in console_errors if "Failed to load resource" not in e and "net::ERR_FAILED" not in e]
print("INFO console errors:", console_errors or "none")
check("no unexpected browser console errors", not real_errors, "; ".join(real_errors)[:150])
print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
