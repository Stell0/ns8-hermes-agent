*** Settings ***
Library    Collections
Library    SSHLibrary

*** Test Cases ***
Check if hermes-agent is installed correctly
    ${output}  ${rc} =    Execute Command    add-module ${IMAGE_URL} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}  0
    &{output} =    Evaluate    ${output}
    Set Suite Variable    ${module_id}    ${output.module_id}
    ${module_home} =    Execute Command    getent passwd ${module_id} | cut -d: -f6
    Set Suite Variable    ${module_home}    ${module_home}

Check if hermes-agent can be configured with mixed agent states
    ${configure_payload} =    Set Variable    {"agents":[{"id":1,"name":"Foo Bar","role":"developer","status":"start"},{"id":2,"name":"Alice User","role":"default","status":"stop"}],"openviking":{"embedding":{"provider":"jina","api_key":"test-embedding-key"}}}
    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${configure_payload}'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0

Check if hermes-agent creates shared and per-running-agent runtime files
    ${environment_file} =    Execute Command    find ${module_home} -maxdepth 8 -name 'environment' -print -quit
    ${shared_secrets} =    Execute Command    find ${module_home} -maxdepth 8 -name 'secrets.env' -print -quit
    ${systemd_env} =    Execute Command    find ${module_home} -maxdepth 8 -name 'systemd.env' -print -quit
    ${shared_openviking} =    Execute Command    find ${module_home} -maxdepth 8 -name 'openviking.conf' -print -quit
    ${system_agent_env} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent-0.env' -print -quit
    ${system_agent_secrets} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent-0_secrets.env' -print -quit
    ${agent1_env} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent-1.env' -print -quit
    ${agent1_secrets} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent-1_secrets.env' -print -quit
    ${agent2_env} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent-2.env' -print -quit
    ${agent2_secrets} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent-2_secrets.env' -print -quit
    ${agent2_openviking} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent-2_openviking.conf' -print -quit
    ${tcp_port} =    Execute Command    grep '^TCP_PORT=' ${environment_file} | cut -d= -f2-
    ${openviking_port} =    Execute Command    grep '^OPENVIKING_PORT=' ${environment_file} | cut -d= -f2-
    ${system_api_port} =    Execute Command    grep '^HERMES_SYSTEM_API_PORT=' ${environment_file} | cut -d= -f2-
    ${root_openviking_key} =    Execute Command    grep '^OPENVIKING_ROOT_API_KEY=' ${shared_secrets} | cut -d= -f2-
    ${embedding_key} =    Execute Command    grep '^OPENVIKING_EMBEDDING_API_KEY=' ${shared_secrets} | cut -d= -f2-
    ${system_api_key} =    Execute Command    grep '^API_SERVER_KEY=' ${system_agent_secrets} | cut -d= -f2-
    ${system_api_enabled} =    Execute Command    grep '^API_SERVER_ENABLED=' ${system_agent_env} | cut -d= -f2-
    ${system_api_host} =    Execute Command    grep '^API_SERVER_HOST=' ${system_agent_env} | cut -d= -f2-
    ${system_api_container_port} =    Execute Command    grep '^API_SERVER_PORT=' ${system_agent_env} | cut -d= -f2-
    ${system_gateway_port} =    Execute Command    grep '^HERMES_GATEWAY_PORT=' ${system_agent_env} | cut -d= -f2-
    ${vlm_provider} =    Execute Command    python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["vlm"]["provider"])' ${shared_openviking}
    ${vlm_api_base} =    Execute Command    python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["vlm"]["api_base"])' ${shared_openviking}
    ${embedding_provider} =    Execute Command    python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["embedding"]["dense"]["provider"])' ${shared_openviking}
    ${agent1_openviking_key} =    Execute Command    grep '^OPENVIKING_API_KEY=' ${agent1_secrets} | cut -d= -f2-
    Should Not Be Empty    ${environment_file}
    Should Not Be Empty    ${shared_secrets}
    Should Not Be Empty    ${systemd_env}
    Should Not Be Empty    ${shared_openviking}
    Should Not Be Empty    ${system_agent_env}
    Should Not Be Empty    ${system_agent_secrets}
    Should Not Be Empty    ${agent1_env}
    Should Not Be Empty    ${agent1_secrets}
    Should Be Empty    ${agent2_env}
    Should Be Empty    ${agent2_secrets}
    Should Be Empty    ${agent2_openviking}
    Should Not Be Empty    ${tcp_port}
    Should Not Be Empty    ${openviking_port}
    Should Be Equal    ${openviking_port}    ${tcp_port}
    Should Not Be Empty    ${system_api_port}
    Should Not Be Empty    ${root_openviking_key}
    Should Be Equal    ${embedding_key}    test-embedding-key
    Should Not Be Empty    ${system_api_key}
    Should Be Equal    ${system_api_enabled}    true
    Should Be Equal    ${system_api_host}    0.0.0.0
    Should Be Equal    ${system_api_container_port}    8642
    Should Be Equal    ${system_gateway_port}    8642
    Should Be Equal    ${vlm_provider}    openai
    Should Contain    ${vlm_api_base}    /v1
    Should Be Equal    ${embedding_provider}    jina
    Should Not Be Empty    ${agent1_openviking_key}
    Set Suite Variable    ${agent1_openviking_key}
    Set Suite Variable    ${root_openviking_key}
    Set Suite Variable    ${openviking_port}
    Set Suite Variable    ${system_api_key}
    Set Suite Variable    ${system_api_port}

Check if hermes-agent returns actual agent states and tenant metadata
    ${output} =    Execute Command    api-cli run module/${module_id}/get-configuration --data '{}'
    ${agent_count} =    Evaluate    len(json.loads(r'''${output}''')["agents"])    json
    ${system_status} =    Evaluate    next(item["status"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 0)    json
    ${system_hidden} =    Evaluate    next(item["hidden"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 0)    json
    ${system_protected} =    Evaluate    next(item["protected"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 0)    json
    ${system_flag} =    Evaluate    next(item["system"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 0)    json
    ${embedding_provider_output} =    Evaluate    json.loads(r'''${output}''')["openviking"]["embedding"]["provider"]    json
    ${embedding_key_configured} =    Evaluate    json.loads(r'''${output}''')["openviking"]["embedding"]["api_key_configured"]    json
    ${agent1_name} =    Evaluate    next(item["name"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 1)    json
    ${agent1_role} =    Evaluate    next(item["role"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 1)    json
    ${agent1_status} =    Evaluate    next(item["status"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 1)    json
    ${agent1_account} =    Evaluate    next(item["account"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 1)    json
    ${agent1_user} =    Evaluate    next(item["user"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 1)    json
    ${agent1_agent_id} =    Evaluate    next(item["agent_id"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 1)    json
    ${agent2_name} =    Evaluate    next(item["name"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 2)    json
    ${agent2_role} =    Evaluate    next(item["role"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 2)    json
    ${agent2_status} =    Evaluate    next(item["status"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 2)    json
    ${agent2_account} =    Evaluate    next(item["account"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 2)    json
    ${agent2_user} =    Evaluate    next(item["user"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 2)    json
    ${agent2_agent_id} =    Evaluate    next(item["agent_id"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 2)    json
    Should Be Equal As Integers    ${agent_count}  3
    Should Be Equal    ${system_status}  start
    Should Be True    ${system_hidden}
    Should Be True    ${system_protected}
    Should Be True    ${system_flag}
    Should Be Equal    ${embedding_provider_output}  jina
    Should Be True    ${embedding_key_configured}
    Should Be Equal    ${agent1_name}  Foo Bar
    Should Be Equal    ${agent1_role}  developer
    Should Be Equal    ${agent1_status}  start
    Should Not Be Empty    ${agent1_account}
    Should Not Be Empty    ${agent1_user}
    Should Not Be Empty    ${agent1_agent_id}
    Should Be Equal    ${agent2_name}  Alice User
    Should Be Equal    ${agent2_role}  default
    Should Be Equal    ${agent2_status}  stop
    Should Not Be Empty    ${agent2_account}
    Should Not Be Empty    ${agent2_user}
    Should Not Be Empty    ${agent2_agent_id}
    Set Suite Variable    ${agent1_account}
    Set Suite Variable    ${agent1_user}
    Set Suite Variable    ${agent1_agent_id}
    Set Suite Variable    ${agent2_account}
    Set Suite Variable    ${agent2_user}
    Set Suite Variable    ${agent2_agent_id}

Check if hermes-agent starts one shared OpenViking service and one runtime per running agent
    ${target1_output}  ${target1_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent@1.target'
    ...    return_rc=True
    ${system_hermes_output}  ${system_hermes_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent-hermes-system.service'
    ...    return_rc=True
    ${pod_output}  ${pod_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent-pod@1.service'
    ...    return_rc=True
    ${openviking_output}  ${openviking_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent-openviking.service'
    ...    return_rc=True
    ${legacy_openviking_output}  ${legacy_openviking_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent-openviking@1.service'
    ...    return_rc=True
    ${hermes_output}  ${hermes_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent-hermes@1.service'
    ...    return_rc=True
    ${gateway_output}  ${gateway_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent-gateway@1.service'
    ...    return_rc=True
    ${shared_container_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman container exists hermes-agent-openviking'
    ...    return_rc=True  return_stdout=False
    ${system_hermes_container_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman container exists hermes-agent-hermes-0'
    ...    return_rc=True  return_stdout=False
    ${hermes_container_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman container exists hermes-agent-hermes-1'
    ...    return_rc=True  return_stdout=False
    ${pod_exists_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman pod exists hermes-agent-1'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${target1_rc}  0
    Should Not Be Equal As Integers    ${pod_rc}  0
    Should Be Equal As Integers    ${openviking_rc}  0
    Should Be Equal As Integers    ${system_hermes_rc}  0
    Should Not Be Equal As Integers    ${legacy_openviking_rc}  0
    Should Be Equal As Integers    ${hermes_rc}  0
    Should Not Be Equal As Integers    ${gateway_rc}  0
    Should Be Equal As Integers    ${shared_container_rc}  0
    Should Be Equal As Integers    ${system_hermes_container_rc}  0
    Should Be Equal As Integers    ${hermes_container_rc}  0
    Should Not Be Equal As Integers    ${pod_exists_rc}  0
    Should Be Equal    ${target1_output}  active
    Should Be Equal    ${openviking_output}  active
    Should Be Equal    ${system_hermes_output}  active
    Should Be Equal    ${hermes_output}  active

Check if hermes-agent creates persistent volumes and keeps data across restart
    ${system_hermes_volume_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman volume exists hermes-agent-hermes-data-0'
    ...    return_rc=True  return_stdout=False
    ${hermes_volume_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman volume exists hermes-agent-hermes-data-1'
    ...    return_rc=True  return_stdout=False
    ${openviking_volume_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman volume exists hermes-agent-openviking-data'
    ...    return_rc=True  return_stdout=False
    ${write_runtime_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman exec hermes-agent-hermes-1 sh -lc "printf persistent > /opt/data/persist-sentinel"'
    ...    return_rc=True  return_stdout=False
    ${write_openviking_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman exec hermes-agent-openviking sh -lc "mkdir -p /app/data/test && printf persistent > /app/data/test/persist-sentinel"'
    ...    return_rc=True  return_stdout=False
    ${restart_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user restart hermes-agent@1.target'
    ...    return_rc=True  return_stdout=False
    ${hermes_restart_output}  ${hermes_restart_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent-hermes@1.service'
    ...    return_rc=True
    ${openviking_restart_output}  ${openviking_restart_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent-openviking.service'
    ...    return_rc=True
    ${runtime_sentinel} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman exec hermes-agent-hermes-1 sh -lc "cat /opt/data/persist-sentinel"'
    ${openviking_sentinel} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman exec hermes-agent-openviking sh -lc "cat /app/data/test/persist-sentinel"'
    Should Be Equal As Integers    ${system_hermes_volume_rc}  0
    Should Be Equal As Integers    ${hermes_volume_rc}  0
    Should Be Equal As Integers    ${openviking_volume_rc}  0
    Should Be Equal As Integers    ${write_runtime_rc}  0
    Should Be Equal As Integers    ${write_openviking_rc}  0
    Should Be Equal As Integers    ${restart_rc}  0
    Should Be Equal As Integers    ${hermes_restart_rc}  0
    Should Be Equal As Integers    ${openviking_restart_rc}  0
    Should Be Equal    ${hermes_restart_output}  active
    Should Be Equal    ${openviking_restart_output}  active
    Should Be Equal    ${runtime_sentinel}  persistent
    Should Be Equal    ${openviking_sentinel}  persistent

Check if hermes-agent keeps stopped agents inactive
    ${target2_output}  ${target2_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent@2.target'
    ...    return_rc=True
    ${runtime2_exists_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman container exists hermes-agent-hermes-2'
    ...    return_rc=True  return_stdout=False
    Should Not Be Equal As Integers    ${target2_rc}  0
    Should Not Be Equal As Integers    ${runtime2_exists_rc}  0
    Should Be Equal    ${target2_output}  inactive

Check if hermes-agent can start a second agent on the shared OpenViking instance
    ${configure_payload} =    Set Variable    {"agents":[{"id":1,"name":"Foo Bar","role":"developer","status":"start"},{"id":2,"name":"Alice User","role":"default","status":"start"}],"openviking":{"embedding":{"provider":"jina"}}}
    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${configure_payload}'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0
    ${agent2_env} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent-2.env' -print -quit
    ${agent2_secrets} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent-2_secrets.env' -print -quit
    ${agent2_openviking_key} =    Execute Command    grep '^OPENVIKING_API_KEY=' ${agent2_secrets} | cut -d= -f2-
    ${target2_output}  ${target2_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent@2.target'
    ...    return_rc=True
    ${shared_openviking_output}  ${shared_openviking_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent-openviking.service'
    ...    return_rc=True
    ${runtime2_exists_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman container exists hermes-agent-hermes-2'
    ...    return_rc=True  return_stdout=False
    Should Not Be Empty    ${agent2_env}
    Should Not Be Empty    ${agent2_secrets}
    Should Not Be Empty    ${agent2_openviking_key}
    Should Not Be Equal    ${agent1_openviking_key}  ${agent2_openviking_key}
    Should Be Equal As Integers    ${target2_rc}  0
    Should Be Equal As Integers    ${shared_openviking_rc}  0
    Should Be Equal As Integers    ${runtime2_exists_rc}  0
    Should Be Equal    ${target2_output}  active
    Should Be Equal    ${shared_openviking_output}  active
    Set Suite Variable    ${agent2_openviking_key}

Check if shared OpenViking keeps agent accounts isolated
    ${accounts_output} =    Execute Command    curl -sf -H 'X-API-Key: ${root_openviking_key}' http://127.0.0.1:${openviking_port}/api/v1/admin/accounts
    ${account_ids} =    Evaluate    sorted(item["account_id"] for item in json.loads(r'''${accounts_output}''')["result"])    json
    ${agent1_own_users_rc} =    Execute Command    curl -sf -H 'X-API-Key: ${agent1_openviking_key}' http://127.0.0.1:${openviking_port}/api/v1/admin/accounts/${agent1_account}/users
    ...    return_rc=True  return_stdout=False
    ${agent1_other_users_rc} =    Execute Command    curl -sf -H 'X-API-Key: ${agent1_openviking_key}' http://127.0.0.1:${openviking_port}/api/v1/admin/accounts/${agent2_account}/users
    ...    return_rc=True  return_stdout=False
    ${agent2_own_users_rc} =    Execute Command    curl -sf -H 'X-API-Key: ${agent2_openviking_key}' http://127.0.0.1:${openviking_port}/api/v1/admin/accounts/${agent2_account}/users
    ...    return_rc=True  return_stdout=False
    ${agent2_other_users_rc} =    Execute Command    curl -sf -H 'X-API-Key: ${agent2_openviking_key}' http://127.0.0.1:${openviking_port}/api/v1/admin/accounts/${agent1_account}/users
    ...    return_rc=True  return_stdout=False
    Length Should Be    ${account_ids}    3
    List Should Contain Value    ${account_ids}    system
    List Should Contain Value    ${account_ids}    ${agent1_account}
    List Should Contain Value    ${account_ids}    ${agent2_account}
    Should Be Equal As Integers    ${agent1_own_users_rc}  0
    Should Not Be Equal As Integers    ${agent1_other_users_rc}  0
    Should Be Equal As Integers    ${agent2_own_users_rc}  0
    Should Not Be Equal As Integers    ${agent2_other_users_rc}  0

Check if hermes-agent cleans removed agents and keeps shared OpenViking accounts in sync
    ${configure_payload} =    Set Variable    {"agents":[{"id":2,"name":"Alice User","role":"default","status":"start"}],"openviking":{"embedding":{"provider":"volcengine","api_key":"rotated-embedding-key"}}}
    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${configure_payload}'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0
    ${output} =    Execute Command    api-cli run module/${module_id}/get-configuration --data '{}'
    ${agent_count} =    Evaluate    len(json.loads(r'''${output}''')["agents"])    json
    ${remaining_id} =    Evaluate    next(item["id"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 2)    json
    ${remaining_status} =    Evaluate    next(item["status"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 2)    json
    ${remaining_account} =    Evaluate    next(item["account"] for item in json.loads(r'''${output}''')["agents"] if item["id"] == 2)    json
    ${embedding_provider_after} =    Evaluate    json.loads(r'''${output}''')["openviking"]["embedding"]["provider"]    json
    ${agent1_env} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent-1.env' -print -quit
    ${agent1_secrets} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent-1_secrets.env' -print -quit
    ${agent1_openviking} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent-1_openviking.conf' -print -quit
    ${agent2_secrets} =    Execute Command    find ${module_home} -maxdepth 8 -name 'agent-2_secrets.env' -print -quit
    ${agent2_openviking_key_after} =    Execute Command    grep '^OPENVIKING_API_KEY=' ${agent2_secrets} | cut -d= -f2-
    ${embedding_key_after} =    Execute Command    grep '^OPENVIKING_EMBEDDING_API_KEY=' ${shared_secrets} | cut -d= -f2-
    ${accounts_output} =    Execute Command    curl -sf -H 'X-API-Key: ${root_openviking_key}' http://127.0.0.1:${openviking_port}/api/v1/admin/accounts
    ${account_ids} =    Evaluate    sorted(item["account_id"] for item in json.loads(r'''${accounts_output}''')["result"])    json
    ${target1_output}  ${target1_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent@1.target'
    ...    return_rc=True
    ${target2_output}  ${target2_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'systemctl --user is-active hermes-agent@2.target'
    ...    return_rc=True
    ${runtime1_exists_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman container exists hermes-agent-hermes-1'
    ...    return_rc=True  return_stdout=False
    ${runtime2_exists_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman container exists hermes-agent-hermes-2'
    ...    return_rc=True  return_stdout=False
    ${hermes_volume1_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman volume exists hermes-agent-hermes-data-1'
    ...    return_rc=True  return_stdout=False
    ${openviking_volume_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman volume exists hermes-agent-openviking-data'
    ...    return_rc=True  return_stdout=False
    ${hermes_volume2_rc} =    Execute Command    runuser -u ${module_id} -- bash -lc 'podman volume exists hermes-agent-hermes-data-2'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${agent_count}  2
    Should Be Equal As Integers    ${remaining_id}  2
    Should Be Equal    ${remaining_status}  start
    Should Be Equal    ${remaining_account}  ${agent2_account}
    Should Be Equal    ${embedding_provider_after}  volcengine
    Should Be Empty    ${agent1_env}
    Should Be Empty    ${agent1_secrets}
    Should Be Empty    ${agent1_openviking}
    Should Be Equal    ${agent2_openviking_key_after}  ${agent2_openviking_key}
    Should Be Equal    ${embedding_key_after}  rotated-embedding-key
    Length Should Be    ${account_ids}    2
    List Should Contain Value    ${account_ids}    system
    List Should Contain Value    ${account_ids}    ${agent2_account}
    List Should Not Contain Value    ${account_ids}    ${agent1_account}
    Should Not Be Equal As Integers    ${target1_rc}  0
    Should Be Equal    ${target1_output}  inactive
    Should Be Equal As Integers    ${target2_rc}  0
    Should Be Equal    ${target2_output}  active
    Should Not Be Equal As Integers    ${runtime1_exists_rc}  0
    Should Be Equal As Integers    ${runtime2_exists_rc}  0
    Should Not Be Equal As Integers    ${hermes_volume1_rc}  0
    Should Be Equal As Integers    ${openviking_volume_rc}  0
    Should Be Equal As Integers    ${hermes_volume2_rc}  0

Check if hermes-agent is removed correctly
    ${rc} =    Execute Command    remove-module --no-preserve ${module_id}
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0
