# Service mesh integration

This repo includes reference Istio resources under `k8s/istio/`:

* `PeerAuthentication` for **mTLS STRICT**
* `DestinationRule` for connection pooling and outlier detection
* `VirtualService` for timeouts and retries

These illustrate how an AI-native platform typically uses a mesh to:

* enforce encryption in transit
* apply consistent timeout/retry policies
* eject unhealthy pods automatically

If you use Linkerd, you can apply equivalent settings via Linkerd ServiceProfiles.
