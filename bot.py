import os
import asyncio
import docker
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

class DockerBot:
    def __init__(self):
        self.bot_token = os.getenv('BOT_TOKEN')
        # Опционально: ограничить доступ определенным пользователям
        # self.allowed_users = [int(user_id) for user_id in os.getenv('ALLOWED_USERS', '').split(',') if user_id]
        # Настройка Docker клиента для работы с socket
        try:
            # Проверяем доступность socket
            if not os.path.exists('/var/run/docker.sock'):
                raise Exception("Docker socket не найден: /var/run/docker.sock")
            
            # Используем прямой путь к socket
            self.docker_client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
            # Проверяем подключение к Docker
            self.docker_client.ping()
            print("Docker подключение успешно установлено")
        except Exception as e:
            print(f"Ошибка подключения к Docker: {e}")
            print("Убедитесь, что Docker socket смонтирован в контейнер")
            raise
        
    async def get_containers(self):
        """Получить список контейнеров"""
        try:
            containers = self.docker_client.containers.list(all=True)
            result = []
            for container in containers:
                result.append({
                    'name': container.name,
                    'status': container.status,
                    'image': container.image.tags[0] if container.image.tags else container.image.short_id
                })
            return result
        except Exception as e:
            print(f"Ошибка при получении контейнеров: {e}")
            return []
    
    async def get_container_stats(self):
        """Получить статистику контейнеров"""
        try:
            containers = self.docker_client.containers.list()
            if not containers:
                return "Нет запущенных контейнеров"
            
            stats_text = ""
            for container in containers:
                stats = container.stats(stream=False)
                cpu_percent = self._calculate_cpu_percent(stats)
                memory_percent = self._calculate_memory_percent(stats)
                
                stats_text += f"🟢 {container.name}\n"
                stats_text += f"   CPU: {cpu_percent:.1f}%\n"
                stats_text += f"   Память: {memory_percent:.1f}%\n\n"
            
            return stats_text
        except Exception as e:
            print(f"Ошибка при получении статистики: {e}")
            return "Ошибка при получении статистики"
    
    def _calculate_cpu_percent(self, stats):
        """Вычислить процент использования CPU"""
        try:
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
            cpu_percent = (cpu_delta / system_delta) * len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100.0
            return cpu_percent
        except:
            return 0.0
    
    def _calculate_memory_percent(self, stats):
        """Вычислить процент использования памяти"""
        try:
            memory_usage = stats['memory_stats']['usage']
            memory_limit = stats['memory_stats']['limit']
            return (memory_usage / memory_limit) * 100.0
        except:
            return 0.0
    
    async def start_container(self, container_name):
        """Запустить контейнер"""
        try:
            container = self.docker_client.containers.get(container_name)
            container.start()
            return True
        except Exception as e:
            print(f"Ошибка при запуске контейнера: {e}")
            return False
    
    async def stop_container(self, container_name):
        """Остановить контейнер"""
        try:
            container = self.docker_client.containers.get(container_name)
            container.stop()
            return True
        except Exception as e:
            print(f"Ошибка при остановке контейнера: {e}")
            return False
    
    async def restart_container(self, container_name):
        """Перезапустить контейнер"""
        try:
            container = self.docker_client.containers.get(container_name)
            container.restart()
            return True
        except Exception as e:
            print(f"Ошибка при перезапуске контейнера: {e}")
            return False
    
    async def get_container_logs(self, container_name, lines=20):
        """Получить логи контейнера"""
        try:
            container = self.docker_client.containers.get(container_name)
            logs = container.logs(tail=lines).decode('utf-8')
            return logs
        except Exception as e:
            print(f"Ошибка при получении логов: {e}")
            return f"Ошибка при получении логов: {e}"
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        # Опционально: проверка доступа
        # user_id = update.effective_user.id
        # if hasattr(self, 'allowed_users') and self.allowed_users and user_id not in self.allowed_users:
        #     await update.message.reply_text("❌ У вас нет доступа к этому боту.")
        #     return
        
        keyboard = [
            [InlineKeyboardButton("📋 Список контейнеров", callback_data="list")],
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🐳 *Docker Bot*\n\nВыберите действие:",
            reply_markup=reply_markup,
        )
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "list":
            await self.show_containers(query)
        elif query.data == "stats":
            await self.show_stats(query)
        elif query.data == "back":
            await self.start_menu(query)
        elif query.data.startswith("container_"):
            await self.show_container_info(query)
        elif query.data.startswith("action_"):
            await self.handle_action(query)
    
    async def start_menu(self, query):
        """Показать главное меню"""
        keyboard = [
            [InlineKeyboardButton("📋 Список контейнеров", callback_data="list")],
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🐳 *Docker Bot*\n\nВыберите действие:",
            reply_markup=reply_markup,
        )
    
    async def show_containers(self, query):
        """Показать список контейнеров"""
        containers = await self.get_containers()
        
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
                    f"{'⏹️' if container['status'] == 'running' else '▶️'} {container['name']}",
                    callback_data=f"container_{container['name']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup)
    
    async def show_container_info(self, query):
        """Показать информацию о контейнере"""
        container_name = query.data.split("_")[1]
        
        try:
            container = self.docker_client.containers.get(container_name)
            status = container.status
            
            message = f"🐳 *{container_name}*\n\n"
            message += f"Статус: {status}\n"
            message += f"Образ: {container.image.tags[0] if container.image.tags else container.image.short_id}\n\n"
            
            keyboard = []
            
            if status == 'running':
                keyboard.append([InlineKeyboardButton("⏹️ Остановить", callback_data=f"action_stop_{container_name}")])
                keyboard.append([InlineKeyboardButton("🔄 Перезапустить", callback_data=f"action_restart_{container_name}")])
            else:
                keyboard.append([InlineKeyboardButton("▶️ Запустить", callback_data=f"action_start_{container_name}")])
            
            keyboard.append([InlineKeyboardButton("📝 Логи", callback_data=f"action_logs_{container_name}")])
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="list")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup)
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка при получении информации о контейнере: {e}")
    
    async def handle_action(self, query):
        """Обработка действий с контейнерами"""
        data = query.data.split("_")
        action = data[1]
        container_name = "_".join(data[2:])
        
        if action == "start":
            success = await self.start_container(container_name)
            if success:
                await query.edit_message_text(f"✅ Контейнер {container_name} запущен")
            else:
                await query.edit_message_text(f"❌ Ошибка при запуске контейнера {container_name}")
        elif action == "stop":
            success = await self.stop_container(container_name)
            if success:
                await query.edit_message_text(f"⏹️ Контейнер {container_name} остановлен")
            else:
                await query.edit_message_text(f"❌ Ошибка при остановке контейнера {container_name}")
        elif action == "restart":
            success = await self.restart_container(container_name)
            if success:
                await query.edit_message_text(f"🔄 Контейнер {container_name} перезапущен")
            else:
                await query.edit_message_text(f"❌ Ошибка при перезапуске контейнера {container_name}")
        elif action == "logs":
            logs = await self.get_container_logs(container_name, 20)
            if len(logs) > 3000:
                logs = logs[-3000:] + "\n\n... (показаны последние 20 строк)"
            
            message = f"📝 *Логи {container_name}:*\n\n```\n{logs}\n```"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"container_{container_name}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, reply_markup=reply_markup)
    
    async def show_stats(self, query):
        """Показать статистику"""
        stats_text = await self.get_container_stats()
        
        # Подсчет контейнеров
        containers = await self.get_containers()
        total_containers = len(containers)
        running_containers = len([c for c in containers if c['status'] == 'running'])
        
        message = "📊 *Статистика сервера:*\n\n"
        message += f"🌐 Контейнеры: {running_containers}/{total_containers}\n\n"
        message += stats_text
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup)
    
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
