*** Settings ***
Library    Collections
Library    SSHLibrary

*** Test Cases ***
Check if hermes-agent is installed correctly
    ${output}  ${rc} =    Execute Command    add-module ${IMAGE_URL} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    &{output} =    Evaluate    ${output}
    Set Suite Variable    ${module_id}    ${output.module_id}
    ${module_home} =    Execute Command    getent passwd ${module_id} | cut -d: -f6
    Set Suite Variable    ${module_home}    ${module_home}

Check if install starts with no agent runtime
    ${active_units} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user list-units "hermes-agent@*.service" --state=active --no-legend | wc -l'
    ${running_containers} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman ps --format "{{.Names}}" | grep -c "^hermes-agent-" || true'
    Should Be Equal    ${active_units}    0
    Should Be Equal    ${running_containers}    0

Check if configure with zero agents keeps module idle
    ${configure_payload} =    Set Variable    {"agents":[]}
    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${configure_payload}'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${output} =    Execute Command    api-cli run module/${module_id}/get-configuration --data '{}'
    ${agent_count} =    Evaluate    len(json.loads(r'''${output}''')['agents'])    json
    ${active_units} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user list-units "hermes-agent@*.service" --state=active --no-legend | wc -l'
    Should Be Equal As Integers    ${agent_count}    0
    Should Be Equal    ${active_units}    0

Check if one started agent creates one runtime
    ${configure_payload} =    Set Variable    {"base_virtualhost":"agents.example.test","agents":[{"id":1,"name":"Foo Bar","role":"developer","status":"start"}]}
    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${configure_payload}'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${settled_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'for attempt in $(seq 1 20); do systemctl --user is-active --quiet hermes-agent@1.service && podman container exists hermes-agent-1 && podman exec hermes-agent-1 test -f /opt/data/SOUL.md && podman exec hermes-agent-1 test -f /opt/data/.env && exit 0; sleep 1; done; exit 1'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${settled_rc}    0
    ${output} =    Execute Command    api-cli run module/${module_id}/get-configuration --data '{}'
    ${base_virtualhost} =    Evaluate    json.loads(r'''${output}''')['base_virtualhost']    json
    ${agent_status} =    Evaluate    json.loads(r'''${output}''')['agents'][0]['status']    json
    ${agent_runtime_status} =    Evaluate    json.loads(r'''${output}''')['agents'][0]['runtime_status']    json

    ${agent_env} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent_1.env' -print -quit
    ${agent_secrets} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent_1_secrets.env' -print -quit
    ${agent_metadata} =    Execute Command    find ${module_home} -maxdepth 8 -path '*/agents/1/metadata.json' -print -quit
    ${generated_env_count} =    Execute Command    find ${module_home} -maxdepth 8 -regextype posix-extended -regex '.*/agent_1(_secrets)?\.env' | wc -l
    ${service_output}  ${service_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent@1.service'
    ...    return_rc=True
    ${running_containers} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman ps --format "{{.Names}}" | grep -c "^hermes-agent-" || true'
    ${container_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman container exists hermes-agent-1'
    ...    return_rc=True  return_stdout=False
    ${volume_name} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman volume inspect --format "{{.Name}}" hermes-agent-1-home'
    ${agent_name_env} =    Execute Command    grep '^AGENT_NAME=' ${agent_env} | cut -d= -f2-
    ${agent_role_env} =    Execute Command    grep '^AGENT_ROLE=' ${agent_env} | cut -d= -f2-
    ${agent_dashboard_port} =    Execute Command    grep '^AGENT_DASHBOARD_HOST_PORT=' ${agent_env} | cut -d= -f2-
    ${agent_secret} =    Execute Command    grep '^HERMES_AGENT_SECRET=' ${agent_secrets} | cut -d= -f2-
    ${secret_key_count} =    Execute Command    grep -Ec '^(HERMES_AGENT_SECRET|SMTP_PASSWORD)=' ${agent_secrets}
    ${route_output} =    Execute Command    api-cli run module/traefik1/get-route --data '{"instance":"${module_id}-hermes-agent-1"}'
    ${route_host} =    Evaluate    json.loads(r'''${route_output}''')['host']    json
    ${route_path} =    Evaluate    json.loads(r'''${route_output}''')['path']    json
    ${soul_content} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman exec hermes-agent-1 cat /opt/data/SOUL.md'
    ${home_env_content} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman exec hermes-agent-1 cat /opt/data/.env'

    Should Not Be Empty    ${agent_env}
    Should Not Be Empty    ${agent_secrets}
    Should Not Be Empty    ${agent_metadata}
    Should Be Equal    ${volume_name}    hermes-agent-1-home
    Should Be Equal    ${generated_env_count}    2
    Should Be Equal    ${base_virtualhost}    agents.example.test
    Should Be Equal    ${agent_status}    start
    Should Be Equal    ${agent_runtime_status}    start
    Should Be Equal As Integers    ${service_rc}    0
    Should Be Equal    ${running_containers}    1
    Should Be Equal As Integers    ${container_rc}    0
    Should Be Equal    ${service_output}    active
    Should Be Equal    ${agent_name_env}    Foo Bar
    Should Be Equal    ${agent_role_env}    developer
    Should Not Be Empty    ${agent_dashboard_port}
    Should Not Be Empty    ${agent_secret}
    Should Be Equal    ${secret_key_count}    1
    Should Be Equal    ${route_host}    agents.example.test
    Should Be Equal    ${route_path}    /hermes-agent-1
    Should Contain    ${soul_content}    Your name is Foo Bar, you are an Hermes Agent that runs on NethServer8
    Should Contain    ${soul_content}    You are a pragmatic technical partner who values correctness, clarity, and operational reality.
    Should Contain    ${home_env_content}    AGENT_NAME=Foo Bar

Check if stopped agent disables runtime but keeps files
    ${configure_payload} =    Set Variable    {"agents":[{"id":1,"name":"Foo Bar","role":"developer","status":"stop"}]}
    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${configure_payload}'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${output} =    Execute Command    api-cli run module/${module_id}/get-configuration --data '{}'
    ${agent_status} =    Evaluate    json.loads(r'''${output}''')['agents'][0]['status']    json
    ${agent_runtime_status} =    Evaluate    json.loads(r'''${output}''')['agents'][0]['runtime_status']    json
    ${service_output}  ${service_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent@1.service'
    ...    return_rc=True
    ${running_containers} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman ps --format "{{.Names}}" | grep -c "^hermes-agent-" || true'
    ${container_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman container exists hermes-agent-1'
    ...    return_rc=True  return_stdout=False
    ${agent_env} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent_1.env' -print -quit
    ${volume_name} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman volume inspect --format "{{.Name}}" hermes-agent-1-home'
    Should Be Equal    ${agent_status}    stop
    Should Be Equal    ${agent_runtime_status}    stop
    Should Not Be Equal As Integers    ${service_rc}    0
    Should Be Equal    ${running_containers}    0
    Should Not Be Equal As Integers    ${container_rc}    0
    Should Not Be Empty    ${agent_env}
    Should Be Equal    ${volume_name}    hermes-agent-1-home
    Should Be Equal    ${service_output}    inactive

Check if deleting agent cleans runtime files
    ${configure_payload} =    Set Variable    {"agents":[]}
    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${configure_payload}'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${output} =    Execute Command    api-cli run module/${module_id}/get-configuration --data '{}'
    ${agent_count} =    Evaluate    len(json.loads(r'''${output}''')['agents'])    json
    ${service_output}  ${service_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent@1.service'
    ...    return_rc=True
    ${running_containers} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman ps --format "{{.Names}}" | grep -c "^hermes-agent-" || true'
    ${container_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman container exists hermes-agent-1'
    ...    return_rc=True  return_stdout=False
    ${agent_env} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent_1.env' -print -quit
    ${generated_env_count} =    Execute Command    find ${module_home} -maxdepth 8 -regextype posix-extended -regex '.*/agent_1(_secrets)?\.env' | wc -l
    ${agent_secrets} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent_1_secrets.env' -print -quit
    ${agent_metadata} =    Execute Command    find ${module_home} -maxdepth 8 -path '*/agents/1/metadata.json' -print -quit
    ${volume_exists_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman volume exists hermes-agent-1-home'
    ...    return_rc=True  return_stdout=False
    ${route_output} =    Execute Command    api-cli run module/traefik1/get-route --data '{"instance":"${module_id}-hermes-agent-1"}'
    Should Be Equal As Integers    ${agent_count}    0
    Should Not Be Equal As Integers    ${service_rc}    0
    Should Be Equal    ${running_containers}    0
    Should Not Be Equal As Integers    ${container_rc}    0
    Should Be Empty    ${agent_env}
    Should Be Equal    ${generated_env_count}    0
    Should Be Empty    ${agent_secrets}
    Should Be Empty    ${agent_metadata}
    Should Not Be Equal As Integers    ${volume_exists_rc}    0
    Should Be Equal    ${route_output}    {}
    Should Be Equal    ${service_output}    inactive

Check if hermes-agent can be removed cleanly
    ${rc} =    Execute Command    remove-module --no-preserve ${module_id}
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${module_home_exists_rc} =    Execute Command    test -e ${module_home}
    ...    return_rc=True  return_stdout=False
    Should Not Be Equal As Integers    ${module_home_exists_rc}    0