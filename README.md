# 升学e网通 自动刷课脚本

> 一个基于 Playwright 的浏览器自动化脚本，自动完成升学e网通的每日课程任务。

## 功能

- ✅ 自动登录（账号密码登录）
- ✅ 选择任务日期，进入每日任务
- ✅ 自动识别未学习课程，逐个学习
- ✅ 视频自动设置为 2 倍速播放
- ✅ 自动检测并点击"认真度检测"弹窗
- ✅ 视频播完后自动检测完成弹窗，进入下一课
- ✅ 全部课程完成后退出

## 环境要求

- **Python**: 3.9+
- **Chrome**: 已安装（会自动使用系统 Chrome）
- **操作系统**: Windows / macOS / Linux

## 安装

```bash
# 1. 安装 Python 依赖
pip install playwright

# 2. 安装 Chromium 浏览器（供 Playwright 使用）
playwright install chromium
```

> 如果下载慢，可指定国内镜像源：
> ```bash
> pip install playwright -i https://mirrors.aliyun.com/pypi/simple/
> ```

## 快速开始

### 第一步：配置

运行配置向导，填写账号密码和任务信息：

```bash
python setup.py
```

交互式填写：

| 字段 | 说明 | 示例 |
|------|------|------|
| 账号 | 升学e网通手机号/账号 | `138xxxx8888` |
| 密码 | 登录密码 | `********` |
| 登录页地址 | 默认即可 | `https://web.ewt360.com/register/#/login` |
| 任务页地址 | 见下方说明 | `https://teacher.ewt360.com/.../student-task-overview?homeworkId=xxxxx` |
| 课程日期 | 要完成的课程日期 | `2026-07-14` |
| 倍速 | 视频播放速度 | `2.0` |

### 第二步：运行

```bash
python ewt_auto.py
```

### 常用参数

```bash
# 显示浏览器窗口（默认不显示）
python ewt_auto.py --show

# 指定日期（覆盖配置文件）
python ewt_auto.py --date 2026-07-14

# 调试模式（每一步截图保存到 screenshots/）
python ewt_auto.py --debug

# 设置倍速
python ewt_auto.py --speed 2.0
```

## 如何获取任务页地址

1. 在浏览器中登录 升学e网通 学生端
2. 进入 **我的任务** → **每日任务** / **假期任务**
3. 选择一个任务，进入任务详情页
4. **复制浏览器地址栏的完整 URL**
5. 它看起来像这样：
   ```
   https://teacher.ewt360.com/ewtbend/bend/index/index.html#/holiday/student-task-overview?homeworkId=1234567
   ```

## 配置详解

配置文件 `config.json` 用 JSON 格式存储所有设置：

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

可直接编辑 `config.json` 修改配置，无需每次都运行 `setup.py`。

## 运行原理

1. 打开 Chrome 浏览器，访问登录页
2. 填写账号密码，点击登录
3. 跳转到任务页面
4. 从左侧日期列表中选择目标日期
5. 扫描课程列表中的"学"按钮（排除"已学完"的课程）
6. 逐个点击"学"按钮 → 视频在新窗口打开
7. 设置视频为 2 倍速播放
8. 等待视频播放完毕（检测"太酷啦"完成弹窗）
9. 自动关闭视频窗口，回到课程列表
10. 刷新页面，重新选择日期，继续下一课
11. 全部课程完成时退出

## 常见问题

**Q: 视频不播放/倍速没生效？**
A: 可能被网站反自动化检测。尝试在 `ewt_auto.py` 中增加更多反检测脚本。

**Q: 认真度检测弹窗没自动点击？**
A: 弹窗按钮文字和 class 可能与脚本中配置的不同。运行 `--debug` 模式截图分析。

**Q: 任务页面显示"已截止"？**
A: 任务可能在设定日期前已截止。检查 `config.json` 中的 `task_date` 和 `task_url` 是否正确。

**Q: 脚本报错 "no '学' buttons"？**
A: 课程可能全部已完成，或者页面结构发生变化。检查任务日期是否正确。

## 技术栈

- [Playwright](https://playwright.dev/) — 浏览器自动化框架
- Python 3.10+

## 许可证

MIT