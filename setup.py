#!/usr/bin/env python3
"""
升学e网通 自动刷课 --- 配置向导
首次运行时使用，引导用户填写账号、密码、任务URL等信息，生成 config.json
"""

import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULT = {
    "account": "",
    "password": "",
    "login_url": "https://web.ewt360.com/register/#/login",
    "task_url": "",
    "task_date": "",
    "headless": False,
    "video_speed": 2.0,
    "selectors": {
        "username_input": "#login__password_userName",
        "password_input": "#login__password_password",
        "login_button": "button:has-text('登 录')",
        "course_item": "LI.taskItem-ZeyMG",
        "study_button": ".btn-AoqsA:has-text('学')",
        "video_player": "video, [class*='player'], iframe",
        "speed_button": "button:has-text('倍速'), [class*='speed'], [class*='rate']",
        "read_detection_btn": "button:has-text('已阅读'), button:has-text('继续'), button:has-text('确定'), button:has-text('知道了'), [class*='read-dialog'] button, .ant-modal button:has-text('确定')",
        "back_button": "button:has-text('返回'), [class*='back'], span:has-text('返回'), a:has-text('返回')",
    },
}


def load_existing():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text("utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    print(f"\n[OK] config saved -> {CONFIG_PATH}")


def ask(prompt, default=""):
    if default:
        return input(f"{prompt} [{mask_str(default)}]: ").strip() or default
    return input(f"{prompt}: ").strip()


def mask_str(s, show=3):
    """隐藏字符串中间的字符"""
    if len(s) <= show * 2:
        return "*" * len(s)
    return s[:show] + "*" * (len(s) - show * 2) + s[-show:]


def main():
    print("=" * 56)
    print("  升学e网通 自动刷课 --- 配置向导")
    print("=" * 56)
    print()

    existing = load_existing()
    if existing:
        print("[i] 检测到已有配置, 直接回车保留现有值\n")

    cfg = {}

    print("-" * 40)
    print("  账号设置")
    cfg["account"] = ask("  账号/手机号", existing.get("account", DEFAULT["account"]))
    cfg["password"] = ask("  密码", existing.get("password", DEFAULT["password"]))

    print()
    print("-" * 40)
    print("  URL 设置")
    cfg["login_url"] = ask("  登录页地址", existing.get("login_url", DEFAULT["login_url"]))
    cfg["task_url"] = ask("  任务页地址", existing.get("task_url", DEFAULT["task_url"]))

    print()
    print("-" * 40)
    print("  任务设置")
    cfg["task_date"] = ask(
        "  课程日期 (YYYY-MM-DD)",
        existing.get("task_date", DEFAULT["task_date"]),
    )

    print()
    print("-" * 40)
    print("  播放设置")
    speed_str = ask(
        "  倍速 (1.0/1.5/2.0)",
        str(existing.get("video_speed", DEFAULT["video_speed"])),
    )
    try:
        cfg["video_speed"] = float(speed_str)
    except ValueError:
        cfg["video_speed"] = 2.0

    hd = "y" if existing.get("headless", DEFAULT["headless"]) else "n"
    cfg["headless"] = ask("  无头模式? (y/n)", hd).lower() in ("y", "yes", "1")

    # 保留高级选择器
    cfg["selectors"] = existing.get("selectors", DEFAULT["selectors"])

    print()
    print("-" * 40)
    print("  预览:")
    print(f"  账号:     {cfg['account']}")
    print(f"  密码:     {mask_str(cfg['password'], 1)}")
    print(f"  登录页:   {cfg['login_url']}")
    print(f"  任务页:   {cfg['task_url'][:60] + '...' if len(cfg.get('task_url','')) > 60 else cfg['task_url']}")
    print(f"  日期:     {cfg['task_date']}")
    print(f"  倍速:     {cfg['video_speed']}x")
    print(f"  无头模式: {'是' if cfg['headless'] else '否'}")

    if ask("\n  保存以上配置? (y/n)", "y").lower() in ("y", "yes", ""):
        save_config(cfg)
        print("\n  运行: python ewt_auto.py")
    else:
        print("[X] 已取消")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[X] 已取消")
        sys.exit(0)
