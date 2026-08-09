# Локальное окружение Outline Wiki + Keycloak + Nginx

Этот репозиторий содержит конфигурацию для локального развертывания корпоративной базы знаний **Outline Wiki** совместно с локальным провайдером авторизации **Keycloak**.

## Архитектура окружения

*   **Outline Wiki** (порт `3000` внутренний, `3001` внешний через прокси) — основное приложение.
*   **Nginx Proxy** (порт `3000`) — прослойка, которая обманывает систему безопасности Outline, принудительно выставляя заголовок `X-Forwarded-Proto http` для работы кук авторизации без SSL.
*   **Keycloak** (порт `8080`) — локальный OIDC-провайдер авторизации. Хранит данные на диске.
*   **PostgreSQL & Redis** — инфраструктурная база данных и кеш для Outline.

---

## 🚀 Порядок первого запуска и настройки

1. **Скопируй файл `docker.env.example` в `docker.env` и заполни его:**
   ```bash
   cp docker.env.example docker.env
   ```
Значения, которые нужно заполнить:
* `SECRET_KEY` --> `openssl rand -hex 32`
* `UTILS_SECRET` --> `openssl rand -hex 32`
* `OIDC_CLIENT_SECRET` --> Заполняется в шаге 3.

2. **Запусти контейнер Keycloak:**
   ```bash
   docker compose up -d keycloak
   ```

3. **Настрой Keycloak (`http://localhost:8080`):**
   * Войди: `admin` / `adminpassword`.
   * Создай новый Realm с точным именем: `outline-realm`.
   * Перейди в **Clients** -> **Create client**:
     * *Client ID*: `outline`
     * Нажми *Next*, включи тумблер **Client Authentication** (сделает клиент конфиденциальным) и нажми *Save*.
   * В настройках созданного клиента (`outline`) укажи:
     * *Root URL*: `http://localhost:3000`
     * *Valid Redirect URIs*: `http://localhost:3000/*` и `https://localhost:3000/*`
     * *Web Origins*: `*`
   * Перейди во вкладку **Credentials** этого клиента и убедись, что `Client Secret` совпадает со значением `OIDC_CLIENT_SECRET` в твоем `docker.env`.
   * Перейди в **Users** -> **Add user**: создай пользователя, заполни поле **Email** (обязательно для Outline). Во вкладке *Credentials* задай ему постоянный пароль (выключи тумблер *Temporary*).

5. **Запусти все остальные контейнеры:**
   ```bash
   docker compose up -d
   ```

4. **Вход в Outline:**
   * Открой `http://localhost:3000`.
   * Нажми кнопку **Keycloak**.
   * Введи логин и пароль созданного пользователя. Вы внутри!

## 🐳 Полезные команды
* Полная остановка окружения: `docker compose down`
* Просмотр логов: `docker compose logs -f`
