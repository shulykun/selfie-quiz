# 📸 Селфи-квиз «Бой с кринжем»

Викторина с селфи-камерой: отвечаешь на вопросы в прямом эфире, а на стоп-кадре
получаешь себя с яркими игровыми эффектами в стиле японских шоу.

**Live-версия:** https://rumbik.roborumba.com/quiz/

## Суть проекта

Глупый виральный формат для соцсетей: игрок отвечает голосом или текстом на
5 неловких ситуаций, а ИИ-жюри оценивает кринжовость ответа. После оценки игра
даёт время на позу (`2… 1… ЩЁЛК!`), затем ИИ-сегментация вырезает человека из стоп-кадра,
и результат оформляется как «кадр из японского шоу» — неоновая окантовка,
лучи за головой, комиксный impact burst, слэм-тексты. Каждый раунд уникален: фон выбирается
случайно из 8 вариантов, эффекты разные для победы и поражения. Результат
сохраняется в ленту стоп-кадров и шарится одним тапом.

Подробная архитектура: **[ARCHITECTURE.md](ARCHITECTURE.md)**
Арт-дирекшен Manga × Pop Art: **[VISUAL_STYLE.md](VISUAL_STYLE.md)**

## Фичи

- 🎥 Живое селфи в реальном времени (зеркальный режим)
- 🧠 5 открытых ситуаций с оценкой кринжа от 1 до 10
- 🎯 ИИ-жюри отдельно оценивает качество выхода (`grade`) и добавленный ответом кринж (`cringe`)
- 🎙 Голосовой ответ с таймером и полноценным ручным вводом
- ✂️ Сегментация человека MediaPipe Tasks (ImageSegmenter) — фон отделяется от силуэта
- ⏳ После нажатия «Играть» открывается loading-state; игра запускается только после готовности модели
- 🎆 Manga × Pop Art эффекты: вращающиеся лучи, звёзды, точки, молнии, печатные штрихи,
  слэм-тексты («СУПЕР!», «ОГО!»), вспышки и чередующиеся failure-сцены
  (разбитая панель, чернила, manga-шок и редкий ливень)
- 🎨 4 Manga × Pop Art сцены (radial burst, крупный halftone, speed lines, comic panels) — случайная на каждый ответ
- 🖼 Четырёхслойная sticker-окантовка: ink, paper, цвет результата и белая кромка
- 🖨 Смешанная обработка лица: 4 Manga Portrait + 2 Pop Portrait за раунд, без двух Pop подряд
- 📸 Крупный выбранный стоп-кадр и лента всех кадров на финальном экране
- 🎭 Короткая pose-фаза после оценки ответа: результат → `2` → `1` → `ЩЁЛК!`
- 📤 Кнопка «Поделиться» (Web Share API + фолбэк-скачивание)
- 📱 Мобильная адаптация (touch, safe-area, viewport-fit)
- 🎵 Фоновая музыка на стартовом и финальном экранах с плавной остановкой перед раундом
- 🎴 Полноценный режим без камеры: те же ситуации и оценки, но с Manga × Pop Art карточками вместо селфи
- 💬 Реплика игрока печатается на стоп-кадре и share-картинке; текст ситуации в экспорт не попадает

## Структура

```
index.html                     — весь квиз (один файл, vanilla JS)
assets/audio/clown.mp3         — зацикленная музыка стартового и финального экранов
server_data/cringe_task_base.xlsx — приватная серверная база ситуаций (не коммитится)
vendor/tasks/                  — MediaPipe Tasks (хостится локально, без CDN)
  vision_bundle.mjs
  wasm/vision_wasm_internal.wasm
  wasm/vision_wasm_nosimd_internal.wasm
  selfie_segmenter.tflite
```

Backend читает путь из `CRINGE_TASK_BASE` (по умолчанию
`server_data/cringe_task_base.xlsx`). В игровой пул попадают уникальные записи
с `active = 1`, `paid = 0` и минимальным возрастом не выше 12 лет. Клиент получает
только 5 случайных ситуаций на раунд через `/quiz/api/situations`; Excel и полный
пул нельзя размещать в каталоге статической раздачи.

Модель и WASM лежат рядом с проектом, чтобы не зависеть от CDN (в РФ
jsdelivr/unpkg периодически блокируются).

## Запуск

Просто открыть `index.html` через https (камера работает только в secure context).
Для локальной разработки:

```bash
python3 -m http.server 8000
# затем https://localhost:8000/ (нужен https: python3 -m http.server --ssl-cert ... )
```

Либо раздать папку любым статик-сервером с https.

Режим открытых вопросов дополнительно требует локальное жюри:

```bash
python3 -m pip install -r requirements.txt
DEEPSEEK_TOKEN=... python3 quiz_judge_api.py
```

Локальная страница обращается к `http://127.0.0.1:8003/judge`. В production
используется `/quiz/api/judge`; этот путь нужно проксировать на тот же Flask-сервис.
Маршрут `/quiz/api/situations` также должен проксироваться на Flask-сервис.
Сервис ограничивает тело запроса до 16 КБ и по умолчанию принимает не более
10 оценок в минуту с одного адреса (`QUIZ_JUDGE_RATE_LIMIT`). Если перед сервисом
стоит доверенный reverse proxy, передавайте `X-Forwarded-For` и включите
`QUIZ_JUDGE_TRUST_PROXY=1`; не включайте эту настройку при прямом доступе к Flask.

Для сравнения обработки портрета откройте `?lab=1&style=pop`: после первого
ответа появится переключатель `Original / Pop / Manga`, работающий на текущем
стоп-кадре без повторной сегментации.

## Как работает сегментация

1. После нажатия «Играть» грузится `vision_bundle.mjs` + WASM + модель; переход к камере происходит только после `AI: готово ✓`
2. После оценки ответа камера остаётся живой на время pose-countdown; на `ЩЁЛК!` кадр уходит в `ImageSegmenter.segment()` (дедлайн 20с)
3. Маска (человек) инвертируется в альфу canvas и собирает слои: яркий фон → лучи →
   стоп-кадр человека → тройной неоновый контур → частицы/тексты
4. Если маска не пришла — показывается сообщение об ошибке (без тихого фолбэка)

## Технические детали

- `navigator.mediaDevices.getUserMedia({ facingMode: 'user' })`
- `ctx.globalCompositeOperation = 'destination-in'` / `'destination-out'` для вырезания и дыр
- `ctx.filter = 'blur()'` — только как бонус, эффекты не зависят от его поддержки
- Web Share API: `navigator.share({ files: [...] })`, фолбэк — `<a download>`

## Деплой на сервер

### 1. Статическая часть

В публичный web-root копируются только интерфейс и ресурсы MediaPipe:

```bash
sudo cp index.html /var/www/quiz/
sudo cp -r assets /var/www/quiz/
sudo cp -r vendor /var/www/quiz/
# nginx: /etc/nginx/mime.types должен содержать `application/javascript js mjs;`
```

Не копируйте в `/var/www`, public, static или другой публичный каталог файлы
`cringe_task_base.xlsx`, `server_data/` и любые выгрузки полной базы.

### 2. Приватная база ситуаций

Положите Excel в каталог, который не обслуживается nginx, например:

```bash
sudo install -d -m 750 /srv/selfie-cringe/private
sudo install -m 640 server_data/cringe_task_base.xlsx \
  /srv/selfie-cringe/private/cringe_task_base.xlsx
```

Пользователь, от которого запускается Flask-сервис, должен иметь право читать
этот файл. Excel исключён из Git, поэтому его нужно передавать на сервер отдельно
через защищённый канал.

### 3. Настройки backend

Перед запуском сервиса задайте переменные окружения:

```bash
export DEEPSEEK_TOKEN='...'
export CRINGE_TASK_BASE='/srv/selfie-cringe/private/cringe_task_base.xlsx'
export QUIZ_JUDGE_ORIGIN='https://example.com'
export QUIZ_JUDGE_TRUST_PROXY=1
export QUIZ_JUDGE_RATE_LIMIT=10
export QUIZ_SITUATION_RATE_LIMIT=6
python3 quiz_judge_api.py
```

Секреты лучше хранить в environment-файле с правами `600`, а не в репозитории
или unit-файле. `QUIZ_JUDGE_TRUST_PROXY=1` разрешён только когда Flask недоступен
из интернета напрямую и весь трафик проходит через доверенный reverse proxy.

### 4. Проксирование API в nginx

```nginx
location = /quiz/api/judge {
    client_max_body_size 16k;
    proxy_pass http://127.0.0.1:8003/judge;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location = /quiz/api/situations {
    proxy_pass http://127.0.0.1:8003/situations;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Дополнительная страховка от случайной публикации таблиц.
location ~* \.(xlsx|xls)$ {
    return 404;
}
```

После изменения конфигурации проверьте и перезагрузите nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 5. Проверка приватности и работоспособности

```bash
# Backend запущен и отвечает локально.
curl http://127.0.0.1:8003/health

# Клиент получает только пять ситуаций, а не полную базу.
curl https://example.com/quiz/api/situations

# Прямое скачивание Excel должно вернуть 404.
curl -I https://example.com/quiz/server_data/cringe_task_base.xlsx
curl -I https://example.com/quiz/cringe_task_base.xlsx
```

Ожидаемый ответ `/health`: `{"ok":true}`. В ответе `/situations` должно быть
ровно пять элементов. Оба запроса к `.xlsx` должны вернуть `404`.
