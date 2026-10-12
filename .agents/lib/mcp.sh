#!/usr/bin/env bash
# Small, synchronous Streamable HTTP client. Requires Bash, curl, jq and awk.
# Call in the shell that sourced this file, redirecting stdout to capture JSON:
#   mcp_connect "$GITHUB_MCP_URL" "$GITHUB_TOKEN" > initialize.json
#   mcp_list_tools > tools.json
#   mcp_call get_me '{}' > result.json
# Never use $(mcp_call ...): request/session state belongs to the owning shell.
# Caller shell options and traps are not changed. See ../github-mcp-contract.md.

_MCP_OWNER_PID=$BASHPID
_MCP_URL=''
_MCP_TOKEN=''
_MCP_SESSION_ID=''
_MCP_NEGOTIATED_PROTOCOL=''
_MCP_NEXT_REQUEST_ID=1
_MCP_READY=0
_MCP_RESULT=''
_MCP_CONTEXT=''
_MCP_TIMEOUT=30
_MCP_CONNECT_TIMEOUT=10
_MCP_TOOLSETS=''

_mcp_error() {
    printf 'ERROR: MCP %s%s\n' "${_MCP_CONTEXT:+$_MCP_CONTEXT: }" "$1" >&2
    return 1
}

_mcp_owner() {
    [[ "$BASHPID" == "$_MCP_OWNER_PID" ]] || {
        _mcp_error 'call in the owning shell; capture JSON with output redirection'
        return 1
    }
}

# Validate exactly one JSON-RPC message, including unrelated SSE messages.
_mcp_valid_message() {
    jq -es '
        length == 1 and (.[0] |
        type == "object" and .jsonrpc == "2.0" and
        if has("method") then
            (.method | type == "string" and length > 0) and
            (has("result") | not) and (has("error") | not) and
            ((has("params") | not) or (.params | type == "object" or type == "array"))
        else
            has("id") and (.id | type == "number" or type == "string") and
            (has("result") != has("error")) and
            if has("error") then
                (.error | type == "object" and
                 (.code | type == "number" and floor == .) and
                 (.message | type == "string"))
            else (.result | type == "object") end
        end)
    ' >/dev/null 2>&1
}

_mcp_extract_response() {
    local file="$1" content_type="$2" request_id="$3"
    local line='' field='' value='' data='' event='' response='' have_data=0
    case "$content_type" in
        application/json)
            _mcp_valid_message < "$file" || return 1
            jq -ce --argjson id "$request_id" \
                'select(.id == $id and (has("method") | not))' "$file"
            ;;
        text/event-stream)
            while IFS= read -r line || [[ -n "$line" ]]; do
                line="${line%$'\r'}"
                if [[ -z "$line" ]]; then
                    if [[ "$have_data" == 1 && ( -z "$event" || "$event" == message ) ]]; then
                        _mcp_valid_message <<< "$data" || return 1
                        if jq -e 'has("method") and has("id")' >/dev/null <<< "$data"; then
                            # No sampling/elicitation capabilities are advertised.
                            return 1
                        fi
                        if jq -e --argjson id "$request_id" \
                            '.id == $id and (has("method") | not)' >/dev/null <<< "$data"; then
                            [[ -z "$response" ]] || return 1
                            response="$data"
                        fi
                    fi
                    data='' event='' have_data=0
                    continue
                fi
                [[ "$line" == :* ]] && continue
                field="${line%%:*}"
                value=''
                [[ "$line" == *:* ]] && value="${line#*:}"
                value="${value# }"
                case "$field" in
                    data)
                        [[ "$have_data" == 0 ]] || data+=$'\n'
                        data+="$value"
                        have_data=1
                        ;;
                    event) event="$value" ;;
                    id|retry) : ;; # No replay/resumption is performed.
                    *) : ;; # SSE ignores unknown fields.
                esac
            done < "$file"
            # A data event without its terminating blank line is incomplete.
            [[ "$have_data" == 0 && -z "$event" && -n "$response" ]] || return 1
            printf '%s\n' "$response"
            ;;
        *) return 1 ;;
    esac
}

# This subprocess owns all temporary files and traps. No session state changes
# happen here; the parent increments IDs and consumes the returned JSON packet.
_mcp_http() (
    umask 077
    local payload="$1" request_id="$2" directory='' status='' response=''
    local content_type='' session='' curl_status=0
    directory=$(mktemp -d "${TMPDIR:-/tmp}/lean-sdd-mcp.XXXXXXXX") || {
        _mcp_error 'cannot create private request directory'
        exit 1
    }
    trap 'rm -rf -- "$directory"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    printf '%s' "$payload" > "$directory/request" || exit 1
    {
        printf 'Authorization: Bearer %s\n' "$_MCP_TOKEN"
        printf 'Content-Type: application/json\nAccept: application/json, text/event-stream\n'
        [[ -z "$_MCP_SESSION_ID" ]] || printf 'Mcp-Session-Id: %s\n' "$_MCP_SESSION_ID"
        [[ -z "$_MCP_NEGOTIATED_PROTOCOL" ]] || printf 'MCP-Protocol-Version: %s\n' "$_MCP_NEGOTIATED_PROTOCOL"
        [[ -z "$_MCP_TOOLSETS" ]] || printf 'X-MCP-Toolsets: %s\n' "$_MCP_TOOLSETS"
        :
    } > "$directory/auth" || exit 1
    # -q must be first: ignore curlrc options (redirects, retries, extra URLs).
    # Credentials and payload are files, not command-line arguments. Never dump
    # curl stderr or server bodies, which may contain echoed secrets or issue text.
    status=$(curl -q --silent --proto '=https' --max-redirs 0 --retry 0 \
        --connect-timeout "$_MCP_CONNECT_TIMEOUT" \
        --max-time "$_MCP_TIMEOUT" --request POST \
        --header "@$directory/auth" --data-binary "@$directory/request" \
        --dump-header "$directory/headers" --output "$directory/body" \
        --write-out '%{http_code}' --url "$_MCP_URL" 2> "$directory/curl-error") || curl_status=$?
    if [[ "$curl_status" != 0 ]]; then
        _mcp_error "network/timeout failure (curl $curl_status); outcome unconfirmed; no retry"
        exit 1
    fi
    if [[ "$request_id" == notification ]]; then
        [[ "$status" == 202 && ! -s "$directory/body" ]] || {
            _mcp_error 'initialized notification rejected or malformed'
            exit 1
        }
        printf '{}\n'
        exit 0
    fi
    if [[ "$status" != 200 ]]; then
        [[ "$status" =~ ^[0-9]{3}$ ]] || status=invalid
        _mcp_error "HTTP $status; outcome unconfirmed; no retry (404 requires explicit reconnect)"
        exit 1
    fi
    # Reset at each status line: use the final response, not proxy/1xx headers.
    content_type=$(awk '
        { sub(/\r$/, "") }
        /^HTTP\// { value="" }
        tolower($0) ~ /^content-type:/ {
            sub(/^[^:]*:[ \t]*/, ""); value=tolower($0); sub(/[; \t].*$/, "", value)
        }
        END { print value }
    ' "$directory/headers")
    session=$(awk '
        { sub(/\r$/, "") }
        /^HTTP\// { value=""; count=0 }
        tolower($0) ~ /^mcp-session-id:/ {
            count++; sub(/^[^:]*:[ \t]*/, ""); value=$0
        }
        END { if (count>1 || (count==1 && value=="")) exit 1; print value }
    ' "$directory/headers") || {
        _mcp_error 'invalid or duplicate session header'
        exit 1
    }
    if [[ -n "$session" ]] && ! LC_ALL=C grep -Eq '^[!-~]+$' <<< "$session"; then
        _mcp_error 'invalid session header'
        exit 1
    fi
    if ! response=$(_mcp_extract_response "$directory/body" "$content_type" "$request_id"); then
        _mcp_error 'invalid, incomplete, or uncorrelated JSON-RPC/SSE response'
        exit 1
    fi
    jq -cn --arg session "$session" --argjson response "$response" \
        '{session:$session,response:$response}'
)

_mcp_request() {
    local method="$1" params="$2" request_id="$_MCP_NEXT_REQUEST_ID" payload='' packet=''
    _MCP_NEXT_REQUEST_ID=$((_MCP_NEXT_REQUEST_ID + 1))
    _MCP_RESULT=''
    _MCP_CONTEXT="$method${3:+/$3} request $request_id"
    payload=$(jq -cn --arg method "$method" --argjson params "$params" \
        --argjson id "$request_id" '{jsonrpc:"2.0",id:$id,method:$method,params:$params}') || return 1
    if ! packet=$(_mcp_http "$payload" "$request_id"); then
        _MCP_READY=0
        return 1
    fi
    if jq -e '.response | has("error")' >/dev/null <<< "$packet"; then
        _MCP_READY=0
        _mcp_error 'JSON-RPC error; no retry'
        return 1
    fi
    if [[ "$method" == initialize ]]; then
        _MCP_SESSION_ID=$(jq -r '.session' <<< "$packet")
    elif ! jq -e --arg session "$_MCP_SESSION_ID" \
        '.session == "" or .session == $session' >/dev/null <<< "$packet"; then
        _MCP_READY=0
        _mcp_error 'session changed unexpectedly'
        return 1
    fi
    _MCP_RESULT=$(jq -c '.response.result' <<< "$packet")
}

mcp_connect() {
    _mcp_owner || return 1
    _MCP_READY=0 _MCP_RESULT='' _MCP_CONTEXT='connect'
    [[ $# == 2 ]] || { _mcp_error 'usage: mcp_connect <endpoint> <token>'; return 2; }
    [[ -n "$2" ]] || { _mcp_error 'missing credentials'; return 1; }
    [[ "$1" =~ ^https://[^/@?#[:space:]]+(/[^#[:space:]]*)?$ ]] || {
        _mcp_error 'explicit HTTPS MCP endpoint required (no userinfo or fragment)'; return 1;
    }
    [[ "$2" != *$'\r'* && "$2" != *$'\n'* ]] || {
        _mcp_error 'invalid credential header'; return 1;
    }
    local dependency='' setting='' params='' initialized=''
    for dependency in curl jq awk grep mktemp; do
        command -v "$dependency" >/dev/null 2>&1 || {
            _mcp_error "missing command $dependency"; return 1;
        }
    done
    for setting in "${MCP_TIMEOUT:-30}" "${MCP_CONNECT_TIMEOUT:-10}"; do
        [[ "$setting" =~ ^[1-9][0-9]{0,2}$ ]] && (( setting <= 300 )) || {
            _mcp_error 'timeouts must be integer seconds between 1 and 300'; return 1;
        }
    done
    [[ -z "${MCP_TOOLSETS:-}" || "$MCP_TOOLSETS" =~ ^[a-z_]+(,[a-z_]+)*$ ]] || {
        _mcp_error 'invalid toolsets header'; return 1;
    }
    case "${MCP_PROTOCOL_VERSION:-2025-06-18}" in
        2025-06-18|2025-03-26) : ;;
        *) _mcp_error 'unsupported requested protocol version'; return 1 ;;
    esac
    _MCP_URL="$1" _MCP_TOKEN="$2" _MCP_SESSION_ID='' _MCP_NEGOTIATED_PROTOCOL=''
    _MCP_TIMEOUT="${MCP_TIMEOUT:-30}" _MCP_CONNECT_TIMEOUT="${MCP_CONNECT_TIMEOUT:-10}"
    _MCP_TOOLSETS="${MCP_TOOLSETS:-}"
    _MCP_NEXT_REQUEST_ID=1
    params=$(jq -cn --arg version "${MCP_PROTOCOL_VERSION:-2025-06-18}" \
        '{protocolVersion:$version,capabilities:{},clientInfo:{name:"lean-sdd-agent",version:"1.0"}}') || return 1
    _mcp_request initialize "$params" || return 1
    if ! jq -e '
        (.protocolVersion == "2025-06-18" or .protocolVersion == "2025-03-26") and
        (.capabilities.tools | type == "object") and
        (.serverInfo.name | type == "string" and length > 0) and
        (.serverInfo.version | type == "string" and length > 0)
    ' >/dev/null 2>&1 <<< "$_MCP_RESULT"; then
        _mcp_error 'invalid initialize result or unsupported negotiated protocol'
        return 1
    fi
    _MCP_NEGOTIATED_PROTOCOL=$(jq -r '.protocolVersion' <<< "$_MCP_RESULT")
    initialized="$_MCP_RESULT"
    _MCP_CONTEXT='notifications/initialized'
    _mcp_http '{"jsonrpc":"2.0","method":"notifications/initialized"}' notification >/dev/null || return 1
    _MCP_READY=1
    printf '%s\n' "$initialized"
}

mcp_call() {
    _mcp_owner || return 1
    _MCP_CONTEXT='tools/call'
    [[ "$_MCP_READY" == 1 ]] || { _mcp_error 'not connected; explicit reconnect required'; return 1; }
    [[ $# == 2 ]] || { _mcp_error 'usage: mcp_call <tool> <arguments-json>'; return 2; }
    [[ "$1" =~ ^[A-Za-z0-9_.-]+$ ]] || { _mcp_error 'invalid tool name'; return 1; }
    jq -es 'length == 1 and (.[0] | type == "object")' >/dev/null 2>&1 <<< "$2" || {
        _mcp_error 'arguments must be one JSON object'; return 1;
    }
    local params=''
    params=$(jq -cn --arg name "$1" --argjson arguments "$2" '{name:$name,arguments:$arguments}') || return 1
    _mcp_request tools/call "$params" "$1" || return 1
    if ! jq -e '
        (has("isError") | not) or (.isError | type == "boolean")
    ' >/dev/null <<< "$_MCP_RESULT" ||
        jq -e '.isError == true' >/dev/null <<< "$_MCP_RESULT"; then
        _MCP_READY=0
        _mcp_error 'MCP application error or invalid isError; no retry'
        return 1
    fi
    if ! jq -e '
        (.content | type == "array") and
        all(.content[]; type == "object" and (.type | type == "string" and length > 0) and
            (if .type == "text" then (.text | type == "string") else true end)) and
        ((has("structuredContent") | not) or (.structuredContent | type == "object")) and
        ((.content | length > 0) or (.structuredContent | type == "object" and length > 0))
    ' >/dev/null 2>&1 <<< "$_MCP_RESULT"; then
        _MCP_READY=0
        _mcp_error 'empty or malformed tool result'
        return 1
    fi
    printf '%s\n' "$_MCP_RESULT"
}

mcp_list_tools() {
    _mcp_owner || return 1
    _MCP_CONTEXT='tools/list'
    [[ $# == 0 ]] || { _mcp_error 'usage: mcp_list_tools'; return 2; }
    [[ "$_MCP_READY" == 1 ]] || { _mcp_error 'not connected'; return 1; }
    local cursor='' seen='[]' all_tools='[]' params='' page=0
    while :; do
        page=$((page + 1))
        (( page <= 100 )) || { _MCP_READY=0; _mcp_error 'tools/list exceeded 100 pages'; return 1; }
        params=$(jq -cn --arg cursor "$cursor" 'if $cursor == "" then {} else {cursor:$cursor} end') || return 1
        _mcp_request tools/list "$params" || return 1
        if ! jq -e '
            (.tools | type == "array") and
            all(.tools[]; (.name | type == "string" and length > 0) and
                (.inputSchema | type == "object") and .inputSchema.type == "object") and
            ((has("nextCursor") | not) or (.nextCursor | type == "string" and length > 0))
        ' >/dev/null 2>&1 <<< "$_MCP_RESULT"; then
            _MCP_READY=0
            _mcp_error 'malformed tools/list result'
            return 1
        fi
        all_tools=$(jq -cn --argjson previous "$all_tools" --argjson current "$_MCP_RESULT" '$previous + $current.tools') || return 1
        cursor=$(jq -r '.nextCursor // empty' <<< "$_MCP_RESULT")
        [[ -n "$cursor" ]] || break
        if jq -e --arg cursor "$cursor" 'index($cursor) != null' >/dev/null <<< "$seen"; then
            _MCP_READY=0
            _mcp_error 'repeated tools/list cursor'
            return 1
        fi
        seen=$(jq -c --arg cursor "$cursor" '. + [$cursor]' <<< "$seen") || return 1
    done
    if ! jq -e 'map(.name) | length == (unique | length)' >/dev/null <<< "$all_tools"; then
        _MCP_READY=0
        _mcp_error 'duplicate tool names'
        return 1
    fi
    jq -cn --argjson tools "$all_tools" '{tools:$tools}'
}
