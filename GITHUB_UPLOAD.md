# 上传到 GitHub 并开启网页展示

本包保留已确认的网页布局，以及 39 张卡片上真实的历史展示指标。内部连接信息、原始数据库、实际主键配置和非展示字段已排除。网页上的表名、时间列名与指标仍能被访问者查看；详见 `PRIVACY.md`。

## 1. 解压并上传

1. 下载 ZIP，在 Windows 中右键选择“全部解压”，打开解压后的 `Table_Status_Dashboard` 文件夹。
2. 登录 GitHub，打开已创建的仓库 [https://github.com/hjxupup/table-status-dashboard](https://github.com/hjxupup/table-status-dashboard)。使用 GitHub Free 发布 Pages 时，仓库需设为 Public。
3. 打开仓库上传入口：已有仓库选择 **Add file → Upload files**；空仓库选择 **uploading an existing file**。
4. 将解压后文件夹内的文件和子文件夹拖进上传区域。上传文件内容，而不是只上传 ZIP，也不要额外套一层 `Table_Status_Dashboard` 目录。
5. 确认 `README.md` 位于仓库根目录，网页入口是 `docs/index.html`，然后按页面提示提交。提交说明可填写 `Add table status dashboard with original historical snapshots`。

本包 README 已填入计划发布地址 `https://hjxupup.github.io/table-status-dashboard/`；启用 Pages 并部署成功后，此链接才会生效。

README 会显示在仓库首页。源码、历史数据和静态网页会一起保存在仓库中。

## 2. 开启 GitHub Pages

1. 打开仓库 **Settings → Pages**。
2. 在 **Build and deployment** 下，将 **Source** 设为 **Deploy from a branch**。
3. 分支选你的默认分支，通常为 **main**；文件夹选 **/docs**。
4. 点击 **Save**，等待部署完成。
5. 部署完成后，复制 Pages 页面显示的实际网址。

`docs` 已经生成好，无需安装 Python，也无需先运行 Flask。GitHub Pages 展示历史快照；重新分析按钮会重新读取已有快照，并保留真实的采集时间。时间列选择、星标收藏和缓存刷新保留原交互。

## 3. 在 GitHub 首页放网页链接

点击仓库首页 **About** 旁的设置图标，将刚才复制的网址填入 **Website** 并保存。

也可以编辑 `README.md`，在开头加一行：

```markdown
[Live Demo](https://hjxupup.github.io/table-status-dashboard/)
```

别人进入 GitHub 项目后，即可点击链接打开网页。

## 4. 本地预览和后端运行

- 双击 `Table_Status_Dashboard.html` 可直接预览网页。
- 如需运行 Flask，在项目目录执行 `python -m pip install -r requirements.txt`，再执行 `python run.py`，打开 `http://127.0.0.1:8000`。
- 实时 Hive/JDBC 配置和详细技术介绍保留在 `README.md` 中。

## 文件说明

| 文件或目录 | 用途 |
| --- | --- |
| `README.md` | 项目介绍、技术方案和运行说明 |
| `GITHUB_UPLOAD.md` | 当前上传指南 |
| `app/` | Flask 后端与网页模板、样式和交互 |
| `data/snapshots.json` | 原来 39 张表各自最新的一份历史快照 |
| `docs/` | 可直接发布到 GitHub Pages 的网页 |
| `Table_Status_Dashboard.html` | 可双击打开的单文件预览 |
| `target_tables.txt.example`、`table_primary_keys.json.example` | 通用配置模板，实际配置留在本地 |
| `PRIVACY.md` | 公开版本的隐私边界与清理说明 |
| `tools/` | 静态网页导出工具 |
| `tests/` | 后端与静态数据适配器的验证 |
| `.env.example` | 实时连接的配置模板 |

GitHub 官方操作说明：[上传文件](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)、[配置 Pages 发布目录](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)。
