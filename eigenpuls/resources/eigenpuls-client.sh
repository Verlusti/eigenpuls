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

# Optional CLI wrapper when invoked directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    : "${EIGENPULS_URL:?set EIGENPULS_URL}"
    : "${EIGENPULS_APIKEY:=}"
    : "${SERVICE:?set SERVICE}"
    : "${WORKER:?set WORKER}"
    : "${MODE:=running}"
    : "${STATUS:=ok}"
    : "${DETAILS:=}"
    : "${STACKTRACE:=}"
    payload=$(printf '{"mode":"%s","status":"%s","details":"%s","stacktrace":"%s"}' \
        "${MODE}" "${STATUS}" "${DETAILS}" "${STACKTRACE}")
    eigenpuls_http_post "${EIGENPULS_URL%/}/health/service/${SERVICE}/worker/${WORKER}" "${EIGENPULS_APIKEY}" "${payload}"
fi


