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

На сервере должен быть установлен Docker. Для подключения по SSH установим `sshpass`:

```bash
# Ubuntu/Debian
sudo apt install sshpass

# CentOS/RHEL
sudo yum install sshpass
```

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
        self.server_host = os.getenv('SERVER_HOST')
        self.server_user = os.getenv('SERVER_USER')
        self.server_password = os.getenv('SERVER_PASSWORD')
        
    async def run_ssh_command(self, command):
        """Выполнить команду через SSH"""
        ssh_command = [
            'sshpass', '-p', self.server_password,
            'ssh', '-o', 'StrictHostKeyChecking=no',
            f'{self.server_user}@{self.server_host}',
            command
        ]
        
        process = await asyncio.create_subprocess_exec(
            *ssh_command,
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
        result = await self.run_ssh_command("docker ps -a --format '{{.Names}}\t{{.Status}}\t{{.Image}}'")
        
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
SERVER_HOST=your_server_ip
SERVER_USER=your_username
SERVER_PASSWORD=your_password
```

> **Примечание**: `SERVER_HOST` - это IP адрес сервера, где запущены ваши Docker контейнеры. Бот подключается к этому серверу по SSH для выполнения Docker команд. Сам бот может работать на любом сервере (даже локально), главное чтобы он мог подключиться к серверу с Docker по SSH.

## Запуск

1. Установите зависимости:
```bash
pip install python-telegram-bot python-dotenv
```

2. Установите sshpass:
```bash
sudo apt install sshpass  # Ubuntu/Debian
```

3. Настройте .env файл

4. Запустите бота:
```bash
python bot.py
```

## Как это работает

1. **SSH подключение** - бот подключается к серверу через SSH
2. **Выполнение команд** - выполняет Docker команды на удаленном сервере
3. **Обработка результатов** - парсит вывод и показывает в Telegram
4. **Интерактивные кнопки** - удобный интерфейс для управления

## Безопасность

- Используйте SSH-ключи вместо паролей
- Ограничьте доступ к боту через список разрешенных пользователей
- Не храните пароли в открытом виде

## Заключение

Мы создали простого, но функционального бота для управления Docker-контейнерами. Код понятный и легко расширяемый. Вы можете добавить новые функции, например:
- Управление Docker Compose
- Мониторинг в реальном времени
- Уведомления о событиях

**Полезные ссылки:**
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [Docker CLI Reference](https://docs.docker.com/engine/reference/commandline/cli/)

Удачи в автоматизации! 🚀
