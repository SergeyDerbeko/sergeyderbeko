# Учебная среда — онлайн-школа

Веб-платформа с электронным журналом, аккаунтами учеников и преподавателей, расписанием, курсами и административной панелью.

## Архитектура
- `frontend/` — адаптивный интерфейс, публикуется на GitHub Pages.
- `backend/` — Python FastAPI + SQLite, разворачивается отдельно (Render, Railway, VPS и т. п.).
- GitHub Pages не запускает Python и не хранит секреты.

## Запуск backend локально
```bash
cd backend
python -m venv .venv
source .venv/bin/activate # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
export JWT_SECRET="replace-with-a-long-random-secret"
export ADMIN_PASSWORD="replace-this-password"
uvicorn app:app --reload
```
API: `http://localhost:8000`; документация: `/docs`.

Начальный логин администратора: `admin`. Пароль берётся из переменной окружения `ADMIN_PASSWORD`; если она не задана, для локального тестирования используется `admin`. **Не публикуйте сервис с этим паролем.** Задайте уникальный пароль и JWT_SECRET до деплоя.

## Публикация frontend
1. Разверните backend на хостинге с HTTPS.
2. Установите `CORS_ORIGINS` в точный адрес GitHub Pages, например `https://sergeyderbeko.github.io`.
3. В `frontend/config.js` укажите URL backend в `SCHOOL_API_URL`.
4. В GitHub откройте Settings → Pages → Build and deployment → GitHub Actions.
5. После push в `main` сайт будет опубликован по адресу `https://sergeyderbeko.github.io/sergeyderbeko/`.

## Важно перед реальным использованием
Это стартовая версия. Для эксплуатации добавьте смену пароля, сброс доступа, подтверждение email, резервное копирование БД, HTTPS, rate limiting, аудит действий, миграции и тесты. Пароли хранятся в виде bcrypt-хешей; секреты не должны попадать в Git.
