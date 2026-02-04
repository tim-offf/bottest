# Telegram Bot для отслеживания участия

Асинхронный Telegram-бот на **aiogram 3** с хранением данных в **SQLite** через **SQLAlchemy**. Реализует регистрацию участников, ввод кодов, рейтинг, сезонность и админ-команды.

## Возможности

### Пользователи
- `/register ФИО` — регистрация участника.
- Отправка текстового сообщения с кодом — начисление баллов с ограничениями по частоте.
- `/myscore` — текущий счёт и позиция в рейтинге.

### Администратор
- `/admin пароль` — вход в админ-режим.
- `/addcode CODE 1|2` — добавить код.
- `/viewstats` — список участников и баллов.
- `/edituser TG_ID Новое ФИО` — изменить ФИО.
- `/deleteuser TG_ID` — удалить пользователя и историю.
- `/deletecode CODE` — удалить код.
- `/stop_season` — закрыть сезон и зафиксировать топ-5.
- `/notify_winners сообщение` — отправить сообщение победителям.
- `/new_season` — новый сезон, обнуление баллов и очистка кодов.

## Архитектура
```
bot/
├── main.py      # запуск бота
├── db.py        # модели и CRUD
├── handlers.py  # обработчики команд
└── utils.py     # ограничения и утилиты
```

## Быстрый старт

1. Установите зависимости:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Создайте `.env` на основе примера:
   ```bash
   cp .env.example .env
   ```
   Заполните `BOT_TOKEN`, `ADMIN_PASSWORD` и при необходимости `DATABASE_URL`.

3. Запустите бота:
   ```bash
   python -m bot.main
   ```

База данных SQLite (`bot.db`) будет создана автоматически.

## Ограничения безопасности
- После успешного ввода кода — пауза 10 минут.
- После ошибки — пауза 30 секунд.
- Защита от брутфорса: 5 неудачных попыток за минуту.

## Развёртывание в Yandex Cloud (VM)

1. **Создайте VM** в Yandex Cloud (Ubuntu 22.04 LTS) и откройте доступ к интернету.
2. **Подключитесь по SSH**:
   ```bash
   ssh <user>@<public_ip>
   ```
3. **Установите зависимости**:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv git
   ```
4. **Склонируйте репозиторий**:
   ```bash
   git clone <repo_url>
   cd bottest
   ```
5. **Настройте окружение**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   nano .env
   ```
6. **Запустите бота**:
   ```bash
   python -m bot.main
   ```
7. **Запуск как сервис (systemd)**:
   ```bash
   sudo nano /etc/systemd/system/telegram-bot.service
   ```
   Пример unit-файла:
   ```ini
   [Unit]
   Description=Telegram Participation Bot
   After=network.target

   [Service]
   WorkingDirectory=/home/<user>/bottest
   Environment="PATH=/home/<user>/bottest/.venv/bin"
   ExecStart=/home/<user>/bottest/.venv/bin/python -m bot.main
   Restart=always
   User=<user>

   [Install]
   WantedBy=multi-user.target
   ```
   Затем:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now telegram-bot.service
   sudo systemctl status telegram-bot.service
   ```

## Запуск в Docker (Yandex Cloud Container Registry)

1. **Соберите образ**:
   ```bash
   docker build -t yc-bot:latest .
   ```
2. **Проверьте локально (опционально)**:
   ```bash
   docker run --rm --env-file .env yc-bot:latest
   ```
3. **Подготовьте Container Registry** в Yandex Cloud и залогиньтесь:
   ```bash
   yc container registry configure-docker
   ```
4. **Переименуйте образ и отправьте в реестр**:
   ```bash
   docker tag yc-bot:latest cr.yandex/<registry_id>/yc-bot:latest
   docker push cr.yandex/<registry_id>/yc-bot:latest
   ```
5. **Запуск контейнера на VM**:
   ```bash
   docker run -d --name yc-bot --restart unless-stopped --env-file /path/to/.env \\
     cr.yandex/<registry_id>/yc-bot:latest
   ```

## Примечания
- Бот использует один активный сезон. При запуске создаётся сезон, если его нет.
- Победители сохраняются в таблице `winners`.
- Админ-команды логируются в `history`.
