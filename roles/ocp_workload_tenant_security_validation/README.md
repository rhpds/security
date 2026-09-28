# ocp_workload_tenant_security_validation

Last workload on a tenant catalog item. It does not create anything and it does not repair anything. `ocp4_workload_tenant_namespace` creates the namespaces, the ClusterResourceQuota, the LimitRange, the per-tenant AdminNetworkPolicy, and the user's RoleBinding. This role runs after that and reads them.

This role reads Application `cluster-security-policy` in `openshift-gitops` itself and compares the live cluster objects to that Application's helm values. It does not call the cluster validation role. Change the policy on the cluster catalog item. The Application is the source of truth.

Tenant checks use what `ocp4_workload_tenant_namespace` already merged in this job. That includes the builtin quota and LimitRange. This role does not copy those tables. If that merge is not in scope, the check falls back to the catalog overlay only.

- `use_cluster_quota` is true, and ClusterResourceQuota `tenant-<user>` selects `openshift.io/requester` and matches the merged quota
- LimitRange `tenant-limit-range` exists in each tenant namespace and matches the merged LimitRange
- AdminNetworkPolicy `tenant-isolation-<uuid>` allows that tenant's own namespaces, denies other requester namespaces, and is checked before the cluster policy. A missing policy fails the provision.
- each tenant namespace exists and is stamped with the requester and `demo.redhat.com/tenant-uuid`
- the Showroom namespace exists when `ocp4_workload_showroom_namespace` is set
- no other namespace is stamped for this tenant
- the user has the namespace RoleBinding and no cluster-admin ClusterRoleBinding
- no Secret in those namespaces contains the cluster-admin token

The report is written with `agnosticd.core.agnosticd_user_info` as `msg` and as `tenant_security_report` / `tenant_security_report_status` in `data`. The catalog info page shows those keys. Any failed check fails the provision, and the seat is not released.

On destroy it does nothing. The tenant namespace role removes the objects.

## Catalog item

```yaml
workloads:
  - agnosticd.namespaced_workloads.ocp4_workload_tenant_namespace
  - rhpds.security.ocp_workload_tenant_security_validation
```

`ocp_workload_cluster_security_policy` has to have run on the cluster before this tenant is provisioned.
