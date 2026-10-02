#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import base64
import traceback

import yaml
from ansible.module_utils.basic import AnsibleModule

try:
    from kubernetes import client as k8s_client
    from kubernetes.client import Configuration, ApiClient
    from kubernetes.client.rest import ApiException
    HAS_K8S = True
except ImportError:
    HAS_K8S = False


ARGUMENT_SPEC = dict(
    api_url=dict(type='str', required=True),
    api_key=dict(type='str', required=True, no_log=True),
    validate_certs=dict(type='bool', default=False),
    mode=dict(type='str', default='cluster', choices=['cluster', 'tenant']),
    application_name=dict(type='str', default='cluster-security-policy'),
    application_namespace=dict(type='str', default='openshift-gitops'),
    tenant_user=dict(type='str', default=''),
    tenant_uuid=dict(type='str', default=''),
    tenant_role=dict(type='str', default='admin'),
    namespace_specs=dict(type='list', elements='dict', default=[]),
    expected_quota=dict(type='dict', default={}),
    quota_is_complete=dict(type='bool', default=False),
    use_cluster_quota=dict(type='bool', default=True),
    egress_firewall=dict(type='bool', default=False),
    expected_tenant_domains=dict(type='list', elements='str', default=[]),
    expected_tenant_cidrs=dict(type='list', elements='str', default=[]),
    expected_namespace_allows=dict(type='list', elements='str', default=[]),
    showroom_namespace=dict(type='str', default=''),
    admin_token=dict(type='str', default='', no_log=True),
)


def make_client(params):
    conf = Configuration()
    conf.host = params['api_url']
    conf.api_key = {'authorization': 'Bearer ' + params['api_key']}
    conf.verify_ssl = params['validate_certs']
    return ApiClient(conf)


def get_custom(api, group, version, name, namespace=None):
    try:
        if namespace:
            return api.get_namespaced_custom_object(group, version, namespace, plural_for(group, version), name)
        return api.get_cluster_custom_object(group, version, plural_for(group, version), name)
    except ApiException as e:
        if e.status == 404:
            return None
        raise


def list_custom(api, group, version, namespace=None, label_selector=None):
    try:
        if namespace:
            return api.list_namespaced_custom_object(
                group, version, namespace, plural_for(group, version),
                label_selector=label_selector or ''
            )
        return api.list_cluster_custom_object(
            group, version, plural_for(group, version),
            label_selector=label_selector or ''
        )
    except ApiException as e:
        if e.status == 404:
            return {'items': []}
        raise


# Map (group, version) to the plural resource name the API expects.
# Custom resources don't follow a single convention, so we maintain
# an explicit mapping for every type we query.
_PLURALS = {
    ('argoproj.io', 'v1alpha1'): 'applications',
    ('admissionregistration.k8s.io', 'v1'): 'validatingadmissionpolicies',
    ('config.openshift.io', 'v1'): 'images',
    ('quota.openshift.io', 'v1'): 'clusterresourcequotas',
    ('policy.networking.k8s.io', 'v1alpha1'): 'adminnetworkpolicies',
    ('k8s.ovn.org', 'v1'): 'egressfirewalls',
}


def plural_for(group, version):
    return _PLURALS[(group, version)]


# ---------- findings helpers ----------

def finding(check, ok, detail):
    return {'check': check, 'ok': ok, 'detail': detail}


def findings_to_user_data(findings, mode):
    prefix = mode + '_security_finding_'
    failed = [f for f in findings if not f['ok']]
    data = {
        mode + '_security_report_status': 'failed' if failed else 'passed',
    }
    for i, f in enumerate(findings):
        data[prefix + str(i) + '_check'] = f['check']
        data[prefix + str(i) + '_status'] = 'PASS' if f['ok'] else 'FAIL'
        data[prefix + str(i) + '_detail'] = f['detail']
    return data


# ---------- cluster-level checks ----------

def check_argocd(custom_api, params):
    app = get_custom(
        custom_api, 'argoproj.io', 'v1alpha1',
        params['application_name'],
        namespace=params['application_namespace'],
    )
    if app is None:
        return None, finding(
            'Cluster security policy (ArgoCD)', False,
            'Application %s not found in %s' % (params['application_name'], params['application_namespace'])
        )

    health = app.get('status', {}).get('health', {}).get('status', 'missing')
    sync = app.get('status', {}).get('sync', {}).get('status', 'missing')
    ok = health == 'Healthy' and sync == 'Synced'

    helm_values_str = app.get('spec', {}).get('source', {}).get('helm', {}).get('values', '')
    desired = yaml.safe_load(helm_values_str) if helm_values_str else {}

    return desired, finding(
        'Cluster security policy (ArgoCD)', ok,
        '%s, %s' % (health, sync)
    )


def check_vap(custom_api, desired):
    vap_config = desired.get('denyExternalNameServices', {})
    enabled = vap_config.get('enabled', True)
    want_label = vap_config.get('subjectLabel', 'demo.redhat.com/tenant-uuid')

    if not enabled:
        return finding('ExternalName Service block (VAP)', True, 'not required')

    vap = get_custom(custom_api, 'admissionregistration.k8s.io', 'v1', 'deny-externalname-services')
    if vap is None:
        return finding('ExternalName Service block (VAP)', False, 'missing')

    expressions = (vap.get('spec', {})
                   .get('matchConstraints', {})
                   .get('namespaceSelector', {})
                   .get('matchExpressions', []))
    live_label = expressions[0].get('key', '') if expressions else ''
    ok = live_label == want_label
    detail = 'deny-externalname-services, label %s' % live_label
    if not ok:
        detail += ' — expected %s' % want_label
    return finding('ExternalName Service block (VAP)', ok, detail)


def check_registries(custom_api, desired):
    image = get_custom(custom_api, 'config.openshift.io', 'v1', 'cluster')
    if image is None:
        return finding('Allowed container registries', False, 'image config missing')

    sources = image.get('spec', {}).get('registrySources', {})
    live = sorted(sources.get('allowedRegistries', []))
    blocked = sources.get('blockedRegistries', [])
    want = sorted(desired.get('allowedRegistries', []))
    registries_set = 'allowedRegistries' in desired

    if blocked:
        return finding('Allowed container registries', False, 'blockedRegistries is not empty')

    if registries_set:
        missing = set(want) - set(live)
        extra = set(live) - set(want)
        if missing or extra:
            parts = []
            if missing:
                parts.append('missing: ' + ', '.join(sorted(missing)))
            if extra:
                parts.append('unexpected: ' + ', '.join(sorted(extra)))
            return finding('Allowed container registries', False, ' | '.join(parts))

    return finding('Allowed container registries', True,
                   '%d allowed, all match' % len(live))


def check_self_provisioner(rbac_api, desired):
    sp_config = desired.get('selfProvisioner', {})
    enabled = sp_config.get('enabled', False)

    try:
        binding = rbac_api.read_cluster_role_binding('self-provisioners')
    except ApiException as e:
        if e.status == 404:
            return finding('Self-provisioner (oc new-project)', False, 'binding missing')
        raise

    annotations = binding.metadata.annotations or {}
    autoupdate = annotations.get('rbac.authorization.kubernetes.io/autoupdate', '')
    groups = [s.name for s in (binding.subjects or [])]

    issues = []
    if autoupdate != 'false':
        issues.append('autoupdate not false')
    if enabled:
        if 'system:authenticated' not in groups or 'system:authenticated:oauth' not in groups:
            issues.append('groups missing')
    else:
        if 'system:authenticated' in groups or 'system:authenticated:oauth' in groups:
            issues.append('groups still present')

    state = 'enabled' if enabled else 'disabled'
    ok = len(issues) == 0
    detail = '%s, autoupdate %s' % (state, autoupdate or 'missing')
    if not ok:
        detail += ' — ' + ', '.join(issues)
    return finding('Self-provisioner (oc new-project)', ok, detail)


# ---------- tenant-level: quota ----------

def check_quota_mode(params):
    ok = params['use_cluster_quota']
    detail = 'shared pool (ClusterResourceQuota)' if ok else 'per-namespace quota'
    return finding('Cluster resource quota mode', ok, detail)


def check_crq(custom_api, user):
    crq = get_custom(custom_api, 'quota.openshift.io', 'v1', 'tenant-' + user)
    if crq is None:
        return None, finding('Resource quota for %s' % user, False, 'missing')

    selector = (crq.get('spec', {})
                .get('selector', {})
                .get('annotations', {})
                .get('openshift.io/requester', ''))
    ok = selector == user
    return crq, finding(
        'Resource quota for %s' % user, ok,
        'requester %s' % (selector or 'missing')
    )


def check_quota_limits(crq, expected_quota, quota_is_complete):
    if crq is None:
        return finding('Quota limits', False, 'quota not found')

    live = crq.get('spec', {}).get('quota', {}).get('hard', {})
    mismatches = []
    for key, want_val in expected_quota.items():
        live_val = live.get(key, 'missing')
        if str(live_val) != str(want_val):
            mismatches.append('%s: expected %s, live %s' % (key, want_val, live_val))

    if quota_is_complete:
        for key, live_val in live.items():
            if key not in expected_quota:
                mismatches.append('%s: live %s, not part of the merged quota' % (key, live_val))

    ok = len(mismatches) == 0
    detail = 'all limits match' if ok else '; '.join(mismatches)
    return finding('Quota limits', ok, detail)


def check_limit_range(core_api, ns_spec, quota_is_complete):
    ns_name = ns_spec['name']
    want_lr = ns_spec.get('limit_range', {})

    try:
        lr = core_api.read_namespaced_limit_range('tenant-limit-range', ns_name)
    except ApiException as e:
        if e.status == 404:
            return finding('Container defaults for %s' % ns_name, False, 'missing')
        raise

    container_limit = {}
    for item in (lr.spec.limits or []):
        if item.type == 'Container':
            container_limit = {
                'default': item.default or {},
                'defaultRequest': item.default_request or {},
            }
            break

    mismatches = []
    for section in ('default', 'defaultRequest'):
        want_section = want_lr.get(section, {})
        live_section = container_limit.get(section, {})
        for key, want_val in want_section.items():
            live_val = live_section.get(key, 'missing')
            if str(live_val) != str(want_val):
                mismatches.append('%s.%s expected %s live %s' % (section, key, want_val, live_val))
        # Flag unexpected keys when we have the complete merged LimitRange
        if quota_is_complete:
            for key, live_val in live_section.items():
                if key not in want_section:
                    mismatches.append('%s.%s live %s, not part of the merged LimitRange' % (section, key, live_val))

    ok = len(mismatches) == 0
    detail = 'all defaults match' if ok else '; '.join(mismatches)
    return finding('Container defaults for %s' % ns_name, ok, detail)


# ---------- tenant-level: network ----------

def check_anp(custom_api, uuid, expected_namespace_allows):
    anp_name = 'tenant-' + uuid.lower()
    anp = get_custom(custom_api, 'policy.networking.k8s.io', 'v1alpha1', anp_name)

    if anp is None:
        return finding('Tenant network policy', False,
                       'missing — AdminNetworkPolicy %s not found' % anp_name)

    spec = anp.get('spec', {})
    subject_uuid = (spec.get('subject', {})
                    .get('namespaces', {})
                    .get('matchLabels', {})
                    .get('demo.redhat.com/tenant-uuid', ''))

    # Build rule name -> action maps
    ingress = {r['name']: r['action'] for r in spec.get('ingress', [])}
    egress = {r['name']: r['action'] for r in spec.get('egress', [])}
    egress_names = [r['name'] for r in spec.get('egress', [])]

    # Verify own-namespace rules reference the correct UUID
    def check_uuid_in_rules(rules, rule_name, path_key):
        for r in rules:
            if r.get('name') == rule_name:
                peers = r.get(path_key, [])
                for peer in peers:
                    labels = peer.get('namespaces', {}).get('matchLabels', {})
                    if labels.get('demo.redhat.com/tenant-uuid') == uuid:
                        return True
        return False

    # Verify deny rules use matchExpressions with Exists operator
    def check_deny_expression(rules, rule_name, path_key):
        for r in rules:
            if r.get('name') == rule_name:
                peers = r.get(path_key, [])
                for peer in peers:
                    expressions = peer.get('namespaces', {}).get('matchExpressions', [])
                    for expr in expressions:
                        if (expr.get('key') == 'demo.redhat.com/tenant-uuid'
                                and expr.get('operator') == 'Exists'):
                            return True
        return False

    want_ns_allows = ['allow-to-' + a for a in expected_namespace_allows]
    missing_ns_allows = set(want_ns_allows) - set(egress_names)

    # Collect all issues
    issues = []
    if subject_uuid != uuid:
        issues.append('subject uuid mismatch')

    # Required ingress rules
    for name, action in [('allow-from-own-namespaces', 'Allow'),
                         ('allow-from-ingress', 'Allow'),
                         ('deny-from-other-tenants', 'Deny')]:
        if ingress.get(name) != action:
            issues.append('missing %s' % name)

    # Required egress rules
    for name, action in [('allow-to-own-namespaces', 'Allow'),
                         ('deny-to-other-tenants', 'Deny'),
                         ('allow-dns', 'Allow'),
                         ('allow-api', 'Allow'),
                         ('allow-ingress-routes', 'Allow'),
                         ('allow-image-registry', 'Allow'),
                         ('allow-kubernetes-api-svc', 'Allow')]:
        if egress.get(name) != action:
            issues.append('missing %s' % name)

    if missing_ns_allows:
        issues.append('missing namespace allows: %s' % ', '.join(sorted(missing_ns_allows)))

    if not check_uuid_in_rules(spec.get('ingress', []), 'allow-from-own-namespaces', 'from'):
        issues.append('own-namespace ingress uuid mismatch')
    if not check_uuid_in_rules(spec.get('egress', []), 'allow-to-own-namespaces', 'to'):
        issues.append('own-namespace egress uuid mismatch')
    if not check_deny_expression(spec.get('ingress', []), 'deny-from-other-tenants', 'from'):
        issues.append('deny ingress missing Exists expression')
    if not check_deny_expression(spec.get('egress', []), 'deny-to-other-tenants', 'to'):
        issues.append('deny egress missing Exists expression')

    ok = len(issues) == 0
    detail = anp_name if ok else '%s — %s' % (anp_name, ', '.join(issues))
    return finding('Tenant network policy', ok, detail)


def check_egress_firewalls(custom_api, core_api, uuid, expected_domains, expected_cidrs):
    # Discover all namespaces with the tenant label, then read EgressFirewall
    # in each. Split into tenant vs showroom namespaces by the creator label
    # so each type gets its own check with the right expected domains.
    results = []

    try:
        ns_list = core_api.list_namespace(label_selector='demo.redhat.com/tenant-uuid=%s' % uuid)
    except ApiException:
        return [finding('Tenant egress firewall', False, 'could not list namespaces')]

    namespaces = ns_list.items or []
    if not namespaces:
        return [finding('Tenant egress firewall', False, 'no namespaces with tenant label found')]

    tenant_ns = []
    showroom_ns = []
    for ns in namespaces:
        labels = ns.metadata.labels or {}
        if labels.get('creator') == 'agnosticd.showroom.ocp4_workload_showroom':
            showroom_ns.append(ns)
        else:
            tenant_ns.append(ns)

    def validate_ef(ns_name, want_domains, want_cidrs):
        ef = get_custom(custom_api, 'k8s.ovn.org', 'v1', 'default', namespace=ns_name)
        if ef is None:
            return ['%s: missing' % ns_name]

        rules = ef.get('spec', {}).get('egress', [])
        allow_domains = [r['to']['dnsName'] for r in rules
                         if r.get('type') == 'Allow' and 'dnsName' in r.get('to', {})]
        allow_cidrs = [r['to']['cidrSelector'] for r in rules
                       if r.get('type') == 'Allow' and 'cidrSelector' in r.get('to', {})]
        deny_cidrs = [r['to']['cidrSelector'] for r in rules
                      if r.get('type') == 'Deny' and 'cidrSelector' in r.get('to', {})]

        issues = []
        if '0.0.0.0/0' not in deny_cidrs or '::/0' not in deny_cidrs:
            issues.append('%s: no deny-all' % ns_name)
        missing_domains = set(want_domains) - set(allow_domains)
        if missing_domains:
            issues.append('%s: missing domains %s' % (ns_name, ', '.join(sorted(missing_domains))))
        missing_cidrs = set(want_cidrs) - set(allow_cidrs)
        if missing_cidrs:
            issues.append('%s: missing CIDRs %s' % (ns_name, ', '.join(sorted(missing_cidrs))))
        return issues

    # Tenant namespaces: expect pypi domains (or whatever the CI configured)
    tenant_issues = []
    for ns in tenant_ns:
        tenant_issues.extend(validate_ef(ns.metadata.name, expected_domains, expected_cidrs))

    if tenant_ns:
        ok = len(tenant_issues) == 0
        detail = ('%d namespaces, deny-all + allowed domains verified' % len(tenant_ns)
                  if ok else '; '.join(tenant_issues))
        results.append(finding('Tenant egress firewall', ok, detail))

    # Showroom namespaces: expect github.com + objects.githubusercontent.com
    showroom_domains = ['github.com', 'objects.githubusercontent.com']
    showroom_issues = []
    for ns in showroom_ns:
        showroom_issues.extend(validate_ef(ns.metadata.name, showroom_domains, []))

    if showroom_ns:
        ok = len(showroom_issues) == 0
        detail = 'deny-all + github.com verified' if ok else '; '.join(showroom_issues)
        results.append(finding('Showroom egress firewall', ok, detail))

    return results


# ---------- tenant-level: access ----------

def check_unexpected_namespaces(all_namespaces, user, uuid, expected_names):
    unexpected = []
    for ns in all_namespaces:
        name = ns.metadata.name
        if name in expected_names:
            continue
        annotations = ns.metadata.annotations or {}
        labels = ns.metadata.labels or {}
        stamped = (annotations.get('openshift.io/requester') == user
                   or labels.get('demo.redhat.com/tenant-uuid') == uuid)
        if stamped:
            unexpected.append(name)

    ok = len(unexpected) == 0
    detail = 'none found' if ok else ', '.join(sorted(unexpected))
    return finding('Extra namespaces for this tenant', ok, detail)


def check_namespace_identity(all_namespaces, ns_spec, user, uuid):
    ns_name = ns_spec['name']
    ns = None
    for n in all_namespaces:
        if n.metadata.name == ns_name:
            ns = n
            break

    if ns is None:
        return finding('Namespace %s' % ns_name, False, 'missing')

    requester = (ns.metadata.annotations or {}).get('openshift.io/requester', '')
    uuid_label = (ns.metadata.labels or {}).get('demo.redhat.com/tenant-uuid', '')
    ok = requester == user and uuid_label == uuid
    detail = 'requester %s, tenant-uuid %s' % (requester or 'missing', uuid_label or 'missing')
    return finding('Namespace %s' % ns_name, ok, detail)


def check_showroom_namespace(all_namespaces, showroom_ns):
    found = any(n.metadata.name == showroom_ns for n in all_namespaces)
    return finding('Namespace %s' % showroom_ns, found, 'present' if found else 'missing')


def check_rolebinding(rbac_api, ns_name, user, role):
    binding_name = '%s-%s' % (role, user)
    try:
        binding = rbac_api.read_namespaced_role_binding(binding_name, ns_name)
    except ApiException as e:
        if e.status == 404:
            return finding('%s access in %s' % (user, ns_name), False, 'missing')
        raise

    role_name = binding.role_ref.name if binding.role_ref else ''
    subjects = [s.name for s in (binding.subjects or []) if s.kind == 'User']
    ok = role_name == role and user in subjects
    return finding('%s access in %s' % (user, ns_name), ok, 'role %s' % role_name)


def check_cluster_admin_escalation(rbac_api, user):
    try:
        bindings = rbac_api.list_cluster_role_binding()
    except ApiException:
        return finding('Cluster-admin escalation for %s' % user, False, 'could not list bindings')

    admin_bindings = []
    for b in (bindings.items or []):
        if not b.role_ref or b.role_ref.name != 'cluster-admin':
            continue
        for s in (b.subjects or []):
            if s.kind == 'User' and s.name == user:
                admin_bindings.append(b.metadata.name)
                break

    ok = len(admin_bindings) == 0
    detail = 'none' if ok else ', '.join(admin_bindings)
    return finding('Cluster-admin escalation for %s' % user, ok, detail)


def check_token_leak(core_api, expected_names, admin_token):
    # Search every Secret in tenant namespaces for the cluster-admin token.
    # This catches accidental leaks that would let a student escalate.
    if not admin_token:
        return finding('Admin token leaked to tenant', False, 'token not available to compare')

    try:
        for ns_name in expected_names:
            secrets = core_api.list_namespaced_secret(ns_name)
            for secret in (secrets.items or []):
                if not secret.data:
                    continue
                for value in secret.data.values():
                    try:
                        decoded = base64.b64decode(value).decode('utf-8', errors='ignore')
                    except Exception:
                        continue
                    if admin_token in decoded:
                        return finding('Admin token leaked to tenant', False,
                                       '%s/%s' % (ns_name, secret.metadata.name))
    except ApiException:
        return finding('Admin token leaked to tenant', False, 'could not read a Secret')

    return finding('Admin token leaked to tenant', True, 'not found')


# ---------- orchestrator ----------

def run_module():
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    if not HAS_K8S:
        module.fail_json(msg='kubernetes python package is required')

    params = module.params
    api_client = make_client(params)
    custom_api = k8s_client.CustomObjectsApi(api_client)
    core_api = k8s_client.CoreV1Api(api_client)
    rbac_api = k8s_client.RbacAuthorizationV1Api(api_client)

    findings = []

    # --- cluster checks ---
    desired, argocd_finding = check_argocd(custom_api, params)
    if desired is None:
        module.fail_json(msg=argocd_finding['detail'])
    findings.append(argocd_finding)

    findings.append(check_vap(custom_api, desired))
    findings.append(check_registries(custom_api, desired))
    findings.append(check_self_provisioner(rbac_api, desired))

    # --- tenant checks ---
    if params['mode'] == 'tenant':
        user = params['tenant_user']
        uuid = params['tenant_uuid']
        role = params['tenant_role']
        ns_specs = params['namespace_specs']
        showroom_ns = params['showroom_namespace']

        expected_names = [s['name'] for s in ns_specs]
        if showroom_ns:
            expected_names.append(showroom_ns)

        # Quota
        findings.append(check_quota_mode(params))
        crq, crq_finding = check_crq(custom_api, user)
        findings.append(crq_finding)
        findings.append(check_quota_limits(crq, params['expected_quota'], params['quota_is_complete']))

        # LimitRange per namespace
        for spec in ns_specs:
            findings.append(check_limit_range(core_api, spec, params['quota_is_complete']))

        # Network
        findings.append(check_anp(custom_api, uuid, params['expected_namespace_allows']))

        if params['egress_firewall']:
            findings.extend(check_egress_firewalls(
                custom_api, core_api, uuid,
                params['expected_tenant_domains'],
                params['expected_tenant_cidrs'],
            ))

        # Namespaces and access
        all_ns = (core_api.list_namespace()).items or []
        findings.append(check_unexpected_namespaces(all_ns, user, uuid, expected_names))

        for spec in ns_specs:
            findings.append(check_namespace_identity(all_ns, spec, user, uuid))
        if showroom_ns:
            findings.append(check_showroom_namespace(all_ns, showroom_ns))

        for spec in ns_specs:
            findings.append(check_rolebinding(rbac_api, spec['name'], user, role))

        findings.append(check_cluster_admin_escalation(rbac_api, user))
        findings.append(check_token_leak(core_api, expected_names, params['admin_token']))

    user_data = findings_to_user_data(findings, params['mode'])

    module.exit_json(
        changed=False,
        findings=findings,
        user_data=user_data,
    )


if __name__ == '__main__':
    run_module()
