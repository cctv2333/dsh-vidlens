# 发布（维护者）

两步：**首次发布只能在本地做一次**（包还不存在，npm 没有「包设置」页可配 Trusted Publisher），
**之后全部走 OIDC**，CI 里没有任何长期 token。

## 1. 首次发布（只做一次 · 本地）

```powershell
cd D:\vidlens\vidlens-mcp-dsh
npm login                     # 浏览器授权，或按提示输入 OTP
npm publish --access public   # 账号开了 2FA 会要一次 OTP；这是交互式的，不需要 token
```

成功后包就有了：<https://www.npmjs.com/package/dsh-vidlens>

> 为什么不走 CI：npm 的 Trusted Publisher 配置在**包设置**里，包不存在时没有这个页面。
> 这一步也**不需要**把任何 token 交给 CI。

## 2. 配置 Trusted Publisher（一次性）

1. 打开 <https://www.npmjs.com/package/dsh-vidlens/access>
   （或包页 → **Settings** → **Trusted Publisher**）
2. **Add trusted publisher** → **GitHub Actions**，填：

   | 字段 | 值 |
   |---|---|
   | Organization or user | `cctv2333` |
   | Repository | `dsh-vidlens` |
   | Workflow filename | `release.yml`（只写文件名，带 `.yml`） |
   | Environment name | 留空 |
   | Allowed actions | 勾上 **npm publish** |

3. 保存。
   **注意**：新配置必须在 **2 天内成功发布一次**，否则会过期作废。

## 3. 之后发版（CI，无 token）

```powershell
cd D:\vidlens\vidlens-mcp-dsh
git tag v1.2.1
git push origin v1.2.1
```

`.github/workflows/release.yml` 用 `id-token: write` + Node 24（npm ≥ 11.5.1），
`npm publish` 自动用 OIDC 换短期凭证，并自动生成 provenance（来源证明）。

## 4. 收尾（安全）

- GitHub → Settings → Secrets and variables → Actions → 删除 `NPM_TOKEN`
- <https://www.npmjs.com/settings/~/tokens> → 删掉之前建的 granular token
- 可选强化：包 Settings → **Publishing access** 选
  “Require two-factor authentication and disallow tokens”——Trusted Publisher 不受影响

## 常见失败

| 现象 | 原因 | 处理 |
|---|---|---|
| `ENEEDAUTH` / `Unable to authenticate` | workflow 文件名、repo、environment 任一不符；或没给 `id-token: write` | 逐字核对；workflow 必须叫 `release.yml` |
| 提示 repository 不匹配 | `package.json` 的 `repository.url` 与 GitHub 仓库不一致 | 保持 `git+https://github.com/cctv2333/dsh-vidlens.git` |
| `E409` / `cannot publish over` | 同版本号已存在 | 改 `package.json` version 再打新 tag |
| `403 ... bypass 2fa` | 还在用 token 路径 | 本仓库已切 OIDC；确认 workflow 里没有 `NODE_AUTH_TOKEN` |
| 配置 2 天后失效 | 首次发布没在 2 天内完成 | 删掉重新添加 publisher |
