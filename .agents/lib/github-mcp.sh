#!/usr/bin/env bash
# Validate the narrow B/C capability contract against actual mcp_list_tools JSON.
# Does not establish permissions, call tools, normalize domain data, or load tests.
# Usage: github_mcp_check_capabilities <tools-json-file>

github_mcp_check_capabilities() {
    [[ $# == 1 && -r "$1" ]] || {
        printf 'ERROR: GitHub MCP capability check requires a readable tools JSON file\n' >&2
        return 2
    }
    local missing=''
    if ! missing=$(jq -ers '
        if length != 1 or (.[0].tools | type) != "array" then error("invalid") else .[0] end |
        .tools as $tools |
        def schema($name):
            [$tools[] | select(.name == $name)] |
            if length == 1 then .[0].inputSchema else null end;
        def fields($name; $fields):
            schema($name) as $schema |
            if $schema.type != "object" then [$name + ": missing/duplicate tool or invalid schema"]
            else [$fields | to_entries[] | . as $field |
                select($schema.properties[$field.key].type != $field.value) |
                $name + "." + $field.key + ": missing/incompatible field"] end;
        def enum($name; $field; $values):
            (schema($name).properties[$field].enum // []) as $actual |
            [$values[] | select(. as $value | $actual | index($value) == null) |
             $name + "." + $field + ": missing enum " + .];
        [fields("get_me"; {}),
         fields("search_repositories"; {query:"string",page:"number",perPage:"number"}),
         fields("issue_write"; {owner:"string",repo:"string",method:"string",issue_number:"number",title:"string",body:"string",state:"string",state_reason:"string"}),
         fields("issue_read"; {owner:"string",repo:"string",method:"string",issue_number:"number"}),
         fields("add_issue_comment"; {owner:"string",repo:"string",issue_number:"number",body:"string"}),
         fields("create_pull_request"; {owner:"string",repo:"string",title:"string",body:"string",head:"string",base:"string"}),
         fields("pull_request_read"; {owner:"string",repo:"string",method:"string",pullNumber:"number"}),
         fields("list_pull_requests"; {owner:"string",repo:"string",head:"string",base:"string",state:"string",page:"number",perPage:"number"}),
         fields("merge_pull_request"; {owner:"string",repo:"string",pullNumber:"number",expectedHeadSha:"string",merge_method:"string"}),
         enum("issue_write"; "method"; ["create","update"]),
         enum("issue_write"; "state"; ["open","closed"]),
         enum("issue_write"; "state_reason"; ["completed"]),
         enum("issue_read"; "method"; ["get"]),
         enum("pull_request_read"; "method"; ["get"]),
         enum("merge_pull_request"; "merge_method"; ["merge"])] | add | join("; ")
    ' "$1" 2>/dev/null); then
        printf 'ERROR: malformed GitHub MCP capability data\n' >&2
        return 1
    fi
    if [[ -n "$missing" ]]; then
        printf 'ERROR: GitHub MCP capability unavailable: %s; dependent B/C/D blocked\n' "$missing" >&2
        return 1
    fi
    printf '{"schema_verified":true,"write_access_verified":false}\n'
}
