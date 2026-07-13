#!/usr/bin/env python3
"""
轻量飞行记录器 — 不干扰播放，纯观察模式
"""

import asyncio, json
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

CONFIG = Path(__file__).parent / "config.json"
OUT = Path(__file__).parent / "flight_record"
OUT.mkdir(exist_ok=True)
cfg = json.loads(CONFIG.read_text("utf-8"))

seq = [0]

async def analyze(page, label):
    """只在关键时刻做完整DOM分析"""
    seq[0] += 1
    n = f"{seq[0]:02d}"

    # 截图
    await page.screenshot(path=str(OUT / f"{n}_{label}.png"), full_page=True)

    # DOM分析
    info = await page.evaluate("""
        () => {
            var vs = document.querySelectorAll('video');
            var videos = [];
            for (var i = 0; i < vs.length; i++) {
                var v = vs[i];
                videos.push({src:(v.src||'').substring(0,100),dur:v.duration,cur:v.currentTime,ended:v.ended,paused:v.paused,rate:v.playbackRate,ready:v.readyState});
            }
            var btns = [];
            document.querySelectorAll('button,[class*="btn"],[role="button"]').forEach(function(b){
                var t=(b.textContent||'').trim(),r=b.getBoundingClientRect();
                if(t&&r.width>0)btns.push({t:t.substring(0,40),c:(b.className||'').substring(0,80)});
            });
            // popups
            var popups=[];
            document.querySelectorAll('div,section').forEach(function(d){
                var s=window.getComputedStyle(d);
                if(s.position==='fixed'&&parseInt(s.zIndex)>50){
                    var r=d.getBoundingClientRect();
                    if(r.width>80&&r.height>40){
                        var bts=[];d.querySelectorAll('button,[class*=btn]').forEach(function(x){var tt=x.textContent.trim();if(tt)bts.push(tt.substring(0,30));});
                        popups.push({c:(d.className||'').substring(0,120),t:(d.textContent||'').trim().substring(0,150),b:bts,z:parseInt(s.zIndex)});
                    }
                }
            });
            // taskItems
            var items=[];
            document.querySelectorAll('.taskItem-ZeyMG,li[class*=task]').forEach(function(x){items.push({c:(x.className||'').substring(0,80),t:(x.textContent||'').trim().substring(0,150)});});
            return {url:location.href,videos:videos,btns:btns.slice(0,40),popups:popups,items:items};
        }
    """)
    (OUT / f"{n}_{label}.json").write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding="utf-8")

    print(f"\n{'='*40}")
    print(f"  [{n}] {label}")
    print(f"  url={info['url'][:90]}")
    print(f"  videos: {len(info['videos'])}")
    for v in info['videos']:
        print(f"    dur={v['dur']:.0f} cur={v['cur']:.0f} ended={v['ended']} paused={v['paused']} rate={v['rate']}")
    print(f"  popups: {len(info['popups'])}")
    for p in info['popups']:
        print(f"    z={p['z']} btns={p['b']}")
        print(f"    txt: {p['t'][:100]}")
    print(f"  items: {len(info['items'])}")
    for it in info['items']:
        print(f"    {it['t'][:100]}")


async def main():
    print("=" * 56)
    print("  轻量飞行记录器")
    print("=" * 56)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False,channel="chrome",args=["--disable-blink-features=AutomationControlled","--no-sandbox"])
        ctx = await browser.new_context(viewport={"width":1920,"height":1080})
        page = await ctx.new_page()
        await page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>false});window.chrome={runtime:{}};")

        video_page = None
        async def on_page(p):
            nonlocal video_page; video_page = p
        ctx.on("page", on_page)

        try:
            # -- 登录 --
            print("\n[1] Login...")
            await page.goto(cfg["login_url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)
            await page.locator("#login__password_userName").type(cfg["account"], delay=80)
            await page.locator("#login__password_password").type(cfg["password"], delay=80)
            await page.locator("button:has-text('登 录')").click()
            await page.wait_for_timeout(5000)

            # -- 任务页 + 日期 --
            await page.goto(cfg["task_url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(5000)
            date_str = cfg.get("task_date","2026-06-19")
            parts = date_str.split("-")
            chinese = f"{int(parts[1])}月{int(parts[2])}日" if len(parts)==3 else date_str
            await page.get_by_text(chinese,exact=False).first.click()
            await page.wait_for_timeout(3000)

            # -- 分析课程列表初始状态 --
            await analyze(page, "01_course_list_before")

            # -- 点击学 --
            print("\n[2] Click '学'...")
            await page.locator(".btn-AoqsA:has-text('学')").first.click()
            await page.wait_for_timeout(5000)
            if not video_page:
                print("[X] no new page"); return
            await video_page.wait_for_load_state("domcontentloaded")
            await video_page.wait_for_timeout(3000)

            # -- 分析视频页初始 --
            await analyze(video_page, "02_video_opened")

            # -- 设2x倍速 --
            await video_page.evaluate("()=>{var vs=document.querySelectorAll('video');for(var i=0;i<vs.length;i++)vs[i].playbackRate=2.0;}")

            # ============================================
            #  播放期间：每2秒轻量扫描弹窗，每25秒截图
            # ============================================
            print("\n[3] Watching... (auto-detect popups every 2s)")
            print("    Popup keywords: 继续, 确定, 已阅读, 认真, 检测")
            print("    Completion keywords: 学完, 已完成, 播放完毕, 恭喜")

            tick = 0
            screenshot_tick = 0
            max_wait = 60 * 30  # 30 min

            while tick * 2 < max_wait:
                if video_page.is_closed():
                    print("\n[EVENT] video page auto-closed!")
                    break

                # 每2秒：轻量文本扫描（只读 body 文本，不查 DOM 树）
                try:
                    result = await video_page.evaluate("""
                        () => {
                            var body = document.body.innerText || '';
                            var popup = false, popupText = '', done = false;
                            // 弹窗关键词
                            var popupKw = ['认真度','检测','已阅读','继续','确定','我知道了','认真读','学习提醒'];
                            for (var i=0;i<popupKw.length;i++) {
                                var idx = body.indexOf(popupKw[i]);
                                if (idx>=0) {
                                    popup = true;
                                    popupText = body.substring(Math.max(0,idx-30), idx+80);
                                    break;
                                }
                            }
                            // 完成关键词
                            var doneKw = ['学完','已完成','播放完毕','恭喜','本课已学完','再学一课'];
                            for (var j=0;j<doneKw.length;j++) {
                                if (body.indexOf(doneKw[j])>=0) { done=true; break; }
                            }
                            return { popup:popup, popupText:popupText, done:done, bodyLen:body.length };
                        }
                    """)

                    if result.get("popup"):
                        print(f"\n[!] POPUP DETECTED: \"{result['popupText']}\"")
                        print(f"    auto-analyzing...")
                        await analyze(video_page, f"popup_detected_{datetime.now().strftime('%H%M%S')}")
                        print(f"    resuming watch...")

                    if result.get("done"):
                        print("\n[EVENT] completion text detected!")
                        break
                except Exception:
                    pass

                # 每25秒截图（弹窗只有30秒，留5秒余量）
                if tick % 12 == 0:
                    await video_page.screenshot(path=str(OUT / f"screenshot_tick{screenshot_tick:02d}.png"), full_page=True)
                    print(f"  [screenshot {screenshot_tick}] {datetime.now().strftime('%H:%M:%S')}")
                    screenshot_tick += 1

                await asyncio.sleep(2)
                tick += 1

            # ============================================
            #  视频结束 → 完整分析
            # ============================================
            print("\n[4] Video done, analyzing...")
            if not video_page.is_closed():
                await analyze(video_page, "03_video_ended")
                await video_page.close()

            # -- 返回课程列表 --
            await page.bring_to_front()
            await page.wait_for_timeout(3000)

            # 处理弹窗
            for kw in ["继续","确定","知道了","已阅读","关闭"]:
                try:
                    el = page.get_by_text(kw,exact=False).first
                    if await el.is_visible(timeout=500):
                        await el.click()
                        print(f"  clicked '{kw}'")
                        await page.wait_for_timeout(1000)
                except Exception: pass

            await page.wait_for_timeout(2000)

            # -- 分析返回后的课程列表 --
            await analyze(page, "04_course_list_after")

            print(f"\n[DONE] All files in {OUT}")

        except KeyboardInterrupt:
            print("\n\n[!] Paused. Do you want to:")
            print("  1 = analyze current video page and exit")
            print("  2 = analyze main page and exit")
            print("  3 = just exit")
            try:
                choice = input("> ").strip()
                if choice == "1" and video_page and not video_page.is_closed():
                    await analyze(video_page, "manual_video")
                elif choice == "2":
                    await analyze(page, "manual_main")
            except Exception: pass
        except Exception as e:
            print(f"[X] {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
