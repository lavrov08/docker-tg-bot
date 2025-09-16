import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from docker_client import DockerClient
from docker_compose_client import DockerComposeClient
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramDockerBot:
    def __init__(self):
        self.bot_token = os.getenv('BOT_TOKEN')
        self.allowed_users = [int(user_id) for user_id in os.getenv('ALLOWED_USERS', '').split(',') if user_id]
        self.docker_client = DockerClient()
        self.compose_client = DockerComposeClient()
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = update.effective_user.id
        
        if self.allowed_users and user_id not in self.allowed_users:
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return
            
        keyboard = [
            [InlineKeyboardButton("📋 Контейнеры", callback_data="list_containers")],
            [InlineKeyboardButton("🐙 Docker Compose", callback_data="compose_menu")],
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton("🏷️ Образы", callback_data="list_images")],
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🐳 *Docker Manager Bot*\n\n"
            "Выберите действие:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        if self.allowed_users and user_id not in self.allowed_users:
            await query.edit_message_text("❌ У вас нет доступа к этому боту.")
            return
            
        if query.data == "list_containers":
            await self.show_containers(query)
        elif query.data == "compose_menu":
            await self.show_compose_menu(query)
        elif query.data == "stats":
            await self.show_stats(query)
        elif query.data == "list_images":
            await self.show_images(query)
        elif query.data == "refresh":
            await self.refresh_menu(query)
        elif query.data.startswith("container_"):
            await self.handle_container_action(query)
        elif query.data.startswith("compose_"):
            await self.handle_compose_action(query)

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
                status_emoji = "🟢" if container['status'].startswith('Up') else "🔴"
                message += f"{status_emoji} `{container['name']}`\n"
                message += f"   Статус: {container['status']}\n"
                message += f"   Образ: {container['image']}\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"{'⏹️' if container['status'].startswith('Up') else '▶️'} {container['name'][:20]}",
                        callback_data=f"container_{container['id']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="refresh")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка при получении контейнеров: {e}")
            await query.edit_message_text("❌ Ошибка при получении списка контейнеров")

    async def show_compose_menu(self, query):
        """Показать меню Docker Compose"""
        try:
            compose_files = await self.compose_client.find_compose_files()
            
            if not compose_files:
                await query.edit_message_text("🐙 Docker Compose файлы не найдены")
                return
                
            message = "🐙 *Docker Compose проекты:*\n\n"
            keyboard = []
            
            for compose_file in compose_files:
                message += f"📁 `{compose_file['name']}`\n"
                message += f"   Путь: {compose_file['directory']}\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"📁 {compose_file['name'][:25]}",
                        callback_data=f"compose_status_{compose_file['directory']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="refresh")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка при получении compose файлов: {e}")
            await query.edit_message_text("❌ Ошибка при получении Docker Compose проектов")

    async def handle_compose_action(self, query):
        """Обработка действий с Docker Compose"""
        data = query.data.split("_")
        
        if data[1] == "status":
            compose_dir = "_".join(data[2:])  # Восстанавливаем путь с подчеркиваниями
            await self.show_compose_status(query, compose_dir)
        elif data[1] == "start":
            compose_dir = "_".join(data[2:])
            await self.start_compose_services(query, compose_dir)
        elif data[1] == "stop":
            compose_dir = "_".join(data[2:])
            await self.stop_compose_services(query, compose_dir)
        elif data[1] == "restart":
            compose_dir = "_".join(data[2:])
            await self.restart_compose_services(query, compose_dir)
        elif data[1] == "logs":
            compose_dir = "_".join(data[2:])
            await self.show_compose_logs(query, compose_dir)

    async def show_compose_status(self, query, compose_dir):
        """Показать статус Docker Compose проекта"""
        try:
            status = await self.compose_client.get_compose_status(compose_dir)
            
            message = f"🐙 *{os.path.basename(compose_dir)}*\n\n"
            message += f"📊 Всего сервисов: {status['total_services']}\n"
            message += f"🟢 Запущено: {status['running_services']}\n\n"
            
            if status['services']:
                message += "*Сервисы:*\n"
                for service in status['services']:
                    status_emoji = "🟢" if service['state'] == 'running' else "🔴"
                    message += f"{status_emoji} `{service['name']}`\n"
                    message += f"   Статус: {service['state']}\n"
                    if service['ports']:
                        message += f"   Порты: {service['ports']}\n"
                    message += "\n"
            
            keyboard = [
                [InlineKeyboardButton("▶️ Запустить все", callback_data=f"compose_start_{compose_dir}")],
                [InlineKeyboardButton("⏹️ Остановить все", callback_data=f"compose_stop_{compose_dir}")],
                [InlineKeyboardButton("🔄 Перезапустить все", callback_data=f"compose_restart_{compose_dir}")],
                [InlineKeyboardButton("📝 Логи", callback_data=f"compose_logs_{compose_dir}")],
                [InlineKeyboardButton("🔙 Назад", callback_data="compose_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка при получении статуса compose: {e}")
            await query.edit_message_text("❌ Ошибка при получении статуса Docker Compose")

    async def start_compose_services(self, query, compose_dir):
        """Запустить сервисы Docker Compose"""
        try:
            await self.compose_client.start_compose_services(compose_dir)
            await query.edit_message_text("✅ Сервисы Docker Compose запущены")
            
            # Обновляем статус
            await asyncio.sleep(2)
            await self.show_compose_status(query, compose_dir)
            
        except Exception as e:
            logger.error(f"Ошибка при запуске compose сервисов: {e}")
            await query.edit_message_text("❌ Ошибка при запуске сервисов")

    async def stop_compose_services(self, query, compose_dir):
        """Остановить сервисы Docker Compose"""
        try:
            await self.compose_client.stop_compose_services(compose_dir)
            await query.edit_message_text("⏹️ Сервисы Docker Compose остановлены")
            
            # Обновляем статус
            await asyncio.sleep(2)
            await self.show_compose_status(query, compose_dir)
            
        except Exception as e:
            logger.error(f"Ошибка при остановке compose сервисов: {e}")
            await query.edit_message_text("❌ Ошибка при остановке сервисов")

    async def restart_compose_services(self, query, compose_dir):
        """Перезапустить сервисы Docker Compose"""
        try:
            await self.compose_client.restart_compose_services(compose_dir)
            await query.edit_message_text("🔄 Сервисы Docker Compose перезапущены")
            
            # Обновляем статус
            await asyncio.sleep(2)
            await self.show_compose_status(query, compose_dir)
            
        except Exception as e:
            logger.error(f"Ошибка при перезапуске compose сервисов: {e}")
            await query.edit_message_text("❌ Ошибка при перезапуске сервисов")

    async def show_compose_logs(self, query, compose_dir):
        """Показать логи Docker Compose"""
        try:
            logs = await self.compose_client.get_compose_logs(compose_dir, lines=30)
            
            if len(logs) > 3000:
                logs = logs[-3000:] + "\n\n... (показаны последние 30 строк)"
            
            message = f"📝 *Логи {os.path.basename(compose_dir)}:*\n\n"
            message += f"```\n{logs}\n```"
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"compose_status_{compose_dir}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка при получении логов compose: {e}")
            await query.edit_message_text("❌ Ошибка при получении логов")

    async def show_stats(self, query):
        """Показать статистику"""
        try:
            stats = await self.docker_client.get_stats()
            
            message = "📊 *Статистика сервера:*\n\n"
            message += f"🖥️ CPU: {stats['cpu_percent']:.1f}%\n"
            message += f"💾 Память: {stats['memory_percent']:.1f}%\n"
            message += f"💿 Диск: {stats['disk_percent']:.1f}%\n"
            message += f"🌐 Контейнеры: {stats['containers']}\n"
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="refresh")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            await query.edit_message_text("❌ Ошибка при получении статистики")

    async def show_images(self, query):
        """Показать список образов"""
        try:
            images = await self.docker_client.get_images()
            
            if not images:
                await query.edit_message_text("🏷️ Образы не найдены")
                return
                
            message = "🏷️ *Docker образы:*\n\n"
            
            for image in images:
                message += f"`{image['name']}`\n"
                message += f"   Размер: {image['size']}\n"
                message += f"   Создан: {image['created']}\n\n"
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="refresh")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка при получении образов: {e}")
            await query.edit_message_text("❌ Ошибка при получении образов")

    async def handle_container_action(self, query):
        """Обработка действий с контейнерами"""
        container_id = query.data.split("_")[1]
        
        try:
            container_info = await self.docker_client.get_container_info(container_id)
            
            message = f"🐳 *{container_info['name']}*\n\n"
            message += f"Статус: {container_info['status']}\n"
            message += f"Образ: {container_info['image']}\n"
            message += f"Создан: {container_info['created']}\n"
            
            keyboard = []
            
            if container_info['status'] == 'running':
                keyboard.append([InlineKeyboardButton("⏹️ Остановить", callback_data=f"stop_{container_id}")])
                keyboard.append([InlineKeyboardButton("🔄 Перезапустить", callback_data=f"restart_{container_id}")])
            else:
                keyboard.append([InlineKeyboardButton("▶️ Запустить", callback_data=f"start_{container_id}")])
            
            keyboard.append([InlineKeyboardButton("📝 Логи", callback_data=f"logs_{container_id}")])
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="list_containers")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка при получении информации о контейнере: {e}")
            await query.edit_message_text("❌ Ошибка при получении информации о контейнере")

    async def refresh_menu(self, query):
        """Обновить главное меню"""
        keyboard = [
            [InlineKeyboardButton("📋 Контейнеры", callback_data="list_containers")],
            [InlineKeyboardButton("🐙 Docker Compose", callback_data="compose_menu")],
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton("🏷️ Образы", callback_data="list_images")],
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🐳 *Docker Manager Bot*\n\n"
            "Выберите действие:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    def run(self):
        """Запуск бота"""
        application = Application.builder().token(self.bot_token).build()
        
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CallbackQueryHandler(self.button_callback))
        
        logger.info("Бот запущен...")
        application.run_polling()

if __name__ == "__main__":
    bot = TelegramDockerBot()
    bot.run()
