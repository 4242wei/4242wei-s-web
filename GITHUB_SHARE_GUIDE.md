# GitHub 共享说明

这个仓库已经按“只上传代码，不上传你的本地资料和密钥”的方式整理。

## 不会上传的内容

以下内容默认不会进入 GitHub：

- `.env`
- `.env.local`
- `data/`
- `uploads/`
- `reports/`
- `backups/`
- `logs/`
- `.venv/`

这意味着下面这些都不会被共享出去：

- 你的阿里云 / 听悟 / OSS 密钥
- 你本地的研究资料
- 语音转录源文件
- AI 会话记录
- 监控结果和运行日志

## 同事最简单的使用方式

推荐让同事直接按下面流程使用：

1. 从 GitHub 拉代码
2. 在自己的电脑上准备自己的本地目录和密钥
3. 直接运行 `start.bat`

```powershell
git clone https://github.com/4242wei/4242wei-s-web.git
cd 4242wei-s-web
.\start.bat
```

启动后打开：

```text
http://127.0.0.1:5000
```

## 同事如何配置自己的本地路径

如果同事有自己的 Markdown 报告目录，不需要改代码，只要在项目根目录新建 `.env.local`：

```text
REPORTS_DIR=D:\你的报告目录
```

例如：

```text
REPORTS_DIR=D:\工作\FTAI\reports
```

项目还支持这些可选路径覆盖：

```text
STOCKS_DATA_PATH=
STOCKS_UPLOADS_DIR=
TRANSCRIPT_UPLOADS_DIR=
AI_CHAT_DATA_PATH=
AI_CONTEXT_DIR=
```

如果不填，就会使用项目默认本地目录。

## 同事如何启用语音转录

如果同事要使用听悟 / OSS，他们各自在自己的 `.env.local` 中填写：

```text
ALIBABA_CLOUD_ACCESS_KEY_ID=
ALIBABA_CLOUD_ACCESS_KEY_SECRET=
ALIYUN_TINGWU_APP_KEY=
ALIYUN_TINGWU_ENDPOINT=tingwu.cn-beijing.aliyuncs.com
ALIYUN_TINGWU_REGION_ID=cn-beijing
ALIYUN_TINGWU_API_VERSION=2023-09-30
ALIYUN_OSS_ENDPOINT=https://oss-cn-beijing.aliyuncs.com
ALIYUN_OSS_REGION_ID=cn-beijing
ALIYUN_OSS_BUCKET=
```

这些配置不要提交到 GitHub。

## 如果同事只想空白启动

也可以什么都不准备，直接启动：

- 没有 `data/` 也可以
- 没有 `uploads/` 也可以
- 没有 `reports/` 也可以

项目会先以一个空白工作台启动，后面再由他们自己添加资料。

## 适合共享什么

这个仓库适合共享：

- 页面代码
- 模板和样式
- 前后端逻辑
- 启动方式

这个仓库不适合直接共享：

- 你的私有研究内容
- 你的账号密钥
- 你的本地文件和日志

如果以后你想给同事一份“接近你当前本地内容”的副本，建议单独导出备份 zip 给他们，而不是把 `data/` 和 `uploads/` 推到 GitHub。
