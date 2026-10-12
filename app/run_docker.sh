#!/usr/bin/env bash
set -euo pipefail
APP_PATH="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${IMAGE_NAME:-laboratorium-danych:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-laboratorium-danych}"
DATA_PATH="${DATA_DIR:-$APP_PATH/../exercises/dane}"
LOG_PATH="${LOG_DIR:-$APP_PATH/logs}"
CACHE_PATH="${CACHE_DIR:-$APP_PATH/cache}"
# Domyślnie: model lokalny (Ollama) i nasłuch tylko na tym komputerze. Zmień zmiennymi środowiskowymi.
BIND_ADDRESS="${BIND_ADDRESS:-127.0.0.1}"
if [[ ! -f "$DATA_PATH/slownik_danych.csv" || ! -f "$DATA_PATH/scenariusz.json" ||
      ( ! -f "$DATA_PATH/rejestr_brudny.xlsx" && ! -f "$DATA_PATH/rejestr_brudny.csv" ) ]]; then
    printf '%s\n' 'Brak pakietu danych. Ustaw DATA_DIR na kompletny katalog dane.' >&2
    exit 1
fi
USER_PATH="${LAB_USER_DIR:-$APP_PATH/user}"
mkdir -p "$LOG_PATH" "$CACHE_PATH" "$USER_PATH"
args=(--detach --name "$CONTAINER_NAME" --restart unless-stopped
      --user "$(id -u):$(id -g)" --network host
      --mount "type=bind,src=$(cd -- "$DATA_PATH" && pwd),dst=/data,readonly"
      --mount "type=bind,src=$(cd -- "$LOG_PATH" && pwd),dst=/app/logs"
      --mount "type=bind,src=$(cd -- "$CACHE_PATH" && pwd),dst=/app/cache"
      --mount "type=bind,src=$(cd -- "$USER_PATH" && pwd),dst=/app/user"
)
if [[ -n "${ENV_FILE:-}" ]]; then args+=(--env-file "$ENV_FILE"); fi
args+=(--env LAB_USER_DIR=/app/user --env DATA_DIR=/data --env LOG_DIR=/app/logs --env CACHE_DIR=/app/cache
       --env "STREAMLIT_SERVER_ADDRESS=$BIND_ADDRESS")
for variable in ORNITH_BASE_URL ORNITH_BASE_URLS ORNITH_API_KEY ORNITH_MODEL ORNITH_MAX_CONCURRENCY_PER_SERVER ORNITH_LABEL ORNITH_REASONING_EFFORT \
                QWEN_BASE_URL QWEN_API_KEY QWEN_MODEL QWEN_LABEL QWEN_REASONING_EFFORT OLLAMA_BASE_URL LAB_PUBLIC_SERVER; do
    if [[ -v "$variable" ]]; then args+=(--env "$variable=${!variable}"); fi
done
# Pliki hosta z kluczami są montowane tylko do odczytu; treść nie trafia do obrazu.
for prefix in ORNITH QWEN; do
    variable="${prefix}_API_KEY_FILE"
    if [[ -n "${!variable:-}" ]]; then
        secret_path="${!variable}"
        if [[ "$secret_path" != /* ]]; then secret_path="$PWD/$secret_path"; fi
        if [[ ! -f "$secret_path" || ! -r "$secret_path" ]]; then printf '%s\n' "Nie można odczytać pliku $variable." >&2; exit 1; fi
        args+=(--mount "type=bind,src=$secret_path,dst=/run/secrets/${prefix,,},readonly"
               --env "$variable=/run/secrets/${prefix,,}")
    fi
done
docker build -t "$IMAGE_NAME" "$APP_PATH"
if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    docker rm -f "$CONTAINER_NAME" >/dev/null
fi
docker run "${args[@]}" "$IMAGE_NAME"
printf '%s\n' "Uruchomiono na $BIND_ADDRESS:8501. Logi: docker logs $CONTAINER_NAME"
