#!/usr/bin/env python3
"""
诊断 v3 — 监控点击"学"后的所有事件：URL变化、新窗口、对话框、网络请求
"""

import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright

CONFIG = Path(__file__).parent / "config.json"
OUT = Path(__file__).parent / "diagnosis_v3"
OUT.mkdir(exist_ok=True)
cfg = json.loads(CONFIG.read_text("utf-8"))


async def main():
    print("=" * 56)
    print("  诊断 v3")
    print("=" * 56)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()

        # 监听新页面/弹窗
        new_pages = []
        ctx.on("page", lambda p: new_pages.append(p))

        # 监听对话框
        dialogs = []
        page.on("dialog", lambda d: dialogs.append(f"dialog: {d.type} {d.message}"))

        # 监听控制台错误
        console_errors = []
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error","warning") else None)

        # 网络请求监控
        video_urls = []
        def on_response(resp):
            url = resp.url.lower()
            ct = resp.headers.get("content-type", "")
            if any(x in url for x in [".mp4", ".m3u8", ".flv", ".ts", "video", "player", "vod"]):
                video_urls.append(f"{resp.status} {resp.url[:150]}")
            if "video" in ct or "mpeg" in ct:
                video_urls.append(f"{resp.status} {resp.url[:150]} ({ct})")

        page.on("response", on_response)

        try:
            # === 登录 ===
            print("\n[1] login...")
            await page.goto(cfg["login_url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)
            await page.locator("#login__password_userName").type(cfg["account"], delay=80)
            await page.locator("#login__password_password").type(cfg["password"], delay=80)
            await page.locator("button:has-text('登 录')").click()
            await page.wait_for_timeout(5000)
            print(f"  url after login: {page.url[:100]}")

            # === 任务页 ===
            print("\n[2] task page...")
            await page.goto(cfg["task_url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(5000)

            # === 点日期 ===
            date_str = cfg.get("task_date", "2026-06-19")
            parts = date_str.split("-")
            chinese = f"{int(parts[1])}月{int(parts[2])}日" if len(parts) == 3 else date_str
            print(f"\n[3] click date: {chinese}")
            try:
                await page.get_by_text(chinese, exact=False).first.click()
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"  error: {e}")

            # === 找"学"按钮并检查状态 ===
            study_btns = page.locator(".btn-AoqsA:has-text('学')")
            n = await study_btns.count()
            print(f"\n[4] '学' buttons: {n}")

            if n == 0:
                print("  [X] no buttons")
                return

            # 检查第一个"学"按钮的详细信息
            first = study_btns.first
            info = await first.evaluate("""el => ({
                tag: el.tagName,
                text: el.textContent,
                class: el.className,
                disabled: el.disabled || el.getAttribute('disabled'),
                parent_class: el.parentElement ? el.parentElement.className : '',
                parent_parent_class: el.parentElement?.parentElement?.className || '',
                cursor: window.getComputedStyle(el).cursor,
                pointerEvents: window.getComputedStyle(el).pointerEvents,
                opacity: window.getComputedStyle(el).opacity,
                rect: el.getBoundingClientRect(),
                html: el.outerHTML.substring(0, 300),
            })""")
            print(f"  button info: tag={info['tag']}, disabled={info['disabled']}, "
                  f"cursor={info['cursor']}, opacity={info['opacity']}, "
                  f"pointerEvents={info['pointerEvents']}")
            print(f"  parent: {info['parent_class'][:80]}")
            print(f"  HTML: {info['html']}")

            # === 点击"学" ===
            print(f"\n[5] click '学'... url before: {page.url[:100]}")
            url_before = page.url

            # 尝试多种点击方式
            try:
                await first.click(force=True)
            except Exception as e:
                print(f"  click error: {e}")

            await page.wait_for_timeout(5000)
            url_after = page.url
            print(f"  url after click: {url_after[:100]}")
            print(f"  url changed: {url_before != url_after}")
            print(f"  new pages opened: {len(new_pages)}")
            print(f"  dialogs: {dialogs}")
            print(f"  console errors: {console_errors[-5:]}")
            print(f"  video requests: {video_urls}")

            # === 检查页面状态 ===
            # 检查是否出了弹窗/modal
            modal_info = await page.evaluate("""() => {
                const modals = [];
                document.querySelectorAll('[class*="modal"], [class*="dialog"], [class*="popup"], [class*="overlay"], [class*="mask"], [role="dialog"]').forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        modals.push({
                            class: (el.className || '').substring(0, 120),
                            text: (el.textContent || '').trim().substring(0, 150),
                            rect: {x: r.x, y: r.y, w: r.width, h: r.height}
                        });
                    }
                });
                return modals;
            }""")
            print(f"\n  visible modals/dialogs: {len(modal_info)}")
            for m in modal_info[:5]:
                print(f"    class={m['class'][:80]}, text={m['text'][:80]}")

            # 检查所有 iframe
            frames_info = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('iframe')).map(f => ({
                    src: f.src.substring(0, 150),
                    class: f.className.substring(0, 80),
                    rect: f.getBoundingClientRect(),
                }));
            }""")
            print(f"\n  iframes: {len(frames_info)}")
            for f in frames_info:
                print(f"    src={f['src'][:100]}, rect={f['rect']['x']},{f['rect']['y']} {f['rect']['width']}x{f['rect']['height']}")

            # 截图
            await page.screenshot(path=str(OUT / "after_click.png"), full_page=True)

            # 检查是否有课程详情页打开
            current_html_snippet = await page.evaluate("""() => {
                const body = document.body.innerText || '';
                return body.substring(0, 2000);
            }""")
            print(f"\n  page text preview:\n{current_html_snippet[:500]}")

        except Exception as e:
            print(f"\n[X] error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print(f"\n  output: {OUT}")
            await page.wait_for_timeout(3000)
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
