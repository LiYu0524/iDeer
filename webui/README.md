# iDeer Web UI

iDeer 的浏览器端前端，基于 React 构建，替代原有的 HTML 内嵌模板。

## 技术栈

- React 19 + TypeScript
- Vite 6
- Tailwind CSS 3.4
- React Router 7

## 开发

```bash
# 安装依赖
npm install

# 启动开发服务器（默认 http://localhost:5173）
npm run dev

# 构建
npm run build

# 预览构建结果
npm run preview
```

开发服务器通过 Vite proxy 将 `/api` 和 `/ws` 请求转发到后端 `localhost:8090`，需要先启动后端服务（`python web_server.py`）。

## 打包为桌面客户端

使用 PyWebView + PyInstaller 将前后端打包为单个可执行文件。

### 依赖

```bash
pip install pywebview pyinstaller httpx
```

### 打包步骤

```bash
# 1. 构建前端
cd webui && npm run build && cd ..

# 2. 打包为 exe（在项目根目录执行）
pyinstaller --onefile --windowed --name iDeer --add-data "webui/dist;webui/dist" desktop.py
```

打包产物在 `dist/iDeer.exe`。

### 原理

- `desktop.py` 在后台线程启动 FastAPI 后端，等待 `/health` 就绪后用 PyWebView 创建原生窗口加载 `http://127.0.0.1:8090`
- `web_server.py` 检测到 `webui/dist` 存在时，自动优先 serve React 构建产物（否则回退到旧模板）
- 静态资源（JS/CSS/SVG）放在 `public/` 目录下，构建后路径不变，避免 hash 问题

### 与 Tauri 的对比

| 维度       | PyWebView + PyInstaller        | Tauri                        |
| ---------- | ------------------------------ | ---------------------------- |
| 后端语言   | Python（无需重写）             | Rust（需要重写后端）         |
| 打包体积   | ~40-80 MB（含 Python 运行时）  | ~5-10 MB                     |
| 窗口渲染   | 系统 WebView（Edge / WKWebView）| 系统 WebView（同左）         |
| 启动速度   | 较慢（Python 解释器初始化）     | 快                           |
| 维护成本   | 低（现有 Python 代码直接复用）  | 高（需要用 Rust 重写全部逻辑）|
| 跨平台     | Windows / macOS / Linux        | Windows / macOS / Linux      |

**选择建议：** 如果后端逻辑较复杂且已有成熟的 Python 实现，PyWebView 方案更合适，避免用 Rust 重写大量代码。如果追求最小体积和最快启动速度，且愿意投入 Rust 开发成本，可以考虑 Tauri。

## 页面结构

| 路由       | 说明                 | 状态     |
| ---------- | -------------------- | -------- |
| `/`        | 公开页 -- 触发运行和查看结果 | 已完成   |
| `/admin`   | 管理后台 -- 配置/控制台/历史 | 已完成   |

## 项目结构

```
src/
  App.tsx                          # 路由入口
  main.tsx                         # 应用入口
  index.css                        # Tailwind 基础样式 + 自定义 CSS
  hooks/                           # 跨页面共享 Hook
    useToast.tsx                   # 通知状态（Context）
    useWebSocket.ts                # WebSocket 连接管理
  components/                      # 跨页面共享组件
    BackendStatus.tsx              # 后端连接状态横幅
    MarkdownRender.tsx             # Markdown 渲染
    Toast.tsx                      # 通知组件
  lib/
    api.ts                         # HTTP / WebSocket 通信层
    types.ts                       # 类型定义（含 AdminConfig / HistoryEntry 等）
    constants.ts                   # 常量（含 TYPE_COLORS / TYPE_LABELS 等）
    utils.ts                       # 工具函数
  pages/
    public/
      PublicPage.tsx               # 公开页主组件
      hooks/
        useMeta.ts                 # 公开页元信息 + 后端健康检查
      components/
        Header.tsx                 # 页头 + 模式切换
        HeroSection.tsx            # 标题区域
        MailWarning.tsx            # SMTP 未配置警告
        SendForm.tsx               # Quick / Custom 发送表单
        SourceSelection.tsx        # 数据源选择
        SourceCard.tsx             # 数据源卡片
        DeliveryToggle.tsx         # 投递方式切换
        RunProgress.tsx            # 运行进度条
        ResultPanel.tsx            # 结果面板
        FileCard.tsx               # 文件卡片
    admin/                         # 管理后台
      AdminPage.tsx                # 顶层编排（Tab 切换 + Hook 调用）
      hooks/
        useConfig.ts               # 配置加载/编辑/保存
        useHistory.ts              # 历史记录加载
        useRunState.ts             # WebSocket 运行生命周期
      components/
        Header.tsx                 # 导航栏 + Tab 按钮
        config/                    # 配置 Tab
          ConfigView.tsx           # 配置容器 + 保存按钮
          LLMConfig.tsx            # LLM 配置（Provider / Model / Key 等）
          EmailConfig.tsx          # 邮件配置（SMTP）
          SourceConfig.tsx         # 信息源配置（GitHub / HF / Twitter / arXiv / SS）
          InterestConfig.tsx       # 兴趣描述
          ProfileConfig.tsx        # 研究者画像
          ScheduleConfig.tsx       # 定时推送
        dashboard/                 # 控制台 Tab
          DashboardView.tsx        # 控制台容器
          QuickActions.tsx         # 快速运行 / 生成报告 / 研究想法
          SourceSelection.tsx      # 数据源选择网格
          SourceCard.tsx           # 数据源卡片（含配置摘要）
          RunPanel.tsx             # 运行进度 + 日志 + 取消
          ResultsPanel.tsx         # 运行结果展示
        records/                   # 历史 Tab
          HistoryView.tsx          # 历史记录容器 + 筛选
          HistoryList.tsx          # 历史卡片列表
          ResultModal.tsx          # 结果详情弹窗
public/                            # 静态资源（不经过 Vite 处理，原样复制到 dist）
  icons/
    icon_ideer.svg                 # 应用图标
```
