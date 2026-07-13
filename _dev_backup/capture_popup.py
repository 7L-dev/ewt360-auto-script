#!/usr/bin/env python3
"""一键抓取：登录→点学→等你拖到末尾→按回车捕获完成弹窗"""
import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright

CONFIG = Path(__file__).parent / "config.json"
OUT = Path(__file__).parent / "popup_capture"
OUT.mkdir(exist_ok=True)
cfg = json.loads(CONFIG.read_text("utf-8"))

async def capture(page, label):
    info = await page.evaluate("""
        () => {
            var popups=[];
            document.querySelectorAll('div,section').forEach(function(d){
                var s=window.getComputedStyle(d);
                if(s.position==='fixed'&&parseInt(s.zIndex)>50){
                    var r=d.getBoundingClientRect();
                    if(r.width>80&&r.height>40){
                        var bts=[];
                        d.querySelectorAll('button,[class*=btn]').forEach(function(b){var t=(b.textContent||'').trim();if(t)bts.push({text:t,class:(b.className||'').substring(0,100),html:b.outerHTML.substring(0,500)});});
                        popups.push({class:(d.className||'').substring(0,200),text:(d.textContent||'').trim().substring(0,300),buttons:bts,z:parseInt(s.zIndex),html:d.outerHTML.substring(0,1000)});
                    }
                }
            });
            return {url:location.href,popups:popups};
        }
    """)
    (OUT / f"{label}.json").write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding="utf-8")
    await page.screenshot(path=str(OUT / f"{label}.png"),full_page=True)
    print(f"\n  popups: {len(info['popups'])}")
    for p in info['popups']:
        print(f"  z={p['z']} class={p['class'][:100]}")
        print(f"  text: {p['text'][:200]}")
        for b in p['buttons']:
            print(f"  btn: \"{b['text']}\" class={b['class'][:80]}")
            print(f"  html: {b['html'][:300]}")
    return info

async def main():
    print("="*50)
    print("  弹窗捕获器")
    print("="*50)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False,channel="chrome",args=["--disable-blink-features=AutomationControlled","--no-sandbox"])
        ctx = await browser.new_context(viewport={"width":1920,"height":1080})
        page = await ctx.new_page()
        await page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>false});window.chrome={runtime:{}};")

        video_page = None
        async def on_page(p): nonlocal video_page; video_page = p
        ctx.on("page", on_page)

        try:
            # 登录
            print("\n[1] Login...")
            await page.goto(cfg["login_url"],wait_until="networkidle",timeout=30000)
            await page.wait_for_timeout(3000)
            await page.locator("#login__password_userName").type(cfg["account"],delay=80)
            await page.locator("#login__password_password").type(cfg["password"],delay=80)
            await page.locator("button:has-text('登 录')").click()
            await page.wait_for_timeout(5000)

            # 任务页+日期
            await page.goto(cfg["task_url"],wait_until="networkidle",timeout=30000)
            await page.wait_for_timeout(5000)
            date_str = cfg.get("task_date","2026-06-19")
            parts = date_str.split("-")
            chinese = f"{int(parts[1])}月{int(parts[2])}日" if len(parts)==3 else date_str
            await page.get_by_text(chinese,exact=False).first.click()
            await page.wait_for_timeout(3000)

            # 点"学"
            print("\n[2] Click '学'...")
            await page.locator(".btn-AoqsA").filter(has_text="学").first.click()
            await page.wait_for_timeout(5000)
            if not video_page:
                print("[X] no new page"); return
            await video_page.wait_for_load_state("domcontentloaded")
            await video_page.wait_for_timeout(3000)
            await video_page.evaluate("()=>{var vs=document.querySelectorAll('video');for(var i=0;i<vs.length;i++)vs[i].playbackRate=2.0;}")

            # 等待用户操作
            print("\n[3] NOW:")
            print("   1. 在浏览器里把视频进度条拖到最后")
            print("   2. 等弹窗出现")
            print("   3. 回到终端按 Enter")
            input("\n   按 Enter 捕获弹窗...")

            await capture(video_page, "completion_popup")
            print(f"\n  saved to {OUT}/completion_popup.json + .png")

        except KeyboardInterrupt: pass
        finally: await browser.close()

if __name__=="__main__": asyncio.run(main())
