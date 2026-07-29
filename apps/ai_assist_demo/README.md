# AI Assist Demo — human_assist_v2

Deployable copy of the public trial page `human_assist_v2.html` (胃充盈超声 人机互助阅片).

## Language switch

Header includes an **EN / 中文** button (`#btnLangSwitch`) that:

- Persists preference in `localStorage.gastric_reader_lang` (same key as the reader study)
- Translates chrome UI via `data-i18n*`
- Sends `lang` to `/api/llm/assist-report` from the current preference
- Dispatches `reader:langchange` for compatibility with `reader_i18n.js`

## Deploy to `47.106.33.102`

```bash
export DEPLOY_HOST=47.106.33.102
export DEPLOY_USER=root          # or your SSH user
export DEPLOY_PATH=/path/to/web/root   # directory that serves human_assist_v2.html
./scripts/deploy_human_assist_v2.sh
```

Or with an explicit key:

```bash
DEPLOY_SSH_KEY=~/.ssh/id_ed25519 DEPLOY_PATH=/var/www/gastric ./scripts/deploy_human_assist_v2.sh
```

After deploy, open: `http://47.106.33.102/human_assist_v2.html` and use the **EN** button in the top-right.
