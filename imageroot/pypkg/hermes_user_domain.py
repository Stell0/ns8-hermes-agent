import importlib
import sys


USER_DOMAIN_ENV = "USER_DOMAIN"
LDAP_HOST_ENV = "LDAP_HOST"
LDAP_PORT_ENV = "LDAP_PORT"
LDAP_BASE_DN_ENV = "LDAP_BASE_DN"
LDAP_SCHEMA_ENV = "LDAP_SCHEMA"
LDAP_BIND_DN_ENV = "LDAP_BIND_DN"
LDAP_BIND_PASSWORD_ENV = "LDAP_BIND_PASSWORD"
PODMAN_LOOPBACK_HOST = "10.0.2.2"


def normalize_user_domain(value):
    return (value or "").strip().lower()


def normalize_allowed_user(value):
    return (value or "").strip()


def auth_required(base_virtualhost, agents):
    return bool((base_virtualhost or "").strip()) and bool(agents)


def _ldapproxy_client():
    ldapproxy_module = sys.modules.get("agent.ldapproxy")
    if ldapproxy_module is None:
        ldapproxy_module = importlib.import_module("agent.ldapproxy")

    return ldapproxy_module.Ldapproxy()


def _ldapclient_factory():
    ldapclient_module = sys.modules.get("agent.ldapclient")
    if ldapclient_module is None:
        ldapclient_module = importlib.import_module("agent.ldapclient")

    return ldapclient_module.Ldapclient


def list_user_domains():
    return sorted(_ldapproxy_client().get_domains_list())


def get_domain_details(user_domain):
    normalized_domain = normalize_user_domain(user_domain)
    if not normalized_domain:
        return None

    return _ldapproxy_client().get_domain(normalized_domain)


def list_domain_users(user_domain, extra_info=True):
    domain_details = get_domain_details(user_domain)
    if domain_details is None:
        raise ValueError(f"user domain not found: {user_domain}")

    users = _ldapclient_factory().factory(**domain_details).list_users(extra_info=extra_info)
    return sorted(users, key=lambda record: record["user"])


def list_domain_usernames(user_domain):
    return {record["user"] for record in list_domain_users(user_domain, extra_info=False)}


def public_runtime_env(user_domain):
    domain_details = get_domain_details(user_domain)
    if domain_details is None:
        return {}

    ldap_host = domain_details.get("host") or ""
    if ldap_host in {"127.0.0.1", "localhost"}:
        ldap_host = PODMAN_LOOPBACK_HOST

    env_data = {
        USER_DOMAIN_ENV: normalize_user_domain(user_domain),
        LDAP_HOST_ENV: ldap_host,
        LDAP_PORT_ENV: str(domain_details["port"]),
        LDAP_BASE_DN_ENV: domain_details["base_dn"],
        LDAP_SCHEMA_ENV: domain_details["schema"],
    }

    return {key: value for key, value in env_data.items() if value not in (None, "")}


def secrets_runtime_env(user_domain):
    domain_details = get_domain_details(user_domain)
    if domain_details is None:
        return {}

    env_data = {
        LDAP_BIND_DN_ENV: domain_details.get("bind_dn") or "",
        LDAP_BIND_PASSWORD_ENV: domain_details.get("bind_password") or "",
    }

    return {key: value for key, value in env_data.items() if value not in (None, "")}