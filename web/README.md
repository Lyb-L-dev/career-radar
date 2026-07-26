# Career Radar · Web 管理端

Career Radar 的 React 管理端，位于 Python 项目同一仓库的 `web/` 目录，默认连接项目提供的本地 FastAPI。画像来自 `config.yaml`，岗位与状态来自 SQLite，企业来自 YAML，运行记录由真实扫描任务写入；页面不会默认展示 Mock 结果。

## 技术栈

- React 19、TypeScript、Vite 7
- TanStack Query、React Router 7
- Tailwind CSS、shadcn/ui、lucide-react、sonner

## 推荐启动方式

先构建前端，再让 FastAPI 同时托管 API 与静态页面：

```powershell
cd E:\AIProjects\work\career-radar\web
npm ci
npm run lint
npm run build

cd E:\AIProjects\work\career-radar
.\.venv\Scripts\python.exe -m career_radar serve -c config.yaml
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

## 前端开发模式

FastAPI 保持运行，在另一个 PowerShell 窗口执行：

```powershell
cd E:\AIProjects\work\career-radar\web
npm run dev
```

访问 `http://127.0.0.1:7100`。`vite.config.ts` 会把 `/api` 代理到 `http://127.0.0.1:8000`。

默认配置等价于：

```dotenv
VITE_USE_MOCK=false
VITE_API_BASE_URL=/api
```

仅在纯 UI 演示时复制 `.env.example` 并设置 `VITE_USE_MOCK=true`。Mock 分支仍保留用于离线设计预览，但不会在未显式配置时启用。

## 数据与安全边界

- 所有请求集中在 `src/services/`，统一处理超时和 FastAPI `detail` 错误。
- 运行中任务每 3 秒轮询一次；单企业、全部企业和失败重试都会创建真实后端任务。
- JD 完整的具体岗位可创建 AI 申请任务；先展示评估，人工批准后才生成材料，失败任务可从持久化步骤恢复。
- 申请材料下载通过后端受控地址完成，前端不会收到私有画像、联系方式或本机绝对路径。
- DeepSeek 和 SMTP 密钥不会进入前端 bundle，接口只返回是否已配置及固定掩码。
- FastAPI 默认仅监听 `127.0.0.1`；服务器远程部署必须额外配置认证和 HTTPS。

## 质量检查

```powershell
npm run lint
npm run build
```

当前 Vite 会提示主 bundle 超过 500 kB，这是性能优化提醒，不影响构建和功能；后续可按路由拆包。
