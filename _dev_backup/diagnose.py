#!/usr/bin/env python3
"""
诊断脚本 — 打开页面，导出所有可交互元素，帮助定位正确的选择器
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

CONFIG_PATH = Path(__file__).parent / "config.json"
OUTPUT_DIR = Path(__file__).parent / "diagnosis"
OUTPUT_DIR.mkdir(exist_ok=True)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)


async def dump_page_info(page, label):
    """导出当前页面的所有有用信息"""
    print(f"\n{'='*60}")
    print(f"📄 页面分析: {label}")
    print(f"📍 URL: {page.url}")
    print(f"📍 Title: {await page.title()}")

    # 截图
    screenshot_path = OUTPUT_DIR / f"{label}.png"
    await page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"📸 截图: {screenshot_path}")

    # 导出完整 HTML
    html_path = OUTPUT_DIR / f"{label}.html"
    html = await page.content()
    html_path.write_text(html, encoding="utf-8")
    print(f"📝 HTML: {html_path} ({len(html)} 字符)")

    # 列出所有 iframe
    frames = page.frames
    print(f"\n🖼️ iframe 数量: {len(frames)}")
    for idx, frame in enumerate(frames):
        print(f"  Frame {idx}: url={frame.url}, name={frame.name}")

    # 导出所有可见的交互元素信息
    info = await page.evaluate("""() => {
        const result = { buttons: [], links: [], inputs: [], text: [], selects: [] };

        // 按钮
        document.querySelectorAll('button, [role="button"], .btn, [class*="btn"], [onclick]').forEach(el => {
            const rect = el.getBoundingClientRect();
            const text = (el.textContent || '').trim().substring(0, 100);
            const cls = el.className || '';
            const id = el.id || '';
            if (text || cls) {
                result.buttons.push({
                    tag: el.tagName,
                    text: text,
                    class: cls.substring(0, 150),
                    id: id,
                    visible: rect.width > 0 && rect.height > 0,
                    rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                });
            }
        });

        // 链接
        document.querySelectorAll('a[href], span[class*="link"], div[class*="click"]').forEach(el => {
            const rect = el.getBoundingClientRect();
            const text = (el.textContent || '').trim().substring(0, 100);
            const href = el.href || el.getAttribute('href') || '';
            if (text && rect.width > 0) {
                result.links.push({
                    text: text,
                    href: href.substring(0, 200),
                    class: (el.className || '').substring(0, 150),
                    visible: rect.height > 0
                });
            }
        });

        // 输入框
        document.querySelectorAll('input, textarea').forEach(el => {
            result.inputs.push({
                type: el.type || 'text',
                name: el.name || '',
                placeholder: el.placeholder || '',
                class: (el.className || '').substring(0, 150),
                id: el.id || ''
            });
        });

        // 所有可见文本节点（提取关键文本内容）
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        const seen = new Set();
        while (walker.nextNode()) {
            const text = walker.currentNode.textContent.trim();
            if (text.length > 1 && text.length < 60 && !seen.has(text)) {
                seen.add(text);
                const parent = walker.currentNode.parentElement;
                if (parent && parent.getBoundingClientRect().height > 0) {
                    result.text.push({
                        text: text,
                        parent_tag: parent.tagName,
                        parent_class: (parent.className || '').substring(0, 100)
                    });
                }
            }
        }

        // select 下拉框
        document.querySelectorAll('select').forEach(el => {
            const options = [];
            el.querySelectorAll('option').forEach(opt => {
                options.push({ text: opt.textContent.trim(), value: opt.value });
            });
            result.selects.push({ name: el.name, options: options });
        });

        return result;
    }""")

    # 保存交互元素信息
    info_path = OUTPUT_DIR / f"{label}_elements.json"
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📊 元素信息: {info_path}")

    # 汇总输出
    print(f"\n  Buttons:  {len(info['buttons'])}")
    print(f"  Links:    {len(info['links'])}")
    print(f"  Inputs:   {len(info['inputs'])}")
    print(f"  Texts:    {len(info['text'])}")

    # 打印前20个可见按钮
    visible_btns = [b for b in info['buttons'] if b['visible']]
    print(f"\n  可见按钮 ({len(visible_btns)}):")
    for b in visible_btns[:20]:
        print(f"    [{b['tag']}] \"{b['text'][:60]}\" class=\"{b['class'][:80]}\"")

    # 打印可见链接
    visible_links = [l for l in info['links'] if l['visible']]
    print(f"\n  可见链接 ({len(visible_links)}):")
    for l in visible_links[:15]:
        print(f"    \"{l['text'][:60]}\" → {l['href'][:80]}")

    return info


async def main():
    print("=" * 60)
    print("  诊断模式 — 分析页面结构")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149.0.0.0 Safari/537.36",
        )

        page = await context.new_page()

        try:
            # ===== Step 1: 登录页 =====
            login_url = config["login_url"]
            print(f"\n🔗 打开登录页: {login_url}")
            await page.goto(login_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)
            await dump_page_info(page, "01_login_page")

            # ===== Step 2: 填写并登录 =====
            account = config["account"]
            password = config["password"]

            print(f"\n📝 尝试登录: {account}")
            # 尝试各种输入框
            for sel in [
                "input[type='text']",
                "input[placeholder*='手机']",
                "input[placeholder*='账号']",
                "input[name*='phone']",
                "input[name*='mobile']",
                "input[name*='user']",
                "input[name*='account']",
                "input:not([type='password'])",
                "input",
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=1000):
                        await el.click()
                        await el.fill("")
                        await el.type(account, delay=100)
                        print(f"  ✅ 用户名输入: {sel}")
                        break
                except Exception:
                    continue
            else:
                print("  ❌ 未找到用户名输入框！")

            for sel in ["input[type='password']", "input[placeholder*='密码']"]:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=1000):
                        await el.click()
                        await el.fill("")
                        await el.type(password, delay=100)
                        print(f"  ✅ 密码输入: {sel}")
                        break
                except Exception:
                    continue
            else:
                print("  ❌ 未找到密码输入框！")

            await page.screenshot(path=str(OUTPUT_DIR / "02_form_filled.png"), full_page=True)

            # 点击登录
            clicked = False
            for text in ["登录", "登 录", "立即登录"]:
                try:
                    btn = page.get_by_text(text, exact=False).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        clicked = True
                        print(f"  ✅ 点击登录: {text}")
                        break
                except Exception:
                    continue

            if not clicked:
                # 尝试用 enter 键
                await page.keyboard.press("Enter")
                print("  ⚠️ 使用 Enter 键提交")

            # 等待登录结果
            print("⏳ 等待登录...")
            await page.wait_for_timeout(5000)
            await dump_page_info(page, "03_after_login_attempt")

            # ===== Step 3: 任务页面 =====
            task_url = config["task_url"]
            if task_url:
                print(f"\n🔗 跳转到任务页面: {task_url}")
                await page.goto(task_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(5000)
                await dump_page_info(page, "04_task_page")

                # 尝试滚动
                print("\n📜 滚动页面...")
                for i in range(3):
                    await page.evaluate("window.scrollBy(0, 500)")
                    await page.wait_for_timeout(1000)
                await page.screenshot(path=str(OUTPUT_DIR / "05_task_scrolled.png"), full_page=True)

                # 搜索关键文本
                for keyword in ["未学习", "已完成", "课程", "任务", "日期", "日历", "视频"]:
                    try:
                        count = await page.get_by_text(keyword).count()
                        if count > 0:
                            print(f"  🔍 '{keyword}': 找到 {count} 处")
                            first = page.get_by_text(keyword).first
                            text = await first.text_content()
                            print(f"     首处内容: {text[:80]}")
                    except Exception:
                        pass

            # ===== 等待用户手动操作 =====
            print("\n" + "=" * 60)
            print("⏸️  浏览器保持打开，你可以手动浏览页面")
            print("   按 Enter 继续分析当前页面，输入 q 退出...")
            while True:
                cmd = input("> ").strip()
                if cmd.lower() == "q":
                    break
                elif cmd == "":
                    # 分析当前页面
                    timestamp = datetime.now().strftime("%H%M%S")
                    await dump_page_info(page, f"manual_{timestamp}")

                    # 深入分析课程列表区域
                    print("\n🔍 深入搜索课程相关元素...")
                    courses = await page.evaluate("""() => {
                        // 查找所有可能包含课程信息的容器
                        const containers = [];
                        // 查找所有带有 "item" 或 "task" 或 "course" 或 "lesson" class 的元素
                        document.querySelectorAll('[class*="item"], [class*="task"], [class*="course"], [class*="lesson"], [class*="card"], li').forEach(el => {
                            const rect = el.getBoundingClientRect();
                            const text = (el.textContent || '').trim().substring(0, 200);
                            if (text.length > 5 && rect.width > 100) {
                                containers.push({
                                    tag: el.tagName,
                                    class: (el.className || '').substring(0, 200),
                                    text: text.substring(0, 150),
                                    rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                                });
                            }
                        });
                        return containers.slice(0, 50);
                    }""")
                    courses_path = OUTPUT_DIR / f"courses_{timestamp}.json"
                    courses_path.write_text(json.dumps(courses, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"📊 候选课程容器: {courses_path} ({len(courses)} 个)")
                    for c in courses[:20]:
                        print(f"    [{c['tag']}] \"{c['text'][:80]}\" class=\"{c['class'][:80]}\"")

        except KeyboardInterrupt:
            print("\n⚠️ 用户中断")
        except Exception as e:
            print(f"\n❌ 错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("\n📁 所有诊断文件保存在: ", OUTPUT_DIR)
            print("🔒 关闭浏览器...")
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
