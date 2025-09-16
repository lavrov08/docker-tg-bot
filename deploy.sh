#!/bin/bash

# Скрипт для быстрого развертывания Telegram Docker Bot

set -e

echo "🐳 Telegram Docker Bot - Быстрое развертывание"
echo "=============================================="

# Проверка наличия Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker не установлен. Установите Docker и повторите попытку."
    exit 1
fi

# Проверка наличия Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose не установлен. Установите Docker Compose и повторите попытку."
    exit 1
fi

# Проверка наличия .env файла
if [ ! -f .env ]; then
    echo "📝 Создание .env файла из примера..."
    cp env.example .env
    echo "⚠️  Отредактируйте .env файл перед запуском!"
    echo "   Необходимо указать:"
    echo "   - BOT_TOKEN (получить у @BotFather)"
    echo "   - SERVER_HOST (IP вашего сервера)"
    echo "   - SERVER_USER (пользователь для SSH)"
    echo "   - SERVER_PASSWORD (пароль для SSH)"
    echo "   - ALLOWED_USERS (ID пользователей Telegram)"
    echo ""
    read -p "Нажмите Enter после настройки .env файла..."
fi

# Сборка и запуск
echo "🔨 Сборка Docker образа..."
docker-compose build

echo "🚀 Запуск сервисов..."
docker-compose up -d

echo "📊 Статус сервисов:"
docker-compose ps

echo ""
echo "✅ Развертывание завершено!"
echo ""
echo "📋 Полезные команды:"
echo "   docker-compose logs -f telegram-docker-bot  # Просмотр логов"
echo "   docker-compose restart telegram-docker-bot   # Перезапуск бота"
echo "   docker-compose down                          # Остановка сервисов"
echo ""
echo "🎉 Бот готов к работе! Найдите его в Telegram и отправьте /start"
