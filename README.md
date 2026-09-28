# Ansible Collection - rhpds.security

Security hardening roles for Red Hat Demo Platform (RHDP) OpenShift tenants.

## Roles

- [`ocp_workload_cluster_security_policy`](roles/ocp_workload_cluster_security_policy/README.md) — cluster catalog item workload. Points OpenShift GitOps at [`cluster-security-policy`](cluster-security-policy).
- [`ocp_workload_cluster_security_validation`](roles/ocp_workload_cluster_security_validation/README.md) — last cluster workload. Reads the AdminNetworkPolicy and the self-provisioner binding. Fails the provision if they are missing or were changed. Does not repair them.
- [`openshift_tenant_lockdown`](roles/openshift_tenant_lockdown/README.md) — applies Zero Touch tenant lockdown policies (quota, egress, ingress, pod networking) to a per-tenant OpenShift namespace.

## GitOps

- [`cluster-security-policy`](cluster-security-policy) — cluster AdminNetworkPolicy and the self-provisioner switch. Application `cluster-security-policy` points here. This is not the content bootstrap Application named `bootstrap-infra`.
