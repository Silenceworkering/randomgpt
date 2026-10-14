"""Optional browser check: python tests/browser_smoke.py (running server required)."""

import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.getenv("VOLTRIX_TEST_URL", "http://127.0.0.1:8000")
with sync_playwright() as p:
    options = {"headless": True, "args": ["--no-sandbox"]}
    if Path("/usr/bin/chromium").exists():
        options["executable_path"] = "/usr/bin/chromium"
    browser = p.chromium.launch(**options)
    page = browser.new_page(
        viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE_URL)
    page.get_by_role("heading", name="ТВОЙ ПК. ТВОИ ПРАВИЛА.").wait_for()
    catalog = page.request.get(BASE_URL + "/api/catalog").json()
    assert catalog["metadata"]["price_kind"] == "retailer"
    assert not any("estimate_rub" in item for item in catalog["items"])
    page.locator(".hero-art img").wait_for()
    assert page.locator(".hero-art img").evaluate(
        "(img)=>img.complete&&img.naturalWidth>0"
    )
    page.screenshot(path=str(ROOT / "artifacts/home-desktop.png"), full_page=True)
    page.locator("#quick-form button").click()
    page.get_by_role("heading", name="Можно собирать.").wait_for(timeout=20000)
    page.locator("#use-result").click()
    page.locator("#summary-save").wait_for()
    assert "прошла проверки" in page.locator("#config-summary").inner_text()
    page.locator("#save-build").click()
    page.locator("#save-form input").fill("Браузерная проверка")
    page.locator("#save-form button").click()
    page.goto(BASE_URL + "/saved")
    page.get_by_role("heading", name="Браузерная проверка").wait_for()
    page.locator("[data-load]").click()
    page.locator("#summary-save").wait_for()
    price = page.locator("[data-price]").first
    price.fill("12345")
    price.dispatch_event("change")
    page.wait_for_timeout(100)
    assert "Есть введённые вами цены" in page.locator("#config-summary").inner_text()
    page.goto(BASE_URL + "/catalog")
    page.locator("[data-compare]").nth(0).click()
    page.locator("[data-compare]").nth(1).click()
    page.goto(BASE_URL + "/compare")
    page.locator("table").wait_for()
    assert page.locator("thead th").count() == 3
    page.locator("#only-different").check()
    assert page.locator("tr.same:visible").count() == 0
    page.locator("[data-detail]").first.click()
    assert page.locator("#modal a[target=_blank]").count() >= 4
    page.locator('[data-quote="0"]').fill("20000")
    page.locator('[data-quote="0"]').dispatch_event("change")
    page.locator('[data-quote="1"]').fill("18000")
    page.locator('[data-quote="1"]').dispatch_event("change")
    assert "18" in page.locator("#best-quote").inner_text()
    page.locator("#apply-quote").click()
    assert 18000 in page.evaluate(
        'Object.values(JSON.parse(localStorage.getItem("voltrix.draft.v1")).price_overrides)'
    )
    page.locator("#close-modal").click()
    page.goto(BASE_URL + "/saved")
    page.locator("[data-export]").wait_for()
    with page.expect_download() as download:
        page.locator("[data-export]").first.click()
    downloaded = download.value.path()
    page.locator("#import-file").set_input_files(
        {"name": "invalid.json", "mimeType": "application/json", "buffer": b"null"}
    )
    page.wait_for_function(
        "document.querySelector('#toast').textContent.includes('Неверный формат')"
    )
    page.locator("#import-file").set_input_files(str(downloaded))
    page.wait_for_function("document.querySelectorAll('.saved-card').length === 2")
    page.locator("[data-delete]").first.click()
    page.locator("#confirm-action").click()
    assert page.locator(".saved-card").count() == 1
    page.set_viewport_size({"width": 390, "height": 844})
    for route in [
        "/",
        "/smart",
        "/catalog",
        "/configurator",
        "/compare",
        "/saved",
        "/about",
    ]:
        page.goto(BASE_URL + route)
        page.locator("h1").wait_for()
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), (route + " overflows")
        if route == "/":
            page.screenshot(
                path=str(ROOT / "artifacts/home-mobile.png"), full_page=True
            )
        if route == "/configurator":
            page.screenshot(
                path=str(ROOT / "artifacts/configurator-mobile.png"), full_page=True
            )
    page.locator("#menu-button").click()
    page.locator('#mobile-nav a[href="/smart"]').click()
    page.locator("#smart-budget").fill("15000")
    page.locator("#smart-form button").click()
    page.locator("#smart-result .error-box").wait_for()
    assert "Минимальная" in page.locator("#smart-result").inner_text()
    page.goto(BASE_URL + "/configurator?parts=rtx4060")
    page.locator("#summary-save").wait_for()
    assert "Цена не подтверждена" in page.locator("#config-summary .total").inner_text()
    assert "Полная сумма не определена" in page.locator("#config-summary").inner_text()
    assert not errors, errors
    browser.close()
    print(
        "Browser smoke passed: desktop/mobile, selection, prices, saving, comparison, errors."
    )
