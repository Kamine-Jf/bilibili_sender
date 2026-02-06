# B站弹幕自动发送脚本

这是一个使用 Python 编写的自动发送弹幕脚本，支持直播间和视频（主要针对直播间优化）。

## 功能特点
- 自动循环发送指定的两条弹幕内容
- 异步高并发支持 (`aiohttp`)
- 随机发送间隔，降低被封几率
- 支持从文件读取 Cookies
- 详细的日志记录

## 使用前准备

1. **安装依赖**
   请确保已安装 Python 3.7+，然后在终端运行：
   ```bash
   pip install aiohttp
   ```

2. **获取 Cookies**
   - 在浏览器登录 Bilibili。
   - 按 `F12` 打开开发者工具，进入 "Application" (应用) -> "Cookies"。
   - 找到 `https://bilibili.com`。
   - 复制以下关键字段的值：
     - `SESSDATA` (最重要，用于鉴权)
     - `bili_jct` (最重要，即CSRF Token)
     - `DedeUserID` (用户ID)

3. **配置 Cookies**
   打开目录下的 `cookies.json` 文件，填入你获取到的值：
   ```json
   {
       "SESSDATA": "xxxxxx",
       "bili_jct": "xxxxxx",
       "DedeUserID": "xxxxxx"
   }
   ```

## 运行脚本

在终端运行：
```bash
python main.py
```
然后根据提示输入 **直播间ID** (例如 `21672008`) 或 **视频BV号**。

## 注意事项
- **封号风险**：高频发送重复内容容易触发B站的风控系统，导致账号被禁言或封禁。建议发送间隔不要低于 1 秒。
- **视频弹幕**：视频弹幕有严格的去重和频率限制，本脚本虽然支持发送视频弹幕，但成功率远低于直播间弹幕。
