# cluster-security-policy

Cluster chart for an RHDP tenant host. One Argo CD Application points here. A namespace admin cannot delete either object.

- `AdminNetworkPolicy` `tenant-egress`, priority 50. Subject is namespaces with `openshift.io/requester`. Allows DNS, the API on control-plane nodes port 6443, and ingress from the router. Denies `0.0.0.0/0` and `::/0`. There is no Pass of all in-cluster traffic, so anything not named above falls through to the deny.
- `ClusterRoleBinding` `self-provisioner`. Default removes `system:authenticated` and `system:authenticated:oauth` and sets `rbac.authorization.kubernetes.io/autoupdate=false`. Set `selfProvisioner.enabled: true` to put those groups back.

`extraEgressCIDRs` adds one Allow before the deny. Leave it empty unless image pull or another cluster-wide destination has to leave the cluster. The list is CIDRs, not hostnames.

Per-tenant isolation is not in this chart. The tenant namespace role creates that AdminNetworkPolicy.
