# openshift_tenant_lockdown

Applies security lockdown policies to a Zero Touch OpenShift tenant namespace.

## Status

Scaffold only. Each policy area currently runs as a mocked `ansible.builtin.debug` task describing its intended purpose — no OpenShift objects are created yet. Real enforcement (NetworkPolicy/EgressFirewall objects, quota objects, etc.) is still being designed.

## Role Variables

| Variable | Default | Description |
|---|---|---|
| `zero_touch` | `false` | Gate controlling whether the lockdown block runs. Must be `true` for any tasks in this role to execute. |
| `guid` | *(none)* | Used by the security report task to identify the tenant. Reports `unknown` if not set. |

## Tasks

- `enforce_quota_policy` — per-tenant resource quota isolation
- `enforce_egress_policy` — default-deny egress with an allowlist
- `enforce_ingress_policy` — default-deny ingress except router/intra-namespace traffic
- `enforce_pod_networking_policy` — intra-namespace pod-to-pod network segmentation
- `output_security_report` — reports the applied policies for the tenant (guid, date)

## Example Playbook

```yaml
- hosts: localhost
  roles:
    - role: rhpds.security.openshift_tenant_lockdown
      vars:
        zero_touch: true
```
