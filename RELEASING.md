# 发布（维护者）

首次发布用 **staged publishing**（`npm stage publish` **不需要 2FA**，批准时才要）；
之后全部走 **OIDC Trusted Publishing**，CI 里没有任何长期 token。

> 别用 `npm publish` 做首次发布：npm 现在对它强制 2FA，CLI 的 `--otp` 也常被同样拒绝
> （`403 ... bypass 2fa enabled is required`）。

## 1. 首次发布：stage（不需要 2FA）

```powershell
npm --version                     # 需要 >= 11.15.0，低了就 npm i -g npm@latest
cd D:\vidlens\vidlens-mcp-dsh
npm stage publish --access public
npm stage list                    # 记下 id，等 status 变成 staged
```

新包会先在 registry 上生成一个 `0.0.0-stage` 占位版本（公开可见），
真正要发的版本留在 staging 区，**批准后才上线**。

## 2. 批准（要 2FA，只有你能做）

**用命令行，最可靠**（网页的 Staged Packages 入口时有时无，`/package/<name>/staged` 可能 404）：

```powershell
npm stage approve <stage-id>      # 会提示输入 6 位 OTP
npm view dsh-vidlens versions     # 批准后应能看到目标版本
```

> OTP 只有 30 秒有效，输慢了就重来。
> 如果 2FA 是「安全密钥（WebAuthn）」而不是验证器 App，CLI 无法输入 OTP——
> 先把 npm 账号的 2FA 改成 TOTP（Authenticator app）再重试。

## 3. 配置 Trusted Publisher（一次性）

1. 打开 <https://www.npmjs.com/package/dsh-vidlens/access>
   （或包页 → **Settings** → **Trusted Publisher**）
2. **Add trusted publisher** → **GitHub Actions**，填：

   | 字段 | 值 |
   |---|---|
   | Organization or user | `cctv2333` ← **GitHub** 用户名（不是 npm 的 `ghost120`） |
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
