#!/usr/bin/env bash
set -euo pipefail

SERVICE="remote-printer"
UNIT_PATH="/etc/systemd/system/${SERVICE}.service"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

info() { printf '\033[1m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[31mОшибка:\033[0m %s\n' "$*" >&2; exit 1; }

if [[ $EUID -eq 0 ]]; then
    RUN_USER="${SUDO_USER:-}"
    [[ -n "$RUN_USER" && "$RUN_USER" != "root" ]] \
        || fail "запустите скрипт от обычного пользователя: ./install_service.sh"
else
    RUN_USER="$USER"
fi

as_user() {
    if [[ $EUID -eq 0 ]]; then sudo -u "$RUN_USER" "$@"; else "$@"; fi
}

uninstall() {
    info "Останавливаю и удаляю сервис ${SERVICE}"
    sudo systemctl disable --now "$SERVICE" 2>/dev/null || true
    sudo rm -f "$UNIT_PATH"
    sudo systemctl daemon-reload
    info "Готово. Файлы проекта и база данных не тронуты."
}

install() {
    info "Проект: $PROJECT_DIR"
    info "Пользователь: $RUN_USER"

    [[ -f "$PROJECT_DIR/main.py" ]] || fail "не найден main.py рядом со скриптом"
    [[ -f "$PROJECT_DIR/config.toml" ]] || fail "не найден config.toml"
    [[ -f "$PROJECT_DIR/.env" ]] \
        || fail "не найден .env — скопируйте .env.example в .env и заполните BOT_TOKEN и ROOT_TG_ID"

    command -v "$PYTHON" >/dev/null || fail "не найден $PYTHON"
    "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
        || fail "нужен Python 3.11 или новее, а установлен $("$PYTHON" -V 2>&1). Укажите другой: PYTHON=python3.12 ./install_service.sh"

    if [[ ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
        info "Создаю виртуальное окружение .venv"
        as_user "$PYTHON" -m venv "$PROJECT_DIR/.venv" \
            || fail "не удалось создать venv. Установите пакет: sudo apt install python3-venv"
    fi

    info "Устанавливаю зависимости"
    as_user "$PROJECT_DIR/.venv/bin/pip" install --quiet --upgrade pip
    as_user "$PROJECT_DIR/.venv/bin/pip" install --quiet -r "$PROJECT_DIR/requirements.txt"

    if [[ -d "$PROJECT_DIR/data" ]]; then
        info "Назначаю $RUN_USER владельцем папки data"
        sudo chown -R "$RUN_USER": "$PROJECT_DIR/data"
    fi

    for group in lp scanner; do
        if getent group "$group" >/dev/null && ! id -nG "$RUN_USER" | grep -qw "$group"; then
            info "Добавляю $RUN_USER в группу $group (доступ к принтеру и сканеру)"
            sudo usermod -aG "$group" "$RUN_USER"
        fi
    done

    info "Создаю $UNIT_PATH"
    sudo tee "$UNIT_PATH" >/dev/null <<EOF
[Unit]
Description=Telegram bot for remote printing and scanning
After=network-online.target cups.service
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python $PROJECT_DIR/main.py
Environment=PYTHONUNBUFFERED=1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE" >/dev/null
    sudo systemctl restart "$SERVICE"

    sleep 3
    if systemctl is-active --quiet "$SERVICE"; then
        info "Бот запущен и будет стартовать при загрузке системы"
    else
        sudo journalctl -u "$SERVICE" -n 30 --no-pager
        fail "сервис не запустился, последние строки лога выше"
    fi

    cat <<EOF

Полезные команды:
  systemctl status $SERVICE        состояние
  journalctl -u $SERVICE -f        логи в реальном времени
  sudo systemctl restart $SERVICE  перезапуск после обновления кода
  ./install_service.sh uninstall   удалить из автозагрузки
EOF
}

case "${1:-install}" in
    install) install ;;
    uninstall) uninstall ;;
    *) echo "Использование: $0 [install|uninstall]"; exit 1 ;;
esac
