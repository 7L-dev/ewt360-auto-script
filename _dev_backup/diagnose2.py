#!/usr/bin/env python3
"""
诊断 v2 — 重点分析课程视频页面结构
"""

import asyncio, json
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

CONFIG_PATH = Path(__file__).parent / "config.json"
OUT = Path(__file__).parent / "diagnosis2"
OUT.mkdir(exist_ok=True)

cfg = json.loads(CONFIG_PATH.read_text("utf-8"))


async def snapshot(page, label):
    """保存当前页面的截图、HTML、关键元素"""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  URL: {page.url}")

    # 截图
    await page.screenshot(path=str(OUT / f"{label}.png"), full_page=True)

    # 保存 HTML
    html = await page.content()
    (OUT / f"{label}.html").write_text(html, encoding="utf-8")
    print(f"  html: {len(html)} chars")

    # 收集所有 iframe 和它们的 video
    info = await page.evaluate("""() => {
        const data = {
            videos_in_main: [],
            iframes: [],
            all_visible_text: [],
        };

        // 主页面 video
        document.querySelectorAll('video').forEach((v, i) => {
            data.videos_in_main.push({
                index: i,
                src: v.src || v.currentSrc || '',
                duration: v.duration,
                currentTime: v.currentTime,
                ended: v.ended,
                paused: v.paused,
                playbackRate: v.playbackRate,
                readyState: v.readyState,
                rect: {
                    x: v.getBoundingClientRect().x,
                    y: v.getBoundingClientRect().y,
                    w: v.getBoundingClientRect().width,
                    h: v.getBoundingClientRect().height,
                }
            });
        });

        // iframe 信息
        document.querySelectorAll('iframe').forEach((f, i) => {
            data.iframes.push({
                index: i,
                src: f.src,
                name: f.name,
                id: f.id,
                class: f.className.substring(0, 100),
                rect: {
                    x: f.getBoundingClientRect().x,
                    y: f.getBoundingClientRect().y,
                    w: f.getBoundingClientRect().width,
                    h: f.getBoundingClientRect().height,
                }
            });
        });

        // 页面可见关键文本
        const texts = document.querySelectorAll('span, div, button, p, h1, h2, h3, h4, h5');
        texts.forEach(el => {
            const txt = (el.textContent || '').trim();
            if (txt.length > 2 && txt.length < 80) {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    data.all_visible_text.push({
                        text: txt.substring(0, 80),
                        tag: el.tagName,
                        class: (el.className || '').toString().substring(0, 100),
                    });
                }
            }
        });

        return data;
    }""")

    # 保存详细数据
    (OUT / f"{label}_detail.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 输出摘要
    print(f"  videos in main page: {len(info['videos_in_main'])}")
    for v in info["videos_in_main"]:
        print(f"    video[{v['index']}]: src={v['src'][:80]}, duration={v['duration']}, "
              f"current={v['currentTime']}, ended={v['ended']}, paused={v['paused']}, "
              f"readyState={v['readyState']}, rect={v['rect']['w']}x{v['rect']['h']}")

    print(f"  iframes: {len(info['iframes'])}")
    for f in info["iframes"]:
        print(f"    iframe[{f['index']}]: src={f['src'][:80]}, rect={f['rect']['w']}x{f['rect']['h']}")

    # 打印关键文本
    keywords = ["播放", "暂停", "倍速", "进度", "完成", "结束", "返回", "视频", "已阅读"]
    for kw in keywords:
        matches = [t for t in info["all_visible_text"] if kw in t["text"]]
        if matches:
            print(f"  texts with '{kw}':")
            for m in matches[:5]:
                print(f"    [{m['tag']}] \"{m['text'][:60]}\" class=\"{m['class'][:60]}\"")

    return info


async def main():
    print("=" * 60)
    print("  诊断 v2 — 课程视频页面分析")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149.0.0.0 Safari/537.36",
        )
        page = await ctx.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.chrome = { runtime: {} };
        """)

        try:
            # —— 登录 ——
            print("\n[1] 登录...")
            await page.goto(cfg["login_url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            await page.locator("#login__password_userName").type(cfg["account"], delay=80)
            await page.locator("#login__password_password").type(cfg["password"], delay=80)
            await page.locator("button:has-text('登 录')").click()
            await page.wait_for_timeout(5000)
            print("  登录完成")

            # —— 任务页面 ——
            print("\n[2] 进入任务页...")
            await page.goto(cfg["task_url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(5000)
            await snapshot(page, "task_page")

            # —— 点日期 ——
            date_str = cfg.get("task_date", "2026-06-19")
            parts = date_str.split("-")
            chinese = f"{int(parts[1])}月{int(parts[2])}日" if len(parts) == 3 else date_str
            print(f"\n[3] 点击日期: {chinese}")

            try:
                date_el = page.get_by_text(chinese, exact=False).first
                await date_el.click()
                await page.wait_for_timeout(3000)
                await snapshot(page, "date_selected")
            except Exception as e:
                print(f"  error: {e}")

            # —— 找第一个"学"按钮 ——
            print("\n[4] 找第一个'学'按钮...")
            study_btns = page.locator(".btn-AoqsA:has-text('学')")
            n = await study_btns.count()
            print(f"  找到 {n} 个'学'按钮")

            if n == 0:
                print("  [X] 没有'学'按钮, 退出")
                return

            # —— 点击第一个"学" ——
            print("\n[5] 点击第一个'学'按钮...")
            await study_btns.first.click()
            await page.wait_for_timeout(5000)

            # —— 核心: 分析视频页面 ——
            print("\n[6] === 视频页面分析 ===")
            await snapshot(page, "video_page")

            # 也检查 iframe 里的 video
            for frame in page.frames:
                if frame != page.main_frame:
                    print(f"\n  checking iframe: {frame.url[:100]}")
                    try:
                        v_info = await frame.evaluate("""() => {
                            const vs = document.querySelectorAll('video');
                            return Array.from(vs).map(v => ({
                                src: v.src, duration: v.duration,
                                currentTime: v.currentTime, ended: v.ended,
                                paused: v.paused, readyState: v.readyState,
                            }));
                        }""")
                        print(f"  videos in iframe: {len(v_info)}")
                        for v in v_info:
                            print(f"    src={v['src'][:80]}, duration={v['duration']}, "
                                  f"current={v['currentTime']}, ended={v['ended']}, "
                                  f"paused={v['paused']}, readyState={v['readyState']}")
                    except Exception as e:
                        print(f"  iframe eval error: {e}")

            # ——— 交互模式 ———
            print("\n" + "=" * 60)
            print("  浏览器保持打开, 你可以:")
            print("  - 手动点视频播放,让它播一会")
            print("  - 然后按 Enter 重新分析当前页面")
            print("  - 输入 q 退出")

            while True:
                cmd = input("> ").strip()
                if cmd.lower() == "q":
                    break
                elif cmd == "":
                    ts = datetime.now().strftime("%H%M%S")
                    info = await snapshot(page, f"manual_{ts}")

                    # 检查所有 frame
                    for frame in page.frames:
                        if frame != page.main_frame:
                            print(f"\n  iframe: {frame.url[:100]}")
                            try:
                                v_info = await frame.evaluate("""() => {
                                    const vs = document.querySelectorAll('video');
                                    return Array.from(vs).map(v => ({
                                        src: v.src, duration: v.duration,
                                        currentTime: v.currentTime, ended: v.ended,
                                        paused: v.paused, playbackRate: v.playbackRate,
                                        readyState: v.readyState,
                                    }));
                                }""")
                                for v in v_info:
                                    print(f"    video: src={v['src'][:80]}, duration={v['duration']}, "
                                          f"current={v['currentTime']}, ended={v['ended']}, "
                                          f"paused={v['paused']}, rate={v['playbackRate']}, "
                                          f"readyState={v['readyState']}")
                            except Exception as e:
                                print(f"    error: {e}")

        except KeyboardInterrupt:
            print("\n[X] interrupted")
        except Exception as e:
            print(f"\n[X] error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print(f"\n  输出目录: {OUT}")
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
