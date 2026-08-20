# GitHub Actions → Aliyun public Next deploy

Public product UI is [http://47.106.33.102](http://47.106.33.102) (auth edge on `:80`, Next on loopback `:3000`).

## What auto-deploys

Workflow: `.github/workflows/deploy-public-next.yml`

| Trigger | Effect |
|---------|--------|
| `workflow_dispatch` | Manual deploy from Actions tab |
| Push to `main` or `assist-keyframe-workflow-20260814` changing `apps/gastric_scan_next/**` | Build reader-only + atomic Aliyun swap |

Local equivalent:

```bash
bash scripts/deploy_public_next.sh
# or reuse an existing build:
bash scripts/deploy_public_next.sh --skip-build
```

## One-time secrets (GitHub repo)

Repo is **public** (`hyjcde/CEUS-Gastric-Tstaging`). Never commit keys or `users.json` passwords.

Settings → Secrets and variables → Actions:

| Secret | Example |
|--------|---------|
| `ALIYUN_SSH_PRIVATE_KEY` | Full PEM of a deploy-only ed25519 key |
| `ALIYUN_SSH_HOST` | `47.106.33.102` |
| `ALIYUN_SSH_USER` | `root` |
| `ALIYUN_SSH_PORT` | `22` (optional) |

### Create a deploy-only key (recommended)

On the workstation:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_gha_aliyun_deploy -N '' -C 'gha-aliyun-deploy'
# authorize on Aliyun (append only this public key)
ssh aliyun-reader 'mkdir -p ~/.ssh && chmod 700 ~/.ssh'
ssh-copy-id -i ~/.ssh/id_ed25519_gha_aliyun_deploy.pub aliyun-reader
# paste PRIVATE key into GitHub secret ALIYUN_SSH_PRIVATE_KEY
cat ~/.ssh/id_ed25519_gha_aliyun_deploy
```

Lock the key on Aliyun if desired (`from=` / `command=` restrictions). Do not reuse your personal interactive key in CI.

## Remote prerequisites (already in use)

- `gastric-next.service` serves `/var/www/gastric-next`
- `gastric-reader.service` (auth) proxies `/` → Next
- Compute tunnel `18768 → workstation :3300` for agent/ops

The Action only swaps the Next UI bundle. It does **not** rotate `GASTRIC_OPS_INGEST_SECRET` or `users.json`.

## LAN workstation auto-deploy (optional later)

Prefer a **self-hosted runner** on the GPU workstation for `:3000`/`:3300`, because LAN needs local runtime data and the Aliyun SSH alias. Until that exists, restart LAN services manually after pull:

```bash
cd /data/research/gastric/GastricTstaging/apps/gastric_scan_next
npm run build
# package standalone static, then:
systemctl --user restart gastric-next.service gastric-next-public.service
```

## Safety

- Do not put `secrets/`, `runtime/`, `users.json`, session secrets, or patient media in git.
- `scripts/deploy_public_next.sh` keeps timestamped `*.bak_YYYYMMDD_HHMMSS` on the server for rollback.
- Rollback on Aliyun:

```bash
ssh aliyun-reader 'systemctl stop gastric-next
# pick bak stamp
STAMP=20260820_1623
mv /var/www/gastric-next/.next-public-deploy-dist /var/www/gastric-next/.next-public-deploy-dist.failed
mv /var/www/gastric-next/.next-public-deploy-dist.bak_$STAMP /var/www/gastric-next/.next-public-deploy-dist
cp -a /var/www/gastric-next/server.js.bak_$STAMP /var/www/gastric-next/server.js
ln -sfn .next-public-deploy-dist /var/www/gastric-next/.next
systemctl start gastric-next'
```
