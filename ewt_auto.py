#!/usr/bin/env python3
"""
升学e网通 自动刷课 v3
- 每步先扫描页面结构
- 新窗口处理视频
- 2秒轮询弹窗 + 全DOM扫描
- 自动切换课程
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

CONFIG = Path(__file__).parent / "config.json"
SHOTS = Path(__file__).parent / "screenshots"

ARGS = None


def load_config():
    if not CONFIG.exists():
        print(f"[X] {CONFIG} not found"); sys.exit(1)
    return json.loads(CONFIG.read_text("utf-8"))


async def shot(page, name):
    if not ARGS.debug: return
    SHOTS.mkdir(exist_ok=True)
    await page.screenshot(path=str(SHOTS / f"{datetime.now().strftime('%H%M%S')}_{name}.png"), full_page=True)


# ── 页面扫描 ─────────────────────────────────────

async def scan_page(page, label=""):
    """扫描页面：URL、视频、iframe、弹窗、关键文本"""
    info = await page.evaluate("""
        () => {
            // videos
            var vs = document.querySelectorAll('video');
            var videos = [];
            for (var i = 0; i < vs.length; i++) {
                var v = vs[i];
                videos.push({ dur: v.duration, cur: v.currentTime, ended: v.ended, paused: v.paused, ready: v.readyState, src: (v.src||'').substring(0,80) });
            }
            // popups
            var popups = [];
            var all = document.querySelectorAll('div, section, aside');
            for (var i = 0; i < all.length; i++) {
                var el = all[i];
                var s = window.getComputedStyle(el);
                if (s.position === 'fixed' && parseInt(s.zIndex) > 50) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 80 && r.height > 40) {
                        var btns = el.querySelectorAll('button, [class*="btn"]');
                        var btnTxt = [];
                        for (var j = 0; j < btns.length; j++) { var t = btns[j].textContent.trim(); if (t) btnTxt.push(t.substring(0,30)); }
                        popups.push({ cls: (el.className||'').substring(0,120), txt: (el.textContent||'').trim().substring(0,200), btns: btnTxt, z: parseInt(s.zIndex) });
                    }
                }
            }
            return { url: location.href, videos: videos, popups: popups };
        }
    """)
    if label:
        print(f"  [{label}] url={info['url'][:90]}")
    if info['videos']:
        print(f"  [{label}] videos: {len(info['videos'])}")
        for v in info['videos']:
            print(f"    dur={v['dur']:.0f} cur={v['cur']:.0f} ended={v['ended']} paused={v['paused']} ready={v['ready']}")
    if info['popups']:
        print(f"  [{label}] POPUPS FOUND: {len(info['popups'])}")
        for p in info['popups']:
            print(f"    z={p['z']} cls={p['cls'][:80]}")
            print(f"    btns={p['btns']}")
            print(f"    txt={p['txt'][:120]}")
    return info


# ── 弹窗处理 ─────────────────────────────────────

async def dismiss_all_popups(page):
    """扫描弹窗并点击 — 排除完成弹窗(.progress-tip-bg-x7CPv)"""
    handled = False

    # 0. 直接通过 known class 点击（认真度检测弹窗）
    for cls in ["btn-DOCWn"]:
        try:
            el = page.locator(f".{cls}").first
            if await el.is_visible(timeout=500):
                await el.click()
                print(f"  [popup] clicked .{cls}")
                handled = True
                await page.wait_for_timeout(1000)
        except Exception:
            pass

    # 1. 文本匹配
    keywords = [
        "点击通过检查", "继续播放", "继续学习", "继续观看", "继续",
        "已阅读", "确定", "知道了", "我知道了", "关闭", "跳过",
        "好的", "确认", "了解", "没问题", "收到", "是的", "OK",
    ]
    for kw in keywords:
        try:
            els = page.get_by_text(kw, exact=False)
            cnt = await els.count()
            for i in range(cnt):
                try:
                    el = els.nth(i)
                    if await el.is_visible(timeout=300):
                        # 跳过完成弹窗里的按钮
                        parent = await el.evaluate("el => { var p=el.closest('.progress-tip-bg-x7CPv'); return p ? true : false; }")
                        if parent:
                            continue
                        await el.click()
                        print(f"  [popup] clicked '{kw}'")
                        handled = True
                        await page.wait_for_timeout(500)
                except Exception:
                    continue
        except Exception:
            continue

    # 2. DOM 扫描固定层
    try:
        popups = await page.evaluate("""
            () => {
                var found = [];
                var all = document.querySelectorAll('div, section');
                for (var i = 0; i < all.length; i++) {
                    var el = all[i];
                    var s = window.getComputedStyle(el);
                    if (s.position === 'fixed' && parseInt(s.zIndex) > 100 && s.display !== 'none' && s.visibility !== 'hidden') {
                        var r = el.getBoundingClientRect();
                        if (r.width > 80 && r.height > 40 && r.top < window.innerHeight && r.left < window.innerWidth) {
                            var btns = el.querySelectorAll('button, [class*="btn"], .ant-btn');
                            for (var j = 0; j < btns.length; j++) {
                                found.push({ html: btns[j].outerHTML.substring(0,300) });
                            }
                        }
                    }
                }
                return found;
            }
        """)
        for p in popups:
            try:
                # 通过 outerHTML 定位按钮
                await page.evaluate(f"""
                    () => {{
                        var btns = document.querySelectorAll('button, [class*="btn"], .ant-btn');
                        for (var i = 0; i < btns.length; i++) {{
                            if (btns[i].outerHTML.indexOf({json.dumps(p['html'][:80])}) >= 0) {{
                                btns[i].click();
                                return true;
                            }}
                        }}
                    }}
                """)
                handled = True
            except Exception:
                pass
    except Exception:
        pass

    return handled


# ── 视频等待（含弹窗监控） ────────────────────────

async def wait_for_video(page, timeout=3600):
    """等待视频播完 — 检测完成弹窗：太酷了 + 课后习题/再次观看"""
    print("  [wait] watching...")
    elapsed = 0
    interval = 2

    while elapsed < timeout:
        await page.wait_for_timeout(interval * 1000)
        elapsed += interval

        # 1. 弹窗检查（认真度检测等）
        await dismiss_all_popups(page)

        # 2. 页面关闭
        if page.is_closed():
            print("  [wait] page auto-closed")
            return True

        # 3. 完成弹窗检测（真实 DOM: .progress-tip-bg-x7CPv / "太酷啦"）
        try:
            found = await page.evaluate("""
                () => {
                    var body = document.body.innerText;
                    if (body.indexOf('太酷啦')>=0) return 'taikula';
                    if (body.indexOf('温故知新')>=0) return 'wengu';
                    // 直接查弹窗容器
                    var tip = document.querySelector('.progress-tip-bg-x7CPv');
                    if (tip && tip.getBoundingClientRect().height > 0) return 'progress_tip';
                    return '';
                }
            """)
            if found:
                print(f"  [wait] completion: '{found}'")
                await page.wait_for_timeout(2000)
                return True
        except Exception:
            pass

        # 4. video.ended 保底
        try:
            status = await page.evaluate("""
                () => {
                    var vs = document.querySelectorAll('video');
                    for (var i = 0; i < vs.length; i++) {
                        if (vs[i].ended && vs[i].duration > 0) return 'ended';
                        if (vs[i].duration > 0 && !vs[i].paused) return 'playing';
                    }
                    return 'waiting';
                }
            """)
            if status == "ended":
                print("  [wait] video.ended=true")
                await page.wait_for_timeout(3000)
                return True
            if status == "playing" and elapsed % 30 == 0:
                print(f"  [wait] playing... ({elapsed}s)")
        except Exception:
            pass

    print(f"  [X] timeout {timeout}s")
    return False


# ── 核心流程 ─────────────────────────────────────

async def login(page, cfg):
    print("\n[1] Login...")
    await page.goto(cfg["login_url"], wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(3000)
    await scan_page(page, "login")

    await page.locator("#login__password_userName").fill("")
    await page.locator("#login__password_userName").type(cfg["account"], delay=80)
    await page.locator("#login__password_password").fill("")
    await page.locator("#login__password_password").type(cfg["password"], delay=80)

    try:
        cb = page.locator("#login__password_autoLogin")
        if not await cb.is_checked(): await cb.check()
    except Exception: pass

    await page.locator("button:has-text('登 录')").click()
    await page.wait_for_timeout(5000)
    print("  login done")
    return True


async def goto_task_and_date(page, cfg):
    print("\n[2] Task page...")
    await page.goto(cfg["task_url"], wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(5000)
    await scan_page(page, "task")
    await shot(page, "task")

    date_str = ARGS.date or cfg.get("task_date", "")
    parts = date_str.split("-")
    chinese = f"{int(parts[1])}月{int(parts[2])}日" if len(parts) == 3 else date_str

    print(f"\n[3] Date: {chinese}")
    try:
        await page.get_by_text(chinese, exact=False).first.click()
        await page.wait_for_timeout(3000)
        await shot(page, "date_ok")
        return True
    except Exception:
        print("  [X] date click failed")
        await shot(page, "date_err")
        return False


async def scan_courses(page):
    """扫描课程按钮，返回按钮列表"""
    print("\n[4] Scan courses...")
    await page.evaluate("window.scrollTo(0,0)")
    await page.wait_for_timeout(500)
    for _ in range(5):
        await page.evaluate("window.scrollBy(0,500)")
        await page.wait_for_timeout(500)

    await page.evaluate("window.scrollTo(0,0)")
    await page.wait_for_timeout(1000)
    await shot(page, "courses")

    btns = await page.evaluate("""
        () => {
            var all = document.querySelectorAll('.btn-AoqsA');
            var result = [];
            for (var i = 0; i < all.length; i++) {
                var b = all[i];
                var t = b.textContent.trim();
                // 必须以"学"开头（排除"已学完"）
                if (t.indexOf('学') === 0) {
                    var item = b.closest('.taskItem-ZeyMG') || b.closest('li');
                    var title = '';
                    if (item) {
                        var tEl = item.querySelector('[class*="col2"], [class*="title"]');
                        if (tEl) title = tEl.textContent.trim().substring(0, 50);
                    }
                    result.push({ idx: result.length, txt: t.substring(0,15), title: title, finish: b.getAttribute('data-finish') || '' });
                }
            }
            return result;
        }
    """)
    print(f"  {len(btns)} course(s):")
    for b in btns:
        print(f"    [{b['idx']}] {b['txt']:10s} | {b['title']}")
    return btns


async def process_one_course(page, context, cfg, btn_idx, idx_idx):
    """按索引点击第 btn_idx 个'学'按钮，播放视频，等结束"""
    speed = ARGS.speed or cfg.get("video_speed", 2.0)

    # 根据索引定位按钮
    await page.wait_for_timeout(500)
    all_btns = page.locator(".btn-AoqsA")
    cnt = await all_btns.count()
    if btn_idx >= cnt:
        print(f"  [X] btn_idx={btn_idx} >= total={cnt}, rescannning...")
        return False, "stale_idx"

    # 验证这个按钮确实是"学"（以防顺序变了）
    txt = await all_btns.nth(btn_idx).text_content()
    txt = txt.strip() if txt else ""
    if not txt.startswith("学") or "已学完" in txt:
        # 按钮变了，可能是已经完成了
        print(f"  [skip] btn[{btn_idx}] is now '{txt}', already done")
        return False, "already_done"

    btn = all_btns.nth(btn_idx)

    # 取课程标题
    try:
        task_item = btn.locator("xpath=ancestor::li[contains(@class,'taskItem')]")
        title_el = task_item.locator("[class*='col2']").first
        course_title = await title_el.text_content() if await title_el.count() > 0 else "unknown"
        print(f"  [course] {course_title.strip()[:50]}")
    except Exception:
        print(f"  [course] btn[{btn_idx}]")

    # 等新窗口
    new_page = None
    evt = asyncio.Event()
    async def on_page(p):
        nonlocal new_page; new_page = p; evt.set()
    context.on("page", on_page)

    try:
        await btn.scroll_into_view_if_needed()
        await btn.click(force=True)

        try:
            await asyncio.wait_for(evt.wait(), timeout=10)
        except asyncio.TimeoutError:
            print("  [X] no new window")
            return False, "no_window"

        print(f"  [video] {new_page.url[:100]}")
        await new_page.wait_for_load_state("domcontentloaded")
        await new_page.wait_for_timeout(4000)
        await scan_page(new_page, "video")
        await shot(new_page, "video")

        # 设置倍速
        await new_page.evaluate("(s) => { var vs=document.querySelectorAll('video'); for(var i=0;i<vs.length;i++)vs[i].playbackRate=s; }", speed)
        print(f"  [speed] {speed}x")

        # 也检查倍速按钮
        try:
            el = new_page.get_by_text("倍速", exact=False).first
            if await el.is_visible(timeout=1500):
                await el.click()
                await new_page.wait_for_timeout(300)
                opt = new_page.get_by_text(f"{speed}x", exact=False).first
                if await opt.is_visible(timeout=1000):
                    await opt.click()
        except Exception: pass

        await shot(new_page, "playing")

        # 等视频播完
        await wait_for_video(new_page)

        # 视频播完后处理完成弹窗
        await page.wait_for_timeout(1000)
        await dismiss_all_popups(new_page)
        # 点掉完成弹窗（点"重新观看"或直接关页面）
        try:
            for cls in ["progress-action-ghost-GXTxa"]:
                el = new_page.locator(f".{cls}").first
                if await el.is_visible(timeout=500):
                    await el.click()
                    await new_page.wait_for_timeout(1000)
                    break
        except Exception: pass

        # 关闭视频页
        await page.wait_for_timeout(1000)
        if not new_page.is_closed():
            try:
                await new_page.close()
            except Exception: pass

        return True, "ok"
    finally:
        context.remove_listener("page", on_page)
        if new_page and not new_page.is_closed():
            try: await new_page.close()
            except Exception: pass


# ── 主入口 ───────────────────────────────────────

async def main():
    global ARGS
    ARGS = parse_args()
    cfg = load_config()

    if ARGS.headless: cfg["headless"] = True
    if ARGS.show: cfg["headless"] = False
    if ARGS.speed: cfg["video_speed"] = ARGS.speed
    if ARGS.date: cfg["task_date"] = ARGS.date

    print("=" * 56)
    print("  升学e网通 自动刷课 v3")
    print(f"  date={ARGS.date or cfg.get('task_date')}, speed={ARGS.speed or cfg.get('video_speed',2.0)}x")
    print("=" * 56)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=cfg.get("headless", False), channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>false});window.chrome={runtime:{}};")

        try:
            # 1-3. 登录 + 任务页 + 选日期
            await login(page, cfg)
            if not await goto_task_and_date(page, cfg): return

            # 4. 扫描课程
            courses = await scan_courses(page)
            if not courses:
                print("[done] no courses"); return

            # 5. 循环学习
            # 初始扫描拿到所有"学"按钮，按索引逐个点击
            await scan_courses(page)  # 打印课程列表
            all_btns = page.locator(".btn-AoqsA")
            total = await all_btns.count()
            study_indices = []
            for i in range(total):
                txt = await all_btns.nth(i).text_content()
                if txt and txt.strip().startswith("学"):
                    study_indices.append(i)
            total_study = len(study_indices)
            print(f"\n{'='*40}\n  {total_study} uncompleted course(s)\n{'='*40}")

            if total_study == 0:
                print("[done] no courses"); return

            for idx_idx, btn_idx in enumerate(study_indices):
                print(f"\n[course {idx_idx+1}/{total_study}]")
                ok, reason = await process_one_course(page, context, cfg, btn_idx, idx_idx)

                if not ok:
                    if reason == "all_done":
                        break
                    print(f"  [skip] {reason}")
                    # 可能是索引变了，重扫一次
                    continue

                # 刷新页面让课程进度更新
                await page.wait_for_timeout(2000)
                await dismiss_all_popups(page)
                await page.goto(cfg["task_url"], wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(3000)
                # 重新点日期
                ds = ARGS.date or cfg.get("task_date", "")
                dps = ds.split("-")
                ch = f"{int(dps[1])}月{int(dps[2])}日" if len(dps) == 3 else ds
                try:
                    await page.get_by_text(ch, exact=False).first.click()
                    await page.wait_for_timeout(2000)
                except Exception: pass

                print(f"  [done] {idx_idx+1}/{total_study}")

            print("\n[DONE] all courses completed!")

        except KeyboardInterrupt:
            print("\n[!] stopped")
        except Exception as e:
            print(f"[X] {e}")
            import traceback; traceback.print_exc()
            await shot(page, "crash")
        finally:
            await browser.close()


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--date"); p.add_argument("--headless", action="store_true", default=None)
    p.add_argument("--show", action="store_true", default=None)
    p.add_argument("--debug", action="store_true"); p.add_argument("--speed", type=float)
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main())
