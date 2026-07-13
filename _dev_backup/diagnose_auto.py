#!/usr/bin/env python3
"""
全自动诊断 — 自动登录、进课程、监测视频状态，输出分析报告
"""

import asyncio, json
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

CONFIG_PATH = Path(__file__).parent / "config.json"
OUT = Path(__file__).parent / "diagnosis_auto"
OUT.mkdir(exist_ok=True)

cfg = json.loads(CONFIG_PATH.read_text("utf-8"))


async def check_video_all_frames(page):
    """检查所有 frame 中的 video 状态"""
    results = []
    for frame in page.frames:
        try:
            v_data = await frame.evaluate("""() => {
                const vs = document.querySelectorAll('video');
                return Array.from(vs).map(v => ({
                    src: (v.src || v.currentSrc || '').substring(0, 120),
                    duration: v.duration,
                    currentTime: v.currentTime,
                    ended: v.ended,
                    paused: v.paused,
                    playbackRate: v.playbackRate,
                    readyState: v.readyState,
                    muted: v.muted,
                    width: v.videoWidth,
                    height: v.videoHeight,
                }));
            }""")
            for v in v_data:
                v["frame_url"] = frame.url[:100]
                v["frame_name"] = frame.name
            results.extend(v_data)
        except Exception:
            pass
    return results


async def main():
    print("=" * 60)
    print("  全自动诊断")
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
            # === 登录 ===
            print("\n[1] login...")
            await page.goto(cfg["login_url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            await page.locator("#login__password_userName").type(cfg["account"], delay=80)
            await page.locator("#login__password_password").type(cfg["password"], delay=80)
            await page.locator("button:has-text('登 录')").click()
            await page.wait_for_timeout(5000)
            print("  login done, url:", page.url[:80])

            # === 任务页 ===
            print("\n[2] task page...")
            await page.goto(cfg["task_url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(5000)
            await page.screenshot(path=str(OUT / "01_task.png"), full_page=True)

            # === 点日期 ===
            date_str = cfg.get("task_date", "2026-06-19")
            parts = date_str.split("-")
            chinese = f"{int(parts[1])}月{int(parts[2])}日" if len(parts) == 3 else date_str
            print(f"\n[3] click date: {chinese}")

            try:
                date_el = page.get_by_text(chinese, exact=False).first
                await date_el.click()
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"  error: {e}")

            await page.screenshot(path=str(OUT / "02_date_selected.png"), full_page=True)

            # === 找"学"按钮 ===
            print("\n[4] find '学' buttons...")
            study_btns = page.locator(".btn-AoqsA:has-text('学')")
            n = await study_btns.count()
            print(f"  found {n}")

            if n == 0:
                print("  [X] no buttons, exit")
                return

            # === 点击第一个"学" ===
            print("\n[5] click first '学'...")
            await study_btns.first.click()
            await page.wait_for_timeout(5000)

            # === 检查视频状态（初始） ===
            print("\n[6] check video state after click...")
            await page.screenshot(path=str(OUT / "03_after_click.png"), full_page=True)

            videos = await check_video_all_frames(page)
            print(f"  videos found: {len(videos)}")
            for v in videos:
                print(f"    frame={v.get('frame_name','main')[:30]}, src={v['src']}, "
                      f"duration={v['duration']}, current={v['currentTime']:.1f}, "
                      f"ended={v['ended']}, paused={v['paused']}, readyState={v['readyState']}")

            # 保存初始状态
            (OUT / "video_initial.json").write_text(json.dumps(videos, indent=2, ensure_ascii=False))

            # === 尝试播放视频 ===
            print("\n[7] try to start video...")

            # 方法1: JS play()
            for frame in page.frames:
                try:
                    result = await frame.evaluate("""() => {
                        const vs = document.querySelectorAll('video');
                        let msg = [];
                        vs.forEach((v, i) => {
                            v.muted = true;
                            v.playbackRate = 2.0;
                            const p = v.play();
                            msg.push('video[' + i + ']: play() returned, readyState=' + v.readyState);
                        });
                        return msg.join(', ') || 'no videos';
                    }""")
                    print(f"  play attempt: {result}")
                except Exception as e:
                    print(f"  play error: {e}")

            # === 等一会儿再检查 ===
            print("\n[8] wait 10s then check...")
            await page.wait_for_timeout(10000)
            await page.screenshot(path=str(OUT / "04_10s_later.png"), full_page=True)

            videos = await check_video_all_frames(page)
            print(f"  videos after 10s: {len(videos)}")
            for v in videos:
                print(f"    frame={v.get('frame_name','main')[:30]}, src={v['src']}, "
                      f"duration={v['duration']}, current={v['currentTime']:.1f}, "
                      f"ended={v['ended']}, paused={v['paused']}, readyState={v['readyState']}")

            (OUT / "video_10s.json").write_text(json.dumps(videos, indent=2, ensure_ascii=False))

            # === 再等30秒 ===
            print("\n[9] wait 30s more...")
            await page.wait_for_timeout(30000)
            await page.screenshot(path=str(OUT / "05_40s_later.png"), full_page=True)

            videos = await check_video_all_frames(page)
            print(f"  videos after 40s: {len(videos)}")
            for v in videos:
                print(f"    frame={v.get('frame_name','main')[:30]}, src={v['src']}, "
                      f"duration={v['duration']}, current={v['currentTime']:.1f}, "
                      f"ended={v['ended']}, paused={v['paused']}, readyState={v['readyState']}")

            (OUT / "video_40s.json").write_text(json.dumps(videos, indent=2, ensure_ascii=False))

            # === 检查页面文本（寻找完成标志） ===
            print("\n[10] page texts...")
            texts = await page.evaluate("""() => {
                const result = [];
                document.querySelectorAll('span, div, button, p').forEach(el => {
                    const t = (el.textContent || '').trim();
                    if (t.length > 2 && t.length < 100) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) result.push(t);
                    }
                });
                return result;
            }""")
            keywords = ["播放", "暂停", "倍速", "进度", "完成", "结束", "返回", "已阅读", "继续"]
            for kw in keywords:
                found = [t for t in texts if kw in t]
                if found:
                    print(f"  '{kw}': {found[:3]}")

            # === 导出完整 HTML ===
            html = await page.content()
            (OUT / "video_page.html").write_text(html, encoding="utf-8")
            print(f"\n  HTML saved: {len(html)} chars")

        except Exception as e:
            print(f"\n[X] error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print(f"\n  output: {OUT}")
            print("  closing browser in 5s...")
            await page.wait_for_timeout(5000)
            await browser.close()
            print("  done")


if __name__ == "__main__":
    asyncio.run(main())
