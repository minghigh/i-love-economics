# i-love-economics

第一版已经打通：每天从旧项目 `we-mp-rss` 的 SQLite 里读取昨天发布的公众号文章，用本地 LLM 做筛选和选题理解，再用 DeepSeek 生成可发布的公众号文章候选稿、HTML 排版稿、封面图和事实校验结果。

## 当前部署

代码已同步到 251：

```bash
/home/daofu/github/i-love-economics
```

251 上的 `.env` 已配置：

- `LOCAL_LLM_BASE_URL=http://10.88.255.251:8008/v1`
- `LOCAL_LLM_API_KEY`
- `DEEPSEEK_API_KEY`
- `WE_MP_RSS_DB_PATH=/we-mp-rss-data/db.db`
- `SCREEN_BATCH_SIZE=20`

`.env.example` 只保留变量名，不放真实密钥。

## 每天自动运行

251 已安装 cron，每天凌晨 2 点跑：

```bash
cd /home/daofu/github/i-love-economics
docker compose run --rm daily --date yesterday
```

日志写到：

```bash
/home/daofu/github/i-love-economics/logs/daily.log
```

## 手动运行

```bash
cd /home/daofu/github/i-love-economics
docker compose run --rm daily --date yesterday
```

重跑某天：

```bash
docker compose run --rm daily --date 2026-07-04 --force
```

## 输出目录

每次运行生成：

```text
data/index.html
data/runs/YYYY-MM-DD/
  index.html
  articles.json
  screening.json
  topics.json
  rejected_topics.json
  run.log
  candidates/
    01/
      article.md
      article.html
      cover.png
      sources.json
      fact_check.json
      knowledge-card.patch.md
      topic.json
```

打开当天的 `index.html` 看候选稿：

```bash
data/runs/YYYY-MM-DD/index.html
```

打开总览页查看每天的文章情况：

```bash
data/index.html
```

## 发布流程

1. 打开当天 `index.html`。
2. 选择一篇候选。
3. 检查 `fact_check.json`，确认事实校验状态。
4. 推送到公众号草稿箱。
5. 在公众号后台人工预览、修改、发布。
6. 发布后再应用知识卡片。

推送草稿箱：

```bash
docker compose run --rm draft data/runs/YYYY-MM-DD/candidates/01
```

成功后会写入：

```text
data/runs/YYYY-MM-DD/candidates/01/wechat-draft.json
```

需要先在 251 的 `.env` 配好 `WECHAT_APPID`、`WECHAT_APPSECRET`，并把 251 的出口 IP 加到公众号后台 IP 白名单。

应用知识卡片：

```bash
docker compose run --rm apply-card data/runs/YYYY-MM-DD/candidates/01
```

## 单篇重写

```bash
docker compose run --rm rewrite data/runs/YYYY-MM-DD/candidates/02
```

旧稿会备份成：

```text
article.prev.md
article.prev.html
```

## 已验证

2026-07-04 已试跑成功，生成 3 篇候选：

1. `日本为何开始从废旧空调中提取稀土？`
2. `世界杯来了，电视却卖不动了：智能电视的商业模式与消费者体验的冲突`
3. `鸭血粉丝店被LV起诉，实际侵权方竟是隔壁餐吧：商标权与责任归属的经济学分析`

三篇事实校验均为 `passed`。

## 第一版边界

不做：

- 自动发布公众号。
- Web UI 编辑器。
- 文章正文配图。
- AI 生成图片。
- 数据库。
- 外部搜索 API。

先用文件系统、Docker、可见 prompt 和静态 `index.html` 把每日流程跑稳。
