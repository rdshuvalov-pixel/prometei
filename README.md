# prometei

## Vercel (если видишь `404: NOT_FOUND` при успешном Deploy)

1. **Project → Settings → General → Root Directory:** `apps/web` (не `app`, не корень репо).
2. **Build & Development → Framework Preset:** **Next.js** (не «Other» / не Static).
3. **Output Directory:** оставь **пустым** (дефолт Next на Vercel). Любой кастомный `dist`/`out`/`public` ломает выдачу.
4. Открой **точный** Production URL из вкладки **Deployments → последний деплой → Visit** (не старый preview-URL).
5. Если включена **Deployment Protection** (SSO), без входа в Vercel может быть не тот ответ — для проверки временно ослабь защиту или залогинься.

После смены настроек — **Redeploy** без кэша (сними галку *Use existing Build Cache*).
