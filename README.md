# Ansible Collection - rhpds.security

Security hardening roles for Red Hat Demo Platform (RHDP) OpenShift tenants.

## Roles

- [`ocp_workload_cluster_security_policy`](roles/ocp_workload_cluster_security_policy/README.md) — cluster catalog item workload. Points OpenShift GitOps at [`cluster-security-policy`](cluster-security-policy).
- [`ocp_workload_cluster_security_validation`](roles/ocp_workload_cluster_security_validation/README.md) — last cluster workload. Reads Application `cluster-security-policy` and fails the provision if the live objects do not match its helm values. Does not repair them.
- [`ocp_workload_tenant_security_validation`](roles/ocp_workload_tenant_security_validation/README.md) — last tenant workload. Checks the cluster Application and the tenant objects. Fails the provision when a check fails. Does not create anything.
- [`openshift_tenant_lockdown`](roles/openshift_tenant_lockdown/README.md) — scaffold for Zero Touch tenant lockdown. Left unchanged. New tenant catalog items use `ocp_workload_tenant_security_validation`.

## GitOps

- [`cluster-security-policy`](cluster-security-policy) — cluster AdminNetworkPolicy and the self-provisioner switch. Application `cluster-security-policy` points here. This is not the content bootstrap Application named `bootstrap-infra`.
