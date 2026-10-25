# 发布（维护者）

> GitHub 新版界面：入口在仓库 **Settings → 最下面「Security and quality」→ Secrets and variables → Actions**。
> 直达链接（打开就是这个页面）：
> <https://github.com/cctv2333/dsh-vidlens/settings/secrets/actions>
>
> 点右栏 **Repository secrets** 下面的绿色按钮 **New repository secret**。

## 0. 一次性准备：npm token

1. 注册 / 登录 <https://www.npmjs.com>
2. 创建 token：<https://www.npmjs.com/settings/~/tokens> → **Generate New Token**
   - 选 **Granular Access Token**
   - **Permissions**: `Read and write`
   - **Packages**: `All packages`（首次 `dsh-vidlens` 还不存在，只能这样）
   - 可选：设一个短有效期（比如 30 天），发完就删
   - 值以 `npm_` 开头，**只显示一次**
3. 写进 GitHub：<https://github.com/cctv2333/dsh-vidlens/settings/secrets/actions/new>
   - **Name**: `NPM_TOKEN`
   - **Secret**: 粘贴上面那串 `npm_...`
   - 点 **Add secret**

> npm 目前仍需 token；PyPI 那边可以用 OIDC 免 token（见 `cctv2333/vidlens` 的 `RELEASING.md`）。

## 1. 发版

```bash
cd D:\vidlens\vidlens-mcp-dsh
git tag v1.2.0          # 必须是 v* 开头
git push origin v1.2.0
```

`release.yml` 会：`npm pack` → `npm publish --access public` → 把 tgz 挂到 GitHub Release。

## 2. 验证

- Actions：<https://github.com/cctv2333/dsh-vidlens/actions/workflows/release.yml>
- npm：<https://www.npmjs.com/package/dsh-vidlens>
- 用户侧：

```bash
dsh plugin --profile desktop add dsh-vidlens
# 或
plugin_manager action=install_bundle target=dsh-vidlens
```

## 3. 常见失败

| 现象 | 原因 | 处理 |
|---|---|---|
| `404 Not Found - PUT ...` | token 没有该包写权限 / 包名已被占用 | 确认 granular token 为 `All packages` + read/write；`npm view dsh-vidlens` 确认没被抢 |
| `403 Forbidden` + `two-factor` | 账号开了 2FA 但用的是 legacy token | 改用 granular token（可绕过发布时的 2FA） |
| `E409` / `cannot publish over` | 同版本号已存在 | 改 `package.json` 的 version 再打 tag |
| CI 里 selftest 失败 | `cctv2333/vidlens` 私有或被删 | 两个仓库都必须是 public，或给 checkout 加 token |
