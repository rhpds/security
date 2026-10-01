# Ansible Collection - rhpds.security

Security hardening roles for Red Hat Demo Platform (RHDP) OpenShift clusters.

## Roles

- [`ocp_workload_cluster_security_policy`](roles/ocp_workload_cluster_security_policy/README.md) — cluster workload. Points OpenShift GitOps at the [`cluster-security-policy`](cluster-security-policy) Helm chart for allowed registries and self-provisioner lockout.
- [`ocp_workload_security_validation`](roles/ocp_workload_security_validation/README.md) — validation workload. Checks cluster and tenant security objects. Runs last in the workload list. Does not create anything.

Network policy (AdminNetworkPolicy + EgressFirewall) is managed per-tenant by `ocp4_workload_tenant_namespace` in the `namespaced_workloads` collection.

## GitOps

- [`cluster-security-policy`](cluster-security-policy) — allowed registries and self-provisioner switch. Application `cluster-security-policy` points here.
