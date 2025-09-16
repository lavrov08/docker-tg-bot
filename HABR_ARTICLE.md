# Создаем Telegram-бота для управления Docker-контейнерами на VDS

Привет, Хабр! Сегодня расскажу, как создать Telegram-бота для управления Docker-контейнерами на удаленном сервере. Это будет полезно для DevOps-инженеров, разработчиков и всех, кто хочет автоматизировать рутинные операции с контейнерами.

## Зачем это нужно?

Представьте ситуацию: у вас есть несколько проектов, развернутых в Docker-контейнерах на VDS. Иногда нужно:
- Перезапустить сервис
- Посмотреть логи
- Проверить статус контейнеров
- Обновить приложение

Обычно для этого нужно подключаться по SSH, что не всегда удобно, особенно когда вы не за компьютером. Telegram-бот решает эту проблему — вы можете управлять контейнерами прямо из мессенджера.

## Архитектура решения

Наше решение состоит из трех компонентов:

1. **Telegram-бот** — интерфейс для пользователя
2. **Docker Client** — класс для работы с Docker через SSH
3. **VDS с Docker** — сервер, где развернуты контейнеры

```
[Пользователь] → [Telegram Bot] → [SSH] → [VDS] → [Docker]
```

## Настройка окружения

### 1. Создание Telegram-бота

Сначала создадим бота через @BotFather:

1. Отправляем `/newbot`
2. Указываем имя и username бота
3. Получаем токен

### 2. Подготовка сервера

На VDS должен быть установлен Docker. Для подключения по SSH установим `sshpass`:

```bash
# Ubuntu/Debian
sudo apt install sshpass

# CentOS/RHEL
sudo yum install sshpass
```

### 3. Установка зависимостей

```bash
pip install python-telegram-bot python-dotenv psutil
```

## Реализация

### Docker Client

Создадим класс для работы с Docker через SSH:

```python
import asyncio
import subprocess
import json
from typing import List, Dict, Any

class DockerClient:
    def __init__(self):
        self.host = os.getenv('SERVER_HOST')
        self.user = os.getenv('SERVER_USER')
        self.password = os.getenv('SERVER_PASSWORD')
        
    async def _run_ssh_command(self, command: str) -> str:
        """Выполнить команду через SSH"""
        ssh_command = [
            'sshpass', '-p', self.password,
            'ssh', '-o', 'StrictHostKeyChecking=no',
            f'{self.user}@{self.host}',
            command
        ]
        
        process = await asyncio.create_subprocess_exec(
            *ssh_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"SSH команда завершилась с ошибкой: {stderr.decode()}")
            
        return stdout.decode()
```

### Основные методы

```python
async def get_containers(self) -> List[Dict[str, Any]]:
    """Получить список контейнеров"""
    command = "docker ps -a --format '{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}'"
    result = await self._run_ssh_command(command)
    
    containers = []
    for line in result.strip().split('\n'):
        if line:
            parts = line.split('\t')
            if len(parts) >= 4:
                containers.append({
                    'id': parts[0],
                    'name': parts[1],
                    'status': parts[2],
                    'image': parts[3]
                })
    
    return containers

async def start_container(self, container_id: str) -> bool:
    """Запустить контейнер"""
    command = f"docker start {container_id}"
    await self._run_ssh_command(command)
    return True

async def stop_container(self, container_id: str) -> bool:
    """Остановить контейнер"""
    command = f"docker stop {container_id}"
    await self._run_ssh_command(command)
    return True
```

### Telegram Bot

Основной класс бота:

```python
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

class TelegramDockerBot:
    def __init__(self):
        self.bot_token = os.getenv('BOT_TOKEN')
        self.allowed_users = [int(user_id) for user_id in os.getenv('ALLOWED_USERS', '').split(',') if user_id]
        self.docker_client = DockerClient()
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = update.effective_user.id
        
        if self.allowed_users and user_id not in self.allowed_users:
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return
            
        keyboard = [
            [InlineKeyboardButton("📋 Список контейнеров", callback_data="list_containers")],
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton("🏷️ Образы", callback_data="list_images")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🐳 *Docker Manager Bot*\n\nВыберите действие:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
```

### Обработка действий с контейнерами

```python
async def show_containers(self, query):
    """Показать список контейнеров"""
    try:
        containers = await self.docker_client.get_containers()
        
        if not containers:
            await query.edit_message_text("📋 Контейнеры не найдены")
            return
            
        message = "📋 *Список контейнеров:*\n\n"
        keyboard = []
        
        for container in containers:
            status_emoji = "🟢" if container['status'] == 'running' else "🔴"
            message += f"{status_emoji} `{container['name']}`\n"
            message += f"   Статус: {container['status']}\n"
            message += f"   Образ: {container['image']}\n\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{'⏹️' if container['status'] == 'running' else '▶️'} {container['name'][:20]}",
                    callback_data=f"container_{container['id']}"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка при получении контейнеров: {e}")
        await query.edit_message_text("❌ Ошибка при получении списка контейнеров")
```

## Безопасность

### 1. Ограничение доступа

```python
# В .env файле
ALLOWED_USERS=123456789,987654321

# В коде
if self.allowed_users and user_id not in self.allowed_users:
    await update.message.reply_text("❌ У вас нет доступа к этому боту.")
    return
```

### 2. Использование SSH-ключей

Вместо пароля лучше использовать SSH-ключи:

```python
async def _run_ssh_command(self, command: str) -> str:
    ssh_command = [
        'ssh', '-i', '/path/to/private/key',
        f'{self.user}@{self.host}',
        command
    ]
    # ...
```

### 3. Валидация команд

```python
def _validate_docker_command(self, command: str) -> bool:
    """Проверить, что команда безопасна"""
    allowed_commands = ['docker ps', 'docker start', 'docker stop', 'docker restart', 'docker logs']
    return any(command.startswith(cmd) for cmd in allowed_commands)
```

## Docker Compose поддержка

### 1. Поиск compose файлов

```python
async def find_compose_files(self) -> List[Dict[str, str]]:
    """Найти все docker-compose.yml файлы на сервере"""
    command = "find / -name 'docker-compose.yml' -o -name 'docker-compose.yaml' 2>/dev/null | head -20"
    result = await self._run_ssh_command(command)
    
    compose_files = []
    for line in result.strip().split('\n'):
        if line and line.strip():
            path = line.strip()
            directory = os.path.dirname(path)
            compose_files.append({
                'path': path,
                'directory': directory,
                'name': os.path.basename(directory)
            })
    
    return compose_files
```

### 2. Управление сервисами

```python
async def get_compose_status(self, compose_dir: str) -> Dict[str, Any]:
    """Получить статус сервисов в docker-compose"""
    command = "docker-compose ps --format json"
    result = await self._run_ssh_command(command, compose_dir)
    
    # Парсинг JSON результата...
    return {
        'directory': compose_dir,
        'services': services,
        'total_services': len(services),
        'running_services': len([s for s in services if s['state'] == 'running'])
    }
```

### 3. Операции с compose

```python
async def start_compose_services(self, compose_dir: str, services: List[str] = None) -> bool:
    """Запустить сервисы docker-compose"""
    if services:
        command = f"docker-compose up -d {' '.join(services)}"
    else:
        command = "docker-compose up -d"
    
    await self._run_ssh_command(command, compose_dir)
    return True

async def scale_compose_service(self, compose_dir: str, service: str, replicas: int) -> bool:
    """Масштабировать сервис docker-compose"""
    command = f"docker-compose up -d --scale {service}={replicas}"
    await self._run_ssh_command(command, compose_dir)
    return True
```

## Расширение функциональности

### 1. Мониторинг ресурсов

```python
async def get_stats(self) -> Dict[str, Any]:
    """Получить статистику сервера"""
    command = "docker stats --no-stream --format '{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}'"
    result = await self._run_ssh_command(command)
    
    # Парсинг результата...
    return {
        'cpu_percent': cpu_percent,
        'memory_percent': memory_percent,
        'containers': f"{running_containers}/{total_containers}"
    }
```

### 2. Просмотр логов

```python
async def get_container_logs(self, container_id: str, lines: int = 50) -> str:
    """Получить логи контейнера"""
    command = f"docker logs --tail {lines} {container_id}"
    return await self._run_ssh_command(command)
```

### 3. Управление образами

```python
async def get_images(self) -> List[Dict[str, Any]]:
    """Получить список образов"""
    command = "docker images --format '{{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}'"
    result = await self._run_ssh_command(command)
    
    # Парсинг результата...
    return images
```

## Контейнеризация бота

### 1. Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    sshpass \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Создание пользователя для безопасности
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# Переменные окружения
ENV PYTHONUNBUFFERED=1

# Команда по умолчанию
CMD ["python", "bot_with_compose.py"]
```

### 2. Docker Compose

```yaml
version: '3.8'

services:
  telegram-docker-bot:
    build: .
    container_name: telegram-docker-bot
    restart: unless-stopped
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
      - SERVER_HOST=${SERVER_HOST}
      - SERVER_USER=${SERVER_USER}
      - SERVER_PASSWORD=${SERVER_PASSWORD}
      - ALLOWED_USERS=${ALLOWED_USERS}
    volumes:
      - ./logs:/app/logs
    networks:
      - bot-network
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    container_name: telegram-bot-redis
    restart: unless-stopped
    volumes:
      - redis_data:/data
    networks:
      - bot-network

volumes:
  redis_data:

networks:
  bot-network:
    driver: bridge
```

### 3. Запуск в Docker

```bash
# Клонирование репозитория
git clone https://github.com/your-username/telegram-docker-bot.git
cd telegram-docker-bot

# Настройка переменных окружения
cp env.example .env
# Отредактируйте .env файл

# Запуск
docker-compose up -d

# Просмотр логов
docker-compose logs -f telegram-docker-bot
```

## Запуск и тестирование

### 1. Настройка переменных окружения

Создайте файл `.env`:

```env
BOT_TOKEN=your_telegram_bot_token
SERVER_HOST=your_server_ip
SERVER_USER=your_username
SERVER_PASSWORD=your_password
ALLOWED_USERS=123456789,987654321
```

### 2. Запуск бота

```bash
python bot.py
```

### 3. Тестирование

1. Отправьте `/start` боту
2. Проверьте список контейнеров
3. Попробуйте запустить/остановить контейнер
4. Посмотрите логи

## Потенциальные улучшения

### 1. Webhook вместо polling

```python
# Для production лучше использовать webhook
application.run_webhook(
    listen="0.0.0.0",
    port=8443,
    webhook_url="https://yourdomain.com/webhook"
)
```

### 2. База данных для логирования

```python
import sqlite3

class DatabaseLogger:
    def __init__(self):
        self.conn = sqlite3.connect('bot_logs.db')
        self._create_tables()
    
    def log_action(self, user_id: int, action: str, container_id: str):
        # Логирование действий пользователя
        pass
```

### 3. Уведомления о событиях

```python
async def monitor_containers(self):
    """Мониторинг контейнеров в фоне"""
    while True:
        containers = await self.docker_client.get_containers()
        # Проверка изменений статуса
        # Отправка уведомлений
        await asyncio.sleep(60)
```

## Заключение

Мы создали полнофункционального Telegram-бота для управления Docker-контейнерами. Основные преимущества:

- ✅ Удобный интерфейс через Telegram
- ✅ Безопасность через ограничение доступа
- ✅ Асинхронная работа
- ✅ Расширяемость

Код доступен в репозитории и готов к использованию. Вы можете адаптировать его под свои нужды, добавив новые функции или изменив интерфейс.

**Полезные ссылки:**
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [Docker CLI Reference](https://docs.docker.com/engine/reference/commandline/cli/)
- [SSH Key Authentication](https://www.ssh.com/academy/ssh/key)

Удачи в автоматизации! 🚀
