# Показать интерфейс по публичной ссылке

Инструкция для случая «нужно, чтобы человек с другого компьютера открыл мой
чат в браузере». Это демонстрационный режим: локальные процессы остаются
локальными, наружу выставляется один HTTPS-туннель.

## Как это устроено

```text
браузер зрителя
   │  https://<случайное-имя>.trycloudflare.com
   ▼
туннель cloudflared
   ▼
Next.js UI  http://localhost:3000
   │  /api/threads/...  (same-origin прокси, белый список путей)
   ▼
LangGraph API  http://127.0.0.1:2024
   ▼
PostgreSQL (pgserver) + LLM-провайдер
```

Туннелируется **только порт 3000**. Браузер зрителя обращается к
`/api/...` на том же домене, что и страница, а Next-прокси
`ui/app/api/[..._path]/route.ts` пересылает запросы на локальный
`127.0.0.1:2024`.

Так сделано потому, что клиентский код выполняется в браузере: если
`NEXT_PUBLIC_LANGGRAPH_API_URL` равен `http://127.0.0.1:2024`, то у зрителя
запросы уйдут на **его** компьютер и интерфейс не заработает. Поэтому в
`ui/.env.local` стоит:

```dotenv
NEXT_PUBLIC_LANGGRAPH_API_URL=/api
NEXT_PUBLIC_LANGGRAPH_ASSISTANT_ID=audit_assistant
LANGGRAPH_API_URL=http://127.0.0.1:2024
```

## Что подготовить заранее

1. Заполнить `.env` (`OPENAI_API_KEY`) по README.
2. Сгенерировать данные, поднять БД и индекс:

   ```powershell
   .venv\Scripts\python.exe scripts\generate_data.py --deviations
   .venv\Scripts\python.exe scripts\init_db.py --reset-db --yes --seed
   .venv\Scripts\python.exe scripts\build_index.py --hash
   ```

3. Проверить локально, что чат отвечает: `langgraph dev` + `npm run dev`,
   открыть `http://localhost:3000` и задать вопрос.

## Вариант 1. cloudflared (рекомендуется)

Бесплатно, без регистрации, HTTPS и случайный адрес `*.trycloudflare.com`.
Ничего настраивать в аккаунте не нужно.

Установка (один раз, затем перезапустить терминал):

```powershell
winget install --id Cloudflare.cloudflared
```

Ручной запуск в трёх терминалах:

```powershell
# 1. API графа
.venv\Scripts\langgraph.exe dev --port 2024 --no-browser

# 2. UI (production-сборка стабильнее dev-режима)
npm --prefix ui run build
npm --prefix ui run start

# 3. туннель
cloudflared tunnel --url http://localhost:3000
```

`cloudflared` напечатает в рамке адрес вида
`https://quiet-river-1234.trycloudflare.com` — его и отправляйте зрителю.
Ссылка живёт, пока запущен `cloudflared`; после перезапуска она другая.

Одной командой (сам поднимет API, соберёт и запустит UI, откроет туннель):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\share_ui.ps1
```

Полезные ключи: `-Dev` — без production-сборки, `-NoBuild` — использовать
готовый `.next`. `Ctrl+C` останавливает все три процесса.

## Вариант 2. Постоянный адрес и Cloudflare Access (нужен домен)

Quick tunnel (`*.trycloudflare.com`) через Access закрыть **нельзя**: это
чужой домен, политики Access применяются только к зонам вашего аккаунта.
Поэтому нужен свой домен в Cloudflare и named-туннель.

Бесплатный Zero Trust закрывает до **50 пользователей** (`$0`); дальше —
около `$7` за пользователя в месяц. Для демо этого с запасом.

### Один раз настроить

1. Домен добавлен в Cloudflare и его NS уже указывают на Cloudflare.
   Если для будущего hostname уже есть A/AAAA/CNAME-запись — удалите её,
   иначе `route dns` не сможет создать CNAME туннеля.
2. Установить `cloudflared` и авторизоваться (откроется браузер, выберите
   зону; создастся `%USERPROFILE%\.cloudflared\cert.pem`):

   ```powershell
   winget install --id Cloudflare.cloudflared
   cloudflared tunnel login
   ```

3. Создать туннель и запомнить его UUID:

   ```powershell
   cloudflared tunnel create audit-demo
   ```

4. Скопировать `docs/cloudflared.example.yml` в
   `%USERPROFILE%\.cloudflared\config.yml` и подставить UUID и hostname:

   ```yaml
   tunnel: audit-demo
   credentials-file: C:/Users/<you>/.cloudflared/<TUNNEL-ID>.json
   ingress:
     - hostname: demo.example.com
       service: http://localhost:3000
     - service: http_status:404
   ```

5. Привязать DNS (создаст проксируемую CNAME-запись):

   ```powershell
   cloudflared tunnel route dns audit-demo demo.example.com
   ```

6. В дашборде Cloudflare: **Zero Trust → Settings → Authentication →
   Login methods** → включить **One-time PIN** (или Google/GitHub).
   Отдельного пароля не нужно: код приходит на email.

7. **Zero Trust → Access → Applications → Add an application →
   Self-hosted**:
   - Application domain: `demo.example.com`;
   - Session duration: например, 8 часов;
   - Policy `Allow`, Include → **Emails** → список адресов, кому можно.

### Запуск

```powershell
powershell -ExecutionPolicy Bypass -File scripts\share_ui.ps1 `
  -TunnelName audit-demo -Hostname demo.example.com
```

Скрипт поднимет API и UI, запустит named-туннель и проверит, что hostname
отвечает. Адрес постоянный: `https://demo.example.com`.

Зритель открывает ссылку, вводит свой email, получает код, вводит его — и
попадает в чат. Доступ отзывается удалением адреса из политики; в Access
видно, кто и когда заходил.

В `ui/.env.local` при этом `SHARE_BASIC_AUTH_PASSWORD` оставьте пустым,
иначе будет два экрана входа подряд.

### Важное ограничение Cloudflare: 100 секунд

Cloudflare закрывает запрос, если origin не ответил за **100 секунд**
(ошибка 524). У проекта средняя задержка 28 с, p95 — 72 с, поэтому
изредка долгий ответ может не дойти. Что делать:

- повторить вопрос (нить и история сохраняются);
- задавать более узкие вопросы;
- либо перевести UI с `runs/wait` на `runs/stream` — тогда первые байты
  уходят сразу и лимит не срабатывает (это отдельная доработка
  `ui/app/MyRuntimeProvider.tsx`).

### Автозапуск (необязательно)

```powershell
cloudflared service install
```

Служба поднимет туннель при старте Windows, но API и UI всё равно нужно
запускать отдельно.

## Вариант 3. Без установки: SSH-туннель

Подходит, если нельзя ставить программы. Нужен только `ssh` (в Windows
уже есть).

```powershell
ssh -R 80:localhost:3000 nokey@localhost.run
```

В выводе будет адрес `https://<...>.localhost.run`. Бесплатный туннель
живёт около часа и закрывается вместе с SSH-сессией. Это сторонний сервис:
не используйте его для чего-либо, кроме синтетического демо.

## Вариант 4. ngrok

```powershell
winget install --id ngrok.ngrok
ngrok config add-authtoken <токен из личного кабинета>
ngrok http 3000
```

Адрес будет в строке `Forwarding`. Для dev-режима hostname уже разрешён в
`ui/next.config.ts` (`allowedDevOrigins`).

## Пароль на ссылку

Это альтернатива Cloudflare Access для быстрого туннеля, когда домена нет.
По умолчанию ссылку может открыть любой, кто её получил. Чтобы закрыть
демо паролем, добавьте в `ui/.env.local`:

```dotenv
SHARE_BASIC_AUTH_USER=demo
SHARE_BASIC_AUTH_PASSWORD=придумайте-пароль
```

и перезапустите UI. Пароль проверяет `ui/proxy.ts`: без него браузер
получит `401` и стандартное окно входа. Basic Auth передаёт пароль только
по HTTPS — туннели выше дают HTTPS, локальный `http://localhost` тоже
безопасен.

## Ограничения и безопасность

- **Лимит провайдера.** На free-тарифе NeuralDeep — 400 чат-запросов на
  3 часа. Любой, у кого есть ссылка, тратит этот лимит. Пароль и короткое
  время жизни ссылки — обязательные меры для публичной демонстрации.
- **Наружу идёт только UI.** Не туннелируйте порт 2024: у LangGraph API
  нет аутентификации, и тогда будут доступны все эндпоинты, а не только
  белый список из `ui/app/api/[..._path]/route.ts`.
- **Данные синтетические.** Проект учебный; реальные данные банка в демо
  не подключайте. Guardrails блокируют изменение данных и PII, но это не
  замена изоляции.
- **Логи и провайдер.** Вопросы уходят в LLM-провайдер и остаются в логах
  (`logs/`, `reports/`). Не вводите через публичную ссылку секреты.
- **Ссылка случайная и временная.** Не публикуйте её в открытых каналах;
  после демонстрации остановите туннель.
- **Нет rate limit.** При желании ограничьте доступ через Cloudflare
  Access (нужен свой домен) или поставьте пароль выше.

## Если что-то не работает

| Симптом | Причина и решение |
|---|---|
| `Ошибка: Failed to fetch`, пустой ответ | `NEXT_PUBLIC_LANGGRAPH_API_URL` всё ещё `http://127.0.0.1:2024`. Поставьте `/api` и перезапустите UI (в production — пересоберите). |
| `401` по кругу | Неверный `SHARE_BASIC_AUTH_PASSWORD`/`_USER` или UI не перезапущен после правки `.env.local`. |
| `502` от `/api/...` | LangGraph не запущен или `LANGGRAPH_API_URL` указывает не туда. Проверьте `http://127.0.0.1:2024/ok`. |
| `524` от Cloudflare | Запрос шёл дольше 100 с (см. раздел про Cloudflare Access). Повторите вопрос или сузьте его. |
| `403` от Cloudflare Access | Email зрителя не входит в политику `Include → Emails`. |
| Вход через Access идёт по кругу | Не включён login method (One-time PIN) или политика не сохранилась. |
| В dev-режиме `Blocked cross-origin request` | Добавьте hostname туннеля в `allowedDevOrigins` в `ui/next.config.ts` (шаблоны `*.trycloudflare.com`, `*.ngrok-free.app`, `*.loca.lt`, `*.localhost.run` уже есть). |
| Ответ идёт 20–70 секунд | Нормально: UI ждёт `runs/wait`, стриминга нет. Средняя задержка по метрикам — 28 с, p95 — 72 с. |
| `429` от провайдера | Исчерпан лимит free-тарифа, подождите 3 часа. |
