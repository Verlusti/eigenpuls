#!/bin/sh
# Auto-pivot to bash pure mode (EIGENPULS_USE_BASH=1) if bash is available
if [ -z "${BASH_VERSION:-}" ] && [ "${EIGENPULS_USE_BASH:-0}" = "1" ] && command -v bash >/dev/null 2>&1; then
    exec bash "$0" "$@"
fi
# POSIX sh hybrid client: prefers curl, falls back to wget. No bash required.

set -eu

have_cmd() { command -v "$1" >/dev/null 2>&1; }

http_post() {
    url="$1"; apikey="${2-}"; body="${3-}"
    if have_cmd curl; then
        if [ -n "$apikey" ]; then auth="Authorization: Bearer $apikey"; else auth=""; fi
        curl -sS -X POST -H "$auth" -H 'Content-Type: application/json' -d "$body" "$url"
        return 0
    fi
    if have_cmd wget; then
        if [ -n "$apikey" ]; then
            wget -qO- \
              --header="Content-Type: application/json" \
              --header="Authorization: Bearer $apikey" \
              --post-data="$body" "$url"
        else
            wget -qO- \
              --header="Content-Type: application/json" \
              --post-data="$body" "$url"
        fi
        return 0
    fi
    echo "No HTTP client found (curl/wget)." >&2
    return 2
}

probe_http() {
    host="${1:-127.0.0.1}"; port="${2:-80}"; pth="${3:-/}"
    url="http://$host:$port$pth"
    if have_cmd curl; then
        code=$(curl -s -o /dev/null -w "%{http_code}" "$url") || code="000"
        if [ "$code" = "200" ] || [ "$code" = "204" ] || [ "$code" = "302" ]; then
            echo "http ok: $host:$port$pth status=$code"; return 0
        fi
        echo "http bad status: $code"; return 1
    fi
    if have_cmd wget; then
        # wget prints headers to stderr; capture first status line
        out=$(wget -S -O - "$url" 2>&1 >/dev/null || true)
        code=$(printf "%s\n" "$out" | awk '/^  HTTP\//{print $2; exit}')
        [ -z "$code" ] && code=000
        if [ "$code" = "200" ] || [ "$code" = "204" ] || [ "$code" = "302" ]; then
            echo "http ok: $host:$port$pth status=$code"; return 0
        fi
        echo "http bad status: $code"; return 1
    fi
    echo "No HTTP client found (curl/wget)." >&2
    return 2
}

probe_postgres() {
    host="${1:-127.0.0.1}"; port="${2:-5432}"
    if have_cmd pg_isready; then
        if pg_isready -h "$host" -p "$port"; then echo "postgres ok: $host:$port"; return 0; fi
        echo "pg_isready failed"; return 1
    fi
    echo "postgres probe requires pg_isready"; return 2
}

probe_redis() {
    host="${1:-127.0.0.1}"; port="${2:-6379}"
    if have_cmd redis-cli; then
        if redis-cli -h "$host" -p "$port" ping | grep -qi PONG; then echo "redis ok: $host:$port"; return 0; fi
        echo "redis-cli ping failed"; return 1
    fi
    echo "redis probe requires redis-cli"; return 2
}

probe_rabbitmq() {
    host="${1:-127.0.0.1}"; port="${2:-5672}"
    echo "rabbitmq tcp probe not supported without nc/curl/wget status; use http mgmt if available"; return 2
}

# --- Optional pure-bash implementations (enabled by EIGENPULS_USE_BASH=1) ---
if [ -n "${BASH_VERSION:-}" ] && [ "${EIGENPULS_USE_BASH:-0}" = "1" ]; then
    # Pure bash URL parse (sets _scheme _host _port _path)
    eigenpuls_url_parse() {
        local url="$1"
        _scheme="${url%%://*}"
        local rest="${url#*://}"
        _host="${rest%%/*}"
        _path="/${rest#*/}"
        if [[ "${_host}" == "${_path}" ]]; then _path="/"; fi
        if [[ "${_host}" == *:* ]]; then _port="${_host##*:}"; _host="${_host%%:*}"; else _port="80"; fi
    }

    # Pure bash HTTP POST via /dev/tcp (HTTP only)
    eigenpuls_http_post() {
        local url="$1"; shift || true
        local apikey="${1-}"; shift || true
        local body="${1-}"; shift || true
        eigenpuls_url_parse "${url}"
        if [[ "${_scheme}" != "http" ]]; then echo "Only plain HTTP is supported by /dev/tcp (got: ${_scheme})" >&2; return 2; fi
        local content_length
        content_length=$(printf %s "${body}" | wc -c | tr -d ' ')
        exec 3<>"/dev/tcp/${_host}/${_port}"
        {
            printf 'POST %s HTTP/1.1\r\n' "${_path}"
            printf 'Host: %s\r\n' "${_host}"
            printf 'Accept: application/json\r\n'
            printf 'Content-Type: application/json\r\n'
            if [[ -n "${apikey}" ]]; then printf 'Authorization: Bearer %s\r\n' "${apikey}"; fi
            printf 'Content-Length: %s\r\n' "${content_length}"
            printf 'Connection: close\r\n\r\n'
            printf '%s' "${body}"
        } >&3
        local response; response="$(cat <&3)"; exec 3>&- 3<&-
        local resp; resp="${response//$'\r'/}"
        local body_out; body_out="${resp#*$'\n\n'}"; printf '%s' "${body_out}"
    }

    # Override http_post/probe_http to pure bash when requested
    http_post() { eigenpuls_http_post "$@"; }

    probe_http() {
        local host="${1:-127.0.0.1}" port="${2:-80}" hpath="${3:-/}"
        exec 9<>"/dev/tcp/${host}/${port}" || { echo "http connect failed: ${host}:${port}"; return 1; }
        printf 'GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n' "${hpath}" "${host}" >&9
        local resp; resp="$(cat <&9)"; exec 9>&- 9<&-
        resp="${resp//$'\r'/}"
        local status; status="$(printf '%s' "${resp}" | head -n1 | awk '{print $2}')"
        if [[ "${status}" == "200" || "${status}" == "204" || "${status}" == "302" ]]; then
            echo "http ok: ${host}:${port}${hpath} status=${status}"; return 0
        fi
        echo "http bad status: ${status}"; return 1
    }
fi

probe_and_report() {
    url_base="$1"; apikey="$2"; service="$3"; worker="$4"; probe_name="$5"
    host="${PROBE_HOST-127.0.0.1}"; port="${PROBE_PORT-}"; pth="${PROBE_PATH-/}"
    case "$probe_name" in
        postgres) [ -n "$port" ] || port=5432; out=$(probe_postgres "$host" "$port" 2>&1; echo "__RC:$?") ;;
        redis)    [ -n "$port" ] || port=6379; out=$(probe_redis "$host" "$port" 2>&1; echo "__RC:$?") ;;
        rabbitmq) [ -n "$port" ] || port=5672; out=$(probe_rabbitmq "$host" "$port" 2>&1; echo "__RC:$?") ;;
        http)     [ -n "$port" ] || port=80;   out=$(probe_http "$host" "$port" "$pth" 2>&1; echo "__RC:$?") ;;
        tcp)      echo "tcp probe not supported in POSIX mode"; out="__RC:2" ;;
        *) echo "unknown probe: $probe_name"; out="__RC:2" ;;
    esac
    rc=$(printf "%s" "$out" | awk -F"__RC:" 'NF>1{print $2; exit}')
    msg=$(printf "%s" "$out" | sed 's/__RC:.*$//')
    if [ "$rc" -eq 0 ]; then mode=running; stat=ok; else mode=failed; stat=error; fi
    # Truncate details to ~220 chars
    details=$(printf "%s" "$msg" | tr '\r' ' ' | tr '\n' ' ')
    details=$(printf "%.220s" "$details")
    payload=$(printf '{"mode":"%s","status":"%s","details":"%s","stacktrace":""}' "$mode" "$stat" "$details")
    http_post "${url_base%/}/health/service/${service}/worker/${worker}" "$apikey" "$payload"
    return "$rc"
}

config_payload() {
    type="${TYPE-}${EIGENPULS_TYPE-}"; policy="${POLICY-}${EIGENPULS_POLICY-}"
    interval="${INTERVAL-${EIGENPULS_INTERVAL-}}"; timeout="${TIMEOUT-${EIGENPULS_TIMEOUT-}}"; maxr="${MAX_RETRIES-${EIGENPULS_MAX_RETRIES-}}"
    entries=""
    [ -n "$type" ] && entries=$entries$(printf '"type":"%s",' "$type")
    [ -n "$policy" ] && entries=$entries$(printf '"policy":"%s",' "$policy")
    [ -n "$interval" ] && entries=$entries$(printf '"interval":%s,' "$interval")
    [ -n "$timeout" ] && entries=$entries$(printf '"timeout":%s,' "$timeout")
    [ -n "$maxr" ] && entries=$entries$(printf '"max_retries":%s,' "$maxr")
    entries=${entries%,}
    printf '{%s}' "$entries"
}

post_config() {
    url_base="$1"; apikey="$2"; service="$3"; payload="$4"
    [ -n "$payload" ] || payload=$(config_payload)
    http_post "${url_base%/}/health/service/${service}/config" "$apikey" "$payload"
}

if [ "${0##*/}" = "eigenpuls-client.sh" ] || [ "${BASH_SOURCE:+x}" = "" ]; then
    : "${EIGENPULS_URL:?set EIGENPULS_URL}"
    : "${EIGENPULS_APIKEY:=}"
    : "${SERVICE:?set SERVICE}"
    : "${ACTION:=worker}"
    if [ "$ACTION" = "config" ]; then
        post_config "$EIGENPULS_URL" "$EIGENPULS_APIKEY" "$SERVICE" "${PAYLOAD-}"
    elif [ "$ACTION" = "probe" ]; then
        : "${WORKER:?set WORKER}"
        : "${PROBE:?set PROBE (postgres|redis|rabbitmq|http|tcp)}"
        probe_and_report "$EIGENPULS_URL" "$EIGENPULS_APIKEY" "$SERVICE" "$WORKER" "$PROBE"
    else
        : "${WORKER:?set WORKER}"
        : "${MODE:=running}"; : "${STATUS:=ok}"; : "${DETAILS:=}"; : "${STACKTRACE:=}"
        payload=$(printf '{"mode":"%s","status":"%s","details":"%s","stacktrace":"%s"}' "$MODE" "$STATUS" "$DETAILS" "$STACKTRACE")
        http_post "${EIGENPULS_URL%/}/health/service/${SERVICE}/worker/${WORKER}" "$EIGENPULS_APIKEY" "$payload"
    fi
fi


