# EWT360 Auto Course Player

> A Playwright-based browser automation script that automatically completes daily course tasks on the EWT360 (升学e网通) online learning platform.

## Features

- ✅ Automatic login (account/password)
- ✅ Select task date and enter daily tasks
- ✅ Auto-detect uncompleted courses and play them one by one
- ✅ Set video playback speed to 2x
- ✅ Auto-detect and click attentiveness check popups
- ✅ Detect course completion popup and proceed to next course
- ✅ Exit when all courses are completed

## Requirements

- **Python**: 3.9+
- **Chrome**: Installed on your system (script uses system Chrome)
- **OS**: Windows / macOS / Linux

## Installation

```bash
# 1. Install Python dependencies
pip install playwright

# 2. Install Chromium browser (for Playwright)
playwright install chromium
```

> If download is slow, use a mirror:
> ```bash
> pip install playwright -i https://mirrors.aliyun.com/pypi/simple/
> ```

## Quick Start

### Step 1: Configuration

Run the setup wizard to enter your account, password, and task info:

```bash
python setup.py
```

The wizard will ask for:

| Field | Description | Example |
|-------|-------------|---------|
| Account | EWT360 phone number / username | `138xxxx8888` |
| Password | Login password | `********` |
| Login URL | Keep default | `https://web.ewt360.com/register/#/login` |
| Task URL | See guide below | `https://teacher.ewt360.com/.../student-task-overview?homeworkId=xxxxx` |
| Task Date | Date of courses to complete | `2026-07-14` |
| Speed | Video playback speed | `2.0` |

### Step 2: Run

```bash
python ewt_auto.py
```

### Common Options

```bash
# Show browser window (default: hidden)
python ewt_auto.py --show

# Specify date (overrides config file)
python ewt_auto.py --date 2026-07-14

# Debug mode (saves screenshots to screenshots/)
python ewt_auto.py --debug

# Set video speed
python ewt_auto.py --speed 2.0
```

## How to Get Your Task URL

1. Log in to EWT360 student portal in your browser
2. Navigate to **My Tasks** → **Daily Tasks** / **Holiday Tasks**
3. Click a task to enter its detail page
4. **Copy the full URL from your browser's address bar**
5. It should look like this:
   ```
   https://teacher.ewt360.com/ewtbend/bend/index/index.html#/holiday/student-task-overview?homeworkId=1234567
   ```

## Configuration Details

The `config.json` file stores all settings in JSON format:

```json
{
  "account": "138xxxx8888",
  "password": "********",
  "login_url": "https://web.ewt360.com/register/#/login",
  "task_url": "https://teacher.ewt360.com/.../student-task-overview?homeworkId=xxxxx",
  "task_date": "2026-07-14",
  "video_speed": 2.0,
  "headless": false
}
```

You can edit `config.json` directly — no need to run `setup.py` every time.

## How It Works

1. Launch Chrome and navigate to the login page
2. Fill in credentials and click login
3. Navigate to the task page
4. Select the target date from the left sidebar
5. Scan the course list for "学" buttons (excluding completed "已学完" courses)
6. Click each "学" button sequentially → course video opens in a new window
7. Set video speed to 2x
8. Wait for video to finish (detects the "太酷啦" completion popup)
9. Auto-close the video window, return to course list
10. Refresh the page, re-select the date, and proceed to the next course
11. Exit when all courses are completed

## FAQ

**Q: Video doesn't play or speed setting doesn't work?**
A: The website may have anti-bot detection. Try adding more anti-detection scripts in `ewt_auto.py`.

**Q: Attentiveness check popup not auto-clicked?**
A: The popup button text/class might differ from what's configured. Run with `--debug` to capture screenshots for analysis.

**Q: Task page shows "已截止" (expired)?**
A: The task date may have passed. Check `task_date` and `task_url` in `config.json`.

**Q: Script reports "no '学' buttons"?**
A: All courses may be completed, or the page structure has changed. Verify that the task date is correct.

## Tech Stack

- [Playwright](https://playwright.dev/) — browser automation framework
- Python 3.10+

## License

MIT