#!/usr/bin/env python3
"""
弹窗监控/嗅探脚本
在视频播放时运行，实时检测弹窗并自动抓取结构
找到弹窗后保存 HTML + 截图，然后自动点击关闭
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

CONFIG = Path(__file__).parent / "config.json"
OUT = Path(__file__).parent / "popup_sniff"
OUT.mkdir(exist_ok=True)

cfg = json.loads(CONFIG.read_text("utf-8"))


async def sniff_popups(page, label):
    """检测当前页面所有可见弹窗/modal/overlay"""
    found = await page.evaluate("""
        () => {
            var popups = [];
            var selectors = [
                '[class*="modal"]', '[class*="dialog"]', '[class*="popup"]',
                '[class*="overlay"]', '[class*="mask"]', '[class*="toast"]',
                '[class*="notice"]', '[class*="alert"]', '[class*="confirm"]',
                '[role="dialog"]', '.ant-modal', '.ant-popover',
                '[class*="read-dialog"]', '[class*="check-dialog"]',
                '[class*="detect"]', '[class*="tip-dialog"]',
            ];
            for (var i = 0; i < selectors.length; i++) {
                var els = document.querySelectorAll(selectors[i]);
                for (var j = 0; j < els.length; j++) {
                    var el = els[j];
                    var rect = el.getBoundingClientRect();
                    if (rect.width > 50 && rect.height > 50) {
                        var btns = el.querySelectorAll('button, [class*="btn"], span[class*="btn"]');
                        var buttonTexts = [];
                        for (var k = 0; k < btns.length; k++) {
                            var t = btns[k].textContent.trim();
                            if (t) buttonTexts.push(t.substring(0, 40));
                        }
                        popups.push({
                            selector: selectors[i],
                            class: (el.className || '').substring(0, 200),
                            text: (el.textContent || '').trim().substring(0, 300),
                            buttons: buttonTexts,
                            rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
                            html: el.outerHTML.substring(0, 1000),
                        });
                    }
                }
            }

            // 额外检查: 查找居中显示的遮罩层
            var allDivs = document.querySelectorAll('div');
            for (var i2 = 0; i2 < allDivs.length; i2++) {
                var d = allDivs[i2];
                var style = window.getComputedStyle(d);
                if (style.position === 'fixed' && style.zIndex > 100) {
                    var r2 = d.getBoundingClientRect();
                    if (r2.width > 100 && r2.height > 50) {
                        // 检查是否已经被上面的找到
                        var already = false;
                        for (var p = 0; p < popups.length; p++) {
                            if (d.outerHTML.indexOf(popups[p].html.substring(0, 50)) >= 0) {
                                already = true; break;
                            }
                        }
                        if (!already) {
                            var btns2 = d.querySelectorAll('button, [class*="btn"]');
                            var btnTxts2 = [];
                            for (var l = 0; l < btns2.length; l++) {
                                var t2 = btns2[l].textContent.trim();
                                if (t2) btnTxts2.push(t2.substring(0, 40));
                            }
                            popups.push({
                                selector: 'fixed-z-div',
                                class: (d.className || '').substring(0, 200),
                                text: (d.textContent || '').trim().substring(0, 300),
                                buttons: btnTxts2,
                                rect: { x: Math.round(r2.x), y: Math.round(r2.y), w: Math.round(r2.width), h: Math.round(r2.height) },
                                html: d.outerHTML.substring(0, 1000),
                                zIndex: style.zIndex,
                            });
                        }
                    }
                }
            }
            return popups;
        }
    """)
    return found


async def auto_click_popup(page):
    """尝试自动点击弹窗按钮"""
    keywords = [
        "已阅读", "继续", "确定", "知道了", "我知道了", "关闭", "跳过",
        "好的", "确认", "了解", "朕知道了", "没问题", "收到",
    ]
    for kw in keywords:
        try:
            el = page.get_by_text(kw, exact=False).first
            if await el.is_visible(timeout=300):
                await el.click()
                print(f"  [click] '{kw}'")
                return True
        except Exception:
            continue
    return False


async def main():
    print("=" * 56)
    print("  弹窗嗅探器")
    print("=" * 56)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.chrome = { runtime: {} };
        """)

        # 监听新页面（视频窗口）
        video_page = None

        async def on_page(p):
            nonlocal video_page
            video_page = p
            print(f"\n[new page] {p.url[:100]}")

        ctx.on("page", on_page)

        try:
            # —— 登录 ——
            print("\n[1] login...")
            await page.goto(cfg["login_url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)
            await page.locator("#login__password_userName").type(cfg["account"], delay=80)
            await page.locator("#login__password_password").type(cfg["password"], delay=80)
            await page.locator("button:has-text('登 录')").click()
            await page.wait_for_timeout(5000)
            print("  login done")

            # —— 任务页 ——
            print("\n[2] task page...")
            await page.goto(cfg["task_url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(5000)

            # —— 点日期 ——
            date_str = cfg.get("task_date", "2026-06-19")
            parts = date_str.split("-")
            chinese = f"{int(parts[1])}月{int(parts[2])}日" if len(parts) == 3 else date_str
            print(f"\n[3] click date: {chinese}")
            await page.get_by_text(chinese, exact=False).first.click()
            await page.wait_for_timeout(3000)

            # —— 点击第一个"学" ——
            print("\n[4] click '学'...")
            await page.locator(".btn-AoqsA:has-text('学')").first.click()
            await page.wait_for_timeout(5000)

            if not video_page:
                print("  [X] no new page opened")
                return

            await video_page.wait_for_load_state("domcontentloaded")
            await video_page.wait_for_timeout(3000)

            # —— 开始监控 ——
            print("\n[5] Sniffing popups... (press Ctrl+C to stop)")
            print("    Popups will be auto-detected, logged, and auto-clicked")
            print("    Data saved to: popup_sniff/")
            print()

            check_count = 0
            while True:
                check_count += 1

                # 检查主页面和视频页面
                for pg, pg_name in [(page, "main"), (video_page, "video")]:
                    if pg.is_closed():
                        continue
                    popups = await sniff_popups(pg, pg_name)
                    for popup in popups:
                        ts = datetime.now().strftime("%H%M%S")
                        print(f"\n{'!' * 40}")
                        print(f"[!] POPUP DETECTED on {pg_name} page!")
                        print(f"    class: {popup['class'][:150]}")
                        print(f"    text: {popup['text'][:200]}")
                        print(f"    buttons: {popup['buttons']}")
                        print(f"    zIndex: {popup.get('zIndex', 'N/A')}")
                        print(f"    html: {popup['html'][:500]}")

                        # 保存
                        fname = f"{ts}_{pg_name}_popup.json"
                        (OUT / fname).write_text(json.dumps(popup, ensure_ascii=False, indent=2))
                        await pg.screenshot(path=str(OUT / f"{ts}_{pg_name}_popup.png"))

                        # 自动点击
                        await auto_click_popup(pg)

                # 每2秒检查
                await asyncio.sleep(2)

                if check_count % 30 == 0:
                    print(f"  [heartbeat] {check_count * 2}s, still monitoring...")

        except KeyboardInterrupt:
            print("\n[!] stopped")
        finally:
            print(f"\n  output: {OUT}")
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
