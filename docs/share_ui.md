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

## Пароль обязателен

Публичный туннель нельзя поднять «молча без пароля». Перед запуском
`share_ui.ps1` проверяет эффективную защиту с приоритетом:

1. `ui/.share-auth.json` (`enabled`, `user`, `password`);
2. `SHARE_AUTH_ENABLED=on|off`;
3. `SHARE_BASIC_AUTH_PASSWORD` в окружении или `ui/.env.local`.

Если защиты нет, скрипт завершается с ошибкой и подсказывает три варианта:
задать `SHARE_BASIC_AUTH_PASSWORD` в `ui/.env.local`, включить пароль
скриптом `scripts\share_auth.ps1 -On -Password '...'` или осознанно
запустить с `-NoAuth` (тогда в консоль печатается предупреждение, что демо
открыто без пароля).

> Если в `ui/.share-auth.json` стоит `"enabled": false`, обычный запуск
> тоже потребует `-NoAuth`: это защита от случайно открытого демо.

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

Если вместо ссылки в логах `connection with edge closed`, а страница отдаёт
`530`/`1033`, попробуйте другой edge и HTTP/2:

```powershell
cloudflared tunnel --url http://localhost:3000 --region us --protocol http2
```

Если и это не помогло — сеть режет Cloudflare-туннели, переходите на
вариант 3 (Serveo).

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

В `ui/.env.local` при этом `SHARE_BASIC_AUTH_PASSWORD` можно оставить
пустым: доступ закрывает Cloudflare Access. Но скрипт требует явного
подтверждения, что защита выключена локально, поэтому запускайте с
`-NoAuth` — иначе он откажется поднимать туннель.

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

## Вариант 3. Serveo: без установки, если Cloudflare не регистрируется

В некоторых сетях (в том числе в этой) quick tunnel Cloudflare отдаёт
`530`/`1033`, а в логах — `connection with edge closed` или
`Register tunnel error ... context deadline exceeded`. Serveo идёт по SSH
и обычно работает там, где Cloudflare-туннель рвётся.

```powershell
ssh -o StrictHostKeyChecking=accept-new -R 80:localhost:3000 serveo.net
```

В выводе будет адрес вида
`https://<id>-<ip-с-дефисами>.serveousercontent.com`. Туннель живёт, пока
открыта SSH-сессия, и меняется после перезапуска.

То же через скрипт (поднимет API, UI и туннель):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\share_ui.ps1 -Serveo
```

Ограничения: бесплатный сервис, без SLA, возможен баннер-заглушка для
некоторых браузеров; ссылка содержит ваш публичный IP. Для учебного демо
с синтетическими данными это приемлемо.

## Вариант 4. ngrok

```powershell
winget install --id ngrok.ngrok
ngrok config add-authtoken <токен из личного кабинета>
ngrok http 3000
```

Адрес будет в строке `Forwarding`. Для dev-режима hostname уже разрешён в
`ui/next.config.ts` (`allowedDevOrigins`).

## Пароль: включение и отключение

Пароль проверяет `ui/proxy.ts`. Есть три уровня управления, по приоритету:

### 1. Горячо, без перезапуска

```powershell
powershell -ExecutionPolicy Bypass -File scripts\share_auth.ps1 -Off
powershell -ExecutionPolicy Bypass -File scripts\share_auth.ps1 -On
powershell -ExecutionPolicy Bypass -File scripts\share_auth.ps1 -Status
```

Скрипт пишет `ui/.share-auth.json`, а прокси читает его на каждом запросе:
изменение действует сразу. Логин и пароль берутся из `ui/.env.local`; можно
задать и в файле: `-On -User demo -Password 'новый-пароль'`.

### 2. На один запуск

```powershell
powershell -ExecutionPolicy Bypass -File scripts\share_ui.ps1 -Serveo -NoAuth
```

`-NoAuth` выставляет `SHARE_AUTH_ENABLED=off` только для этого процесса UI.
Файл `ui/.share-auth.json` всё равно важнее: если в нём `enabled=true`,
пароль останется — удалите файл.

### 3. Постоянно, через окружение

```dotenv
# ui/.env.local
SHARE_BASIC_AUTH_USER=demo
SHARE_BASIC_AUTH_PASSWORD=придумайте-пароль   # пусто = пароль выключен
```

После правки `.env.local` UI нужно перезапустить (в dev-режиме — тоже).
`SHARE_AUTH_ENABLED=off` в окружении отключает пароль, не трогая файл.

Пока пароль включён, браузер получает `401` и стандартное окно входа.
Basic Auth передаёт пароль только по HTTPS — туннели выше дают HTTPS,
локальный `http://localhost` тоже безопасен. Когда пароль выключен,
ссылку может открыть любой, у кого она есть, и потратить лимит LLM
(400 запросов / 3 часа), поэтому отключайте его только на время показа.

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
| `530`/`1033` от Cloudflare, в логах `connection with edge closed` | Туннель не держит соединение: запустите с `--region us --protocol http2` или используйте `scripts\share_ui.ps1 -Serveo`. |
| `403` от Cloudflare Access | Email зрителя не входит в политику `Include → Emails`. |
| Вход через Access идёт по кругу | Не включён login method (One-time PIN) или политика не сохранилась. |
| В dev-режиме `Blocked cross-origin request` | Добавьте hostname туннеля в `allowedDevOrigins` в `ui/next.config.ts` (шаблоны `*.trycloudflare.com`, `*.ngrok-free.app`, `*.loca.lt`, `*.localhost.run` уже есть). |
| Ответ идёт 20–70 секунд | Нормально: UI ждёт `runs/wait`, стриминга нет. Средняя задержка по метрикам — 28 с, p95 — 72 с. |
| `429` от провайдера | Исчерпан лимит free-тарифа, подождите 3 часа. |
