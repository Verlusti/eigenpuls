#!/usr/bin/env bash
set -euo pipefail

# Pure Bash HTTP POST over /dev/tcp (HTTP only; no TLS)
# Usage:
#   eigenpuls_http_post "http://host:port/path" "bearer_token_or_empty" '{"json":"body"}'
# Outputs response body to stdout. Exposes HTTP status via EIGENPULS_HTTP_STATUS variable.

eigenpuls_url_parse() {
    # Args: url -> sets global vars: _scheme _host _port _path
    local url="$1"
    _scheme="${url%%://*}"
    local rest="${url#*://}"
    _host="${rest%%/*}"
    _path="/${rest#*/}"
    if [[ "${_host}" == "${_path}" ]]; then
        _path="/"
    fi
    if [[ "${_host}" == *:* ]]; then
        _port="${_host##*:}"
        _host="${_host%%:*}"
    else
        _port="80"
    fi
}

eigenpuls_http_post() {
    local url="$1"; shift || true
    local apikey="${1-}"; shift || true
    local body="${1-}"; shift || true

    eigenpuls_url_parse "${url}"
    if [[ "${_scheme}" != "http" ]]; then
        echo "Only plain HTTP is supported by /dev/tcp (got: ${_scheme})" >&2
        return 2
    fi

    local content_length
    content_length=$(printf %s "${body}" | wc -c | tr -d ' ')

    # Open TCP connection
    exec 3<>"/dev/tcp/${_host}/${_port}"

    # Build and send request
    {
        printf 'POST %s HTTP/1.1\r\n' "${_path}"
        printf 'Host: %s\r\n' "${_host}"
        printf 'Accept: application/json\r\n'
        printf 'Content-Type: application/json\r\n'
        if [[ -n "${apikey}" ]]; then
            printf 'Authorization: Bearer %s\r\n' "${apikey}"
        fi
        printf 'Content-Length: %s\r\n' "${content_length}"
        printf 'Connection: close\r\n'
        printf '\r\n'
        printf '%s' "${body}"
    } >&3

    # Read full response
    local response
    response="$(cat <&3)"
    exec 3>&- 3<&-

    # Normalize CRLF to LF
    local resp
    resp="${response//$'\r'/}"

    # Extract status
    local status_line
    status_line="$(printf '%s' "${resp}" | head -n1)"
    export EIGENPULS_HTTP_STATUS
    EIGENPULS_HTTP_STATUS="$(printf '%s' "${status_line}" | awk '{print $2}')"

    # Extract body (after empty line)
    local body_out
    body_out="${resp#*$'\n\n'}"
    printf '%s' "${body_out}"
}

# ----------------------
# Minimal probe library
# ----------------------
probe_tcp() {
    local host="${1:-127.0.0.1}" port="${2:-80}"
    exec 9<>"/dev/tcp/${host}/${port}" || { echo "tcp connect failed: ${host}:${port}"; return 1; }
    exec 9>&- 9<&-
    echo "tcp ok: ${host}:${port}"
}

probe_http() {
    local host="${1:-127.0.0.1}" port="${2:-80}" hpath="${3:-/}"
    exec 9<>"/dev/tcp/${host}/${port}" || { echo "http connect failed: ${host}:${port}"; return 1; }
    printf 'GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n' "${hpath}" "${host}" >&9
    local resp
    resp="$(cat <&9)"
    exec 9>&- 9<&-
    resp="${resp//$'\r'/}"
    local status
    status="$(printf '%s' "${resp}" | head -n1 | awk '{print $2}')"
    if [[ "${status}" == "200" || "${status}" == "204" || "${status}" == "302" ]]; then
        echo "http ok: ${host}:${port}${hpath} status=${status}"
        return 0
    fi
    echo "http bad status: ${status}"
    return 1
}

probe_postgres() {
    local host="${1:-127.0.0.1}" port="${2:-5432}"
    if command -v pg_isready >/dev/null 2>&1; then
        if pg_isready -h "${host}" -p "${port}"; then
            echo "postgres ok: ${host}:${port}"
            return 0
        fi
        echo "pg_isready failed"
        return 1
    fi
    probe_tcp "${host}" "${port}"
}

probe_redis() {
    local host="${1:-127.0.0.1}" port="${2:-6379}"
    if command -v redis-cli >/dev/null 2>&1; then
        if redis-cli -h "${host}" -p "${port}" ping | grep -qi PONG; then
            echo "redis ok: ${host}:${port}"
            return 0
        fi
        echo "redis-cli ping failed"
        return 1
    fi
    probe_tcp "${host}" "${port}"
}

probe_rabbitmq() {
    local host="${1:-127.0.0.1}" port="${2:-5672}"
    probe_tcp "${host}" "${port}"
}

# Probe runner that reports to eigenpuls
eigenpuls_probe_and_report() {
    local url_base="$1" apikey="$2" service="$3" worker="$4" probe_name="$5"; shift 5 || true
    local host="${PROBE_HOST-127.0.0.1}" port="${PROBE_PORT-}"
    local hpath="${PROBE_PATH-/}"
    local out rc
    case "${probe_name}" in
        postgres)
            : "${port:=5432}"; set +e; out="$(probe_postgres "${host}" "${port}" 2>&1)"; rc=$?; set -e ;;
        redis)
            : "${port:=6379}"; set +e; out="$(probe_redis "${host}" "${port}" 2>&1)"; rc=$?; set -e ;;
        rabbitmq)
            : "${port:=5672}"; set +e; out="$(probe_rabbitmq "${host}" "${port}" 2>&1)"; rc=$?; set -e ;;
        http)
            : "${port:=80}"; set +e; out="$(probe_http "${host}" "${port}" "${hpath}" 2>&1)"; rc=$?; set -e ;;
        tcp)
            : "${port:=80}"; set +e; out="$(probe_tcp "${host}" "${port}" 2>&1)"; rc=$?; set -e ;;
        *)
            echo "unknown probe: ${probe_name}" >&2; return 2 ;;
    esac
    local status mode details
    if [[ ${rc} -eq 0 ]]; then
        mode="running"; status="ok"; details="${out}"
    else
        mode="failed"; status="error"; details="${out}"
    fi
    # Truncate details
    details="${details//$'\n'/ }"; details="${details//$'\r'/ }"
    if ((${#details} > 220)); then details="${details:0:217}..."; fi
    local payload
    payload=$(printf '{"mode":"%s","status":"%s","details":"%s","stacktrace":""}' \
        "${mode}" "${status}" "${details}")
    eigenpuls_http_post "${url_base%/}/health/service/${service}/worker/${worker}" "${apikey}" "${payload}"
    return ${rc}
}

# Build JSON for ServiceConfig from env (or positional args)
# Env: TYPE, POLICY, INTERVAL, TIMEOUT, MAX_RETRIES
eigenpuls_config_payload() {
    local type="${TYPE-}${EIGENPULS_TYPE-}"
    local policy="${POLICY-}${EIGENPULS_POLICY-}"
    local interval="${INTERVAL-${EIGENPULS_INTERVAL-}}"
    local timeout="${TIMEOUT-${EIGENPULS_TIMEOUT-}}"
    local max_retries="${MAX_RETRIES-${EIGENPULS_MAX_RETRIES-}}"
    local entries=""
    if [[ -n "${type}" ]]; then entries+=$(printf '"type":"%s",' "${type}"); fi
    if [[ -n "${policy}" ]]; then entries+=$(printf '"policy":"%s",' "${policy}"); fi
    if [[ -n "${interval}" ]]; then entries+=$(printf '"interval":%s,' "${interval}"); fi
    if [[ -n "${timeout}" ]]; then entries+=$(printf '"timeout":%s,' "${timeout}"); fi
    if [[ -n "${max_retries}" ]]; then entries+=$(printf '"max_retries":%s,' "${max_retries}"); fi
    entries="${entries%,}"
    printf '{%s}' "${entries}"
}

# POST ServiceConfig to /health/service/{service}/config
eigenpuls_post_config() {
    local url_base="$1"; shift || true
    local apikey="$1"; shift || true
    local service="$1"; shift || true
    local payload
    if [[ "$#" -gt 0 ]]; then
        payload="$1"
    else
        payload="$(eigenpuls_config_payload)"
    fi
    eigenpuls_http_post "${url_base%/}/health/service/${service}/config" "${apikey}" "${payload}"
}

# Optional CLI wrapper when invoked directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    : "${EIGENPULS_URL:?set EIGENPULS_URL}"
    : "${EIGENPULS_APIKEY:=}"
    : "${SERVICE:?set SERVICE}"
    : "${ACTION:=worker}"
    if [[ "${ACTION}" = "config" ]]; then
        payload="$(eigenpuls_config_payload)"
        eigenpuls_post_config "${EIGENPULS_URL}" "${EIGENPULS_APIKEY}" "${SERVICE}" "${payload}"
    elif [[ "${ACTION}" = "probe" ]]; then
        : "${WORKER:?set WORKER (probe identifier)}"
        : "${PROBE:?set PROBE (postgres|redis|rabbitmq|http|tcp)}"
        eigenpuls_probe_and_report "${EIGENPULS_URL}" "${EIGENPULS_APIKEY}" "${SERVICE}" "${WORKER}" "${PROBE}"
    else
        : "${WORKER:?set WORKER}"
        : "${MODE:=running}"
        : "${STATUS:=ok}"
        : "${DETAILS:=}"
        : "${STACKTRACE:=}"
        payload=$(printf '{"mode":"%s","status":"%s","details":"%s","stacktrace":"%s"}' \
            "${MODE}" "${STATUS}" "${DETAILS}" "${STACKTRACE}")
        eigenpuls_http_post "${EIGENPULS_URL%/}/health/service/${SERVICE}/worker/${WORKER}" "${EIGENPULS_APIKEY}" "${payload}"
    fi
fi


