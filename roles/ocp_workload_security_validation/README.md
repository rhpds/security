# ocp_workload_security_validation

Last workload on a cluster or tenant catalog item. It does not install anything and it does not repair anything. Set `ocp_workload_security_validation_mode` to `cluster` (default) or `tenant`.

## How it works

`ocp_workload_cluster_security_policy` writes the desired policy into Application `cluster-security-policy` and trusts Argo CD once that Application is Healthy and Synced. This role runs after the other workloads, reads the Application helm values, and compares the live objects to those values. The helm values are the source of truth. This role does not keep its own copy of the registry list, the namespace allows, or the priorities.

## Cluster mode (default)

Checks:

- Application `cluster-security-policy` is Healthy and Synced
- AdminNetworkPolicy named by the Application matches those helm values
- `image.config.openshift.io/cluster` `allowedRegistries` matches the Application, and `blockedRegistries` is empty
- ClusterRoleBinding `self-provisioner` matches `selfProvisioner.enabled` from the Application

## Tenant mode

Runs all the cluster checks above, then adds:

- `use_cluster_quota` is true, and ClusterResourceQuota `tenant-<user>` selects `openshift.io/requester` and matches the merged quota
- LimitRange `tenant-limit-range` exists in each tenant namespace and matches the merged LimitRange
- AdminNetworkPolicy `tenant-isolation-<uuid>` allows that tenant's own namespaces, denies other requester namespaces, and is checked before the cluster policy
- Each tenant namespace exists and is stamped with the requester and `demo.redhat.com/tenant-uuid`
- The Showroom namespace exists when `ocp4_workload_showroom_namespace` is set
- No other namespace is stamped for this tenant
- The user has the namespace RoleBinding and no cluster-admin ClusterRoleBinding
- No Secret in those namespaces contains the cluster-admin token

Tenant checks use what `ocp4_workload_tenant_namespace` already merged in this job (the builtin quota and LimitRange). If that merge is not in scope, the check falls back to the catalog overlay only.

## Report

The report is written with `agnosticd.core.agnosticd_user_info`. Data keys are `cluster_security_report` / `cluster_security_report_status` in cluster mode, `tenant_security_report` / `tenant_security_report_status` in tenant mode. Any failed check fails the provision.

On destroy it does nothing. The cluster security policy role or the tenant namespace role removes the objects.

## Catalog item examples

Cluster:

```yaml
workloads:
  - agnosticd.core_workloads.ocp4_workload_openshift_gitops
  - rhpds.security.ocp_workload_cluster_security_policy
  - agnosticd.core_workloads.ocp4_workload_gitops_bootstrap
  - rhpds.security.ocp_workload_security_validation
```

Tenant:

```yaml
workloads:
  - agnosticd.namespaced_workloads.ocp4_workload_tenant_namespace
  - rhpds.security.ocp_workload_security_validation

ocp_workload_security_validation_mode: tenant
```

`ocp_workload_cluster_security_policy` has to have run on the cluster before a tenant is provisioned.
