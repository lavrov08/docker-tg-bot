# Простой Telegram-бот для управления Docker-контейнерами

Привет, Хабр! Сегодня покажу, как создать простого Telegram-бота для управления Docker-контейнерами на удаленном сервере. Это будет полезно для разработчиков, которые хотят быстро перезапустить сервис или посмотреть логи прямо из Telegram.

## Что мы будем делать

Создадим бота, который умеет:
- Показывать список контейнеров
- Запускать и останавливать контейнеры
- Показывать логи
- Работать через SSH с удаленным сервером

## Подготовка

### 1. Создание бота

Идем к [@BotFather](https://t.me/BotFather) в Telegram:
1. Отправляем `/newbot`
2. Придумываем имя: `My Docker Bot`
3. Придумываем username: `my_docker_bot`
4. Получаем токен (сохраняем!)

### 2. Подготовка сервера

На сервере должен быть установлен Docker. Бот будет работать локально на том же сервере, где запущены контейнеры.

## Код бота

### Основной файл bot.py

```python
import os
import asyncio
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

class DockerBot:
    def __init__(self):
        self.bot_token = os.getenv('BOT_TOKEN')
        
    async def run_docker_command(self, command):
        """Выполнить Docker команду локально"""
        process = await asyncio.create_subprocess_exec(
            'docker', *command.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        return stdout.decode() if process.returncode == 0 else stderr.decode()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        keyboard = [
            [InlineKeyboardButton("📋 Список контейнеров", callback_data="list")],
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🐳 *Docker Bot*\n\nВыберите действие:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "list":
            await self.show_containers(query)
        elif query.data == "stats":
            await self.show_stats(query)
        elif query.data.startswith("container_"):
            await self.show_container_info(query)
        elif query.data.startswith("action_"):
            await self.handle_action(query)
    
    async def show_containers(self, query):
        """Показать список контейнеров"""
        result = await self.run_docker_command("ps -a --format '{{.Names}}\t{{.Status}}\t{{.Image}}'")
        
        if not result.strip():
            await query.edit_message_text("📋 Контейнеры не найдены")
            return
        
        message = "📋 *Список контейнеров:*\n\n"
        keyboard = []
        
        for line in result.strip().split('\n'):
            if line:
                parts = line.split('\t')
                if len(parts) >= 3:
                    name, status, image = parts[0], parts[1], parts[2]
                    status_emoji = "🟢" if "Up" in status else "🔴"
                    
                    message += f"{status_emoji} `{name}`\n"
                    message += f"   Статус: {status}\n"
                    message += f"   Образ: {image}\n\n"
                    
                    keyboard.append([
                        InlineKeyboardButton(
                            f"{'⏹️' if 'Up' in status else '▶️'} {name}",
                            callback_data=f"container_{name}"
                        )
                    ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def show_container_info(self, query):
        """Показать информацию о контейнере"""
        container_name = query.data.split("_")[1]
        
        # Получаем статус
        status_result = await self.run_ssh_command(f"docker ps -a --filter name={container_name} --format '{{.Status}}'")
        status = status_result.strip()
        
        message = f"🐳 *{container_name}*\n\n"
        message += f"Статус: {status}\n\n"
        
        keyboard = []
        
        if "Up" in status:
            keyboard.append([InlineKeyboardButton("⏹️ Остановить", callback_data=f"action_stop_{container_name}")])
            keyboard.append([InlineKeyboardButton("🔄 Перезапустить", callback_data=f"action_restart_{container_name}")])
        else:
            keyboard.append([InlineKeyboardButton("▶️ Запустить", callback_data=f"action_start_{container_name}")])
        
        keyboard.append([InlineKeyboardButton("📝 Логи", callback_data=f"action_logs_{container_name}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="list")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def handle_action(self, query):
        """Обработка действий с контейнерами"""
        data = query.data.split("_")
        action = data[1]
        container_name = "_".join(data[2:])
        
        if action == "start":
            await self.run_ssh_command(f"docker start {container_name}")
            await query.edit_message_text(f"✅ Контейнер {container_name} запущен")
        elif action == "stop":
            await self.run_ssh_command(f"docker stop {container_name}")
            await query.edit_message_text(f"⏹️ Контейнер {container_name} остановлен")
        elif action == "restart":
            await self.run_ssh_command(f"docker restart {container_name}")
            await query.edit_message_text(f"🔄 Контейнер {container_name} перезапущен")
        elif action == "logs":
            logs = await self.run_ssh_command(f"docker logs --tail 20 {container_name}")
            if len(logs) > 3000:
                logs = logs[-3000:] + "\n\n... (показаны последние 20 строк)"
            
            message = f"📝 *Логи {container_name}:*\n\n```\n{logs}\n```"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"container_{container_name}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def show_stats(self, query):
        """Показать статистику"""
        result = await self.run_ssh_command("docker stats --no-stream --format '{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}'")
        
        message = "📊 *Статистика сервера:*\n\n"
        
        if result.strip():
            lines = result.strip().split('\n')
            if lines and lines[0]:
                parts = lines[0].split('\t')
                if len(parts) >= 3:
                    cpu = parts[0].replace('%', '')
                    memory = parts[2].replace('%', '')
                    message += f"🖥️ CPU: {cpu}%\n"
                    message += f"💾 Память: {memory}%\n"
        
        # Подсчет контейнеров
        containers_result = await self.run_ssh_command("docker ps -a --format '{{.Names}}'")
        total_containers = len([line for line in containers_result.strip().split('\n') if line.strip()])
        
        running_result = await self.run_ssh_command("docker ps --format '{{.Names}}'")
        running_containers = len([line for line in running_result.strip().split('\n') if line.strip()])
        
        message += f"🌐 Контейнеры: {running_containers}/{total_containers}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    def run(self):
        """Запуск бота"""
        application = Application.builder().token(self.bot_token).build()
        
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CallbackQueryHandler(self.button_handler))
        
        print("Бот запущен...")
        application.run_polling()

if __name__ == "__main__":
    bot = DockerBot()
    bot.run()
```

### Файл requirements.txt

```
python-telegram-bot==20.7
python-dotenv==1.0.0
```

### Файл .env

```env
BOT_TOKEN=your_telegram_bot_token_here
```

## Запуск

1. Установите зависимости:
```bash
pip install python-telegram-bot python-dotenv
```

2. Настройте .env файл

3. Запустите бота:
```bash
python bot.py
```

## Как это работает

1. **Локальное выполнение** - бот выполняет Docker команды локально на сервере
2. **Обработка результатов** - парсит вывод и показывает в Telegram
3. **Интерактивные кнопки** - удобный интерфейс для управления

## Docker Socket - что это такое?

### Основы

**Docker Socket** (`/var/run/docker.sock`) - это Unix-сокет, через который Docker демон общается с клиентами. Это как "дверь" в Docker Engine.

### Как это работает:

1. **На хосте**: Docker демон слушает на `/var/run/docker.sock`
2. **В контейнере**: Монтируем этот сокет внутрь контейнера
3. **Результат**: Контейнер может управлять Docker на хосте

### Практический пример:

```bash
# Без монтирования сокета (внутри контейнера):
docker ps
# Ошибка: Cannot connect to the Docker daemon

# С монтированием сокета:
docker ps
# Работает! Показывает контейнеры хоста
```

### В docker-compose.yml:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock  # Монтируем сокет
```

Эта строка означает: "взять файл `/var/run/docker.sock` с хоста и сделать его доступным внутри контейнера по тому же пути".

### Безопасность Docker Socket:

⚠️ **Важно**: Монтирование Docker socket дает контейнеру **полный доступ** к Docker на хосте. Контейнер может:
- Запускать/останавливать любые контейнеры
- Удалять образы и контейнеры  
- Создавать новые контейнеры
- Получать доступ к файловой системе хоста

**Рекомендации по безопасности:**
- Используйте только для доверенных приложений
- Запускайте контейнер под непривилегированным пользователем
- Ограничьте доступ к боту через Telegram ID
- Регулярно обновляйте Docker и образы

## Безопасность

### Базовые меры
- Запускайте бота под непривилегированным пользователем
- Не храните токены в открытом виде

### Ограничение доступа (опционально)
Если хотите ограничить доступ к боту определенным пользователям:

1. Узнайте свой Telegram ID (отправьте `/start` боту [@userinfobot](https://t.me/userinfobot))
2. Добавьте в `.env`:
```env
ALLOWED_USERS=123456789,987654321
```
3. Раскомментируйте проверки в коде бота

> **Примечание**: Для простоты в примере доступ не ограничен, но в production рекомендуется добавить ограничения.

## Заключение

Мы создали простого, но функционального бота для управления Docker-контейнерами. Код понятный и легко расширяемый. Вы можете добавить новые функции, например:
- Управление Docker Compose
- Мониторинг в реальном времени
- Уведомления о событиях

**Полезные ссылки:**
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [Docker CLI Reference](https://docs.docker.com/engine/reference/commandline/cli/)

Удачи в автоматизации! 🚀
