# Deploying Tree-of-Thought Debugging Tool on GCP (Kubernetes)

This guide walks through building the app, pushing to Artifact Registry, and deploying on GKE with HTTPS at the edge and optional session affinity.

## Prerequisites

- **gcloud** CLI installed and logged in (`gcloud auth login`, `gcloud config set project PROJECT_ID`)
- **kubectl** installed
- **Docker** (or use Cloud Build)
- **GKE cluster** (or create one below)
- **MongoDB** (e.g. [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)) and its connection string
- **Domain** (optional; for TLS and a stable URL)

---

## 1. Set variables

```bash
export GCP_PROJECT_ID=tot-tool
export GCP_REGION=us-central1
export IMAGE_NAME=tot-debugging
export IMAGE_TAG=latest
export ARTIFACT_REGISTRY_REPO=your-repo   # e.g. tot-apps
```

---

## 2. Build and push the Docker image

### Option A: Local Docker + Artifact Registry

```bash
# Enable Artifact Registry API (if not already)
gcloud services enable artifactregistry.googleapis.com --project=$GCP_PROJECT_ID

# Create repo (one-time)
gcloud artifacts repositories create $ARTIFACT_REGISTRY_REPO \
  --repository-format=docker \
  --location=$GCP_REGION \
  --project=$GCP_PROJECT_ID

# Configure Docker for Artifact Registry
gcloud auth configure-docker ${GCP_REGION}-docker.pkg.dev --quiet

# Build (from project root). Use linux/amd64 so the image runs on GKE (x86_64 nodes).
# Required if you build on Apple Silicon (ARM) to avoid "exec format error" in the pod.
docker build --platform linux/amd64 -t ${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${IMAGE_NAME}:${IMAGE_TAG} .

# Push
docker push ${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${IMAGE_NAME}:${IMAGE_TAG}
```

### Option B: Cloud Build (recommended on Apple Silicon; avoids EPIPE / exec format issues)

Builds run natively on amd64 in GCP, so no platform emulation and no "exec format error" or "write EPIPE" during the frontend build:

```bash
# From project root
gcloud builds submit --tag ${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${IMAGE_NAME}:${IMAGE_TAG} .
```

---

## 3. Create or use a GKE cluster

```bash
# Create cluster (one-time)
# Use pd-standard to avoid SSD_TOTAL_GB quota (default pool may use SSD otherwise)
gcloud container clusters create tot-debugging-cluster \
  --project=$GCP_PROJECT_ID \
  --region=$GCP_REGION \
  --num-nodes=1 \
  --machine-type=e2-medium \
  --disk-type=pd-standard \
  --disk-size=30 \
  --enable-autorepair \
  --enable-autoupgrade

# Get credentials
gcloud container clusters get-credentials tot-debugging-cluster \
  --region=$GCP_REGION \
  --project=$GCP_PROJECT_ID
```

---

## 4. Create Kubernetes Secret

Export your real values (replace placeholders), then create the namespace and secret. Do **not** commit these values.

```bash
# Export your actual values (replace with real secrets)
export JWT_SECRET="your-jwt-secret-at-least-32-characters"
export OPENAI_API_KEY="sk-your-openai-key"
export GROQ_API_KEY="gsk_your-groq-api-key"
export MONGODB_URI="your-mongo-uri"

# Create namespace
kubectl create namespace tot-debugging --dry-run=client -o yaml | kubectl apply -f -

# Create app secret (JWT, API keys, MongoDB)
kubectl create secret generic tot-debugging-secret \
  --namespace=tot-debugging \
  --from-literal=JWT_SECRET="$JWT_SECRET" \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
  --from-literal=GROQ_API_KEY="$GROQ_API_KEY" \
  --from-literal=MONGODB_URI="$MONGODB_URI" \
  --dry-run=client -o yaml | kubectl apply -f -
```

If you prefer a YAML secret file: copy `k8s/secret.yaml.example` to `k8s/secret.yaml`, fill in the `data` fields (base64: `echo -n "value" | base64`), then run:

```bash
kubectl apply -f k8s/secret.yaml
```

---

## 5. Apply Deployment, Service, and base manifests

Ensure variables from **Section 1** are set, then run:

```bash
export IMAGE=${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${IMAGE_NAME}:${IMAGE_TAG}

kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
sed -e "s|REGISTRY_IMAGE_PLACEHOLDER|${IMAGE}|g" k8s/deployment.yaml | kubectl apply -f -
kubectl apply -f k8s/service.yaml
```

Verify pods are running:

```bash
kubectl get pods,svc -n tot-debugging
```

### 5.1 Debugging CrashLoopBackOff

If the pod is in `CrashLoopBackOff`, run these in order to see why it's exiting:

**1. Pod status and recent events**

```bash
kubectl get pods -n tot-debugging
kubectl describe pod -n tot-debugging -l app=tot-debugging
```

Check the **Events** at the bottom (image pull errors, failed probes, OOMKilled, etc.).

**2. Application logs (current and previous run)**

```bash
# Logs from the current container run
kubectl logs -n tot-debugging -l app=tot-debugging --tail=200

# If the container restarted, logs from the previous run (often has the crash reason)
kubectl logs -n tot-debugging -l app=tot-debugging --previous --tail=200
```

**3. Common causes and fixes**

| Symptom / Log | Likely cause | Fix |
|---------------|--------------|-----|
| `MONGODB_URI` / connection error | Secret missing or wrong | Recreate secret (Section 4); ensure key is `MONGODB_URI`. |
| `JWT_SECRET` not set / auth error | Secret missing or wrong | Recreate secret with `JWT_SECRET`. |
| `ImagePullBackOff` / `ErrImagePull` | Wrong image name or no pull access | Check `IMAGE` and that Artifact Registry allows cluster's GCP SA; `gcloud auth configure-docker`. |
| Exit code 137 / OOMKilled | Not enough memory | Increase `resources.limits.memory` in `k8s/deployment.yaml` or use a larger node. |
| Liveness/readiness probe failing | App not listening on 5000 or slow startup | Increase `initialDelaySeconds` for probes in `k8s/deployment.yaml`; confirm app binds to `0.0.0.0:5000`. |
| `exec format error` (gunicorn) | Image built for wrong CPU (e.g. ARM on Mac, cluster is amd64) | Rebuild with `docker build --platform linux/amd64 ...` (Section 2); or use Cloud Build. |
| Python traceback / module error | App crash on import or startup | Fix code or dependencies; run the image locally: `docker run --env-file .env <image>`. |

**4. Test the same image locally (optional)**

If the app works locally but not in the cluster, the issue is likely env or networking. Run the deployed image with the same env:

```bash
export IMAGE=${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${IMAGE_NAME}:${IMAGE_TAG}
docker run --rm -p 5000:5000 \
  -e JWT_SECRET="$JWT_SECRET" \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e GROQ_API_KEY="$GROQ_API_KEY" \
  -e MONGODB_URI="$MONGODB_URI" \
  -e MONGODB_DATABASE_NAME=tot_debugging \
  -e FLASK_ENV=production \
  $IMAGE
```

If this crashes too, the fix is in the app or env; if it runs, focus on Secret/ConfigMap and probes in the cluster.

**5. Confirm Secret and ConfigMap exist**

```bash
kubectl get secret tot-debugging-secret -n tot-debugging -o yaml
kubectl get configmap tot-debugging-config -n tot-debugging -o yaml
```

Ensure the secret has `JWT_SECRET`, `OPENAI_API_KEY`, `GROQ_API_KEY`, and `MONGODB_URI` (or the keys your app expects).

---

## 6. Create TLS certificates and expose with NGINX Ingress (HTTPS at edge, HTTP to pods)

### 6.1 Install NGINX Ingress Controller (one-time per cluster)

```bash
# Helm (if you use Helm)
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace

# Or: kubectl (no Helm)
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/cloud/deploy.yaml
```

Wait for the Ingress controller to have an EXTERNAL-IP:

```bash
kubectl get svc -n ingress-nginx
```

### 6.2 Create TLS certificates

**Option A – Self-signed cert (dev / testing)**

Replace `tot-debugging.example.com` with your hostname (or leave as-is for testing).

```bash
mkdir -p certs && cd certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout tls.key \
  -out tls.crt \
  -subj "/CN=tot-debugging.example.com/O=ToT Debugging"
cd ..
```

Create the TLS secret in Kubernetes:

```bash
kubectl create secret tls tot-debugging-tls \
  --namespace=tot-debugging \
  --cert=certs/tls.crt \
  --key=certs/tls.key
```

**Option B – Let's Encrypt with cert-manager (production)**

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
kubectl wait --for=condition=Available deployment --all -n cert-manager --timeout=120s
```

Create a ClusterIssuer (replace email):

```bash
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: nginx
EOF
```

Then in **6.4** use the cert-manager annotation and skip creating the TLS secret manually; cert-manager will create `tot-debugging-tls`.

### 6.3 Set your domain and (for self-signed) ensure TLS secret exists

```bash
# Replace with your real hostname
export INGRESS_HOST=tot-debugging.example.com
```

If you used **Option A** (self-signed), the TLS secret was already created in 6.2. If you use **Option B** (cert-manager), you will reference the ClusterIssuer in the Ingress in 6.4.

### 6.4 Update Ingress host and apply Ingress

Edit `k8s/ingress.yaml`: replace `tot-debugging.example.com` with `$INGRESS_HOST` (e.g. `tot-debugging.yourdomain.com`). If using cert-manager, add to the Ingress metadata annotations: `cert-manager.io/cluster-issuer: letsencrypt-prod` and keep `secretName: tot-debugging-tls` (cert-manager will create that secret).

Then apply the Ingress:

```bash
kubectl apply -f k8s/ingress.yaml
```

Get the Ingress external address:

```bash
kubectl get ingress -n tot-debugging
```

Point your domain's DNS A record to the Ingress ADDRESS (or use the ADDRESS with `/etc/hosts` for testing).

### 6.5 Quick test without TLS (optional)

To expose the app quickly over HTTP (no HTTPS):

```bash
kubectl patch service tot-debugging -n tot-debugging -p '{"spec":{"type":"LoadBalancer"}}'
kubectl get svc -n tot-debugging
# Open http://<EXTERNAL-IP>
```

### 6.6 Expose by IP only (no domain)

Use this when you don't have a domain: users open **https://&lt;INGRESS_IP&gt;** in the browser. You need a TLS cert that includes the Ingress controller's IP in its Subject Alternative Name (SAN).

**1. Get the NGINX Ingress controller external IP**

```bash
kubectl get svc -n ingress-nginx
```

Use the **EXTERNAL-IP** of `ingress-nginx-controller` (e.g. `34.120.45.67`). Set it:

```bash
export INGRESS_IP=34.120.45.67   # Replace with your actual IP
```

**2. Generate a self-signed cert with the IP in SAN**

Browsers require the IP in the cert's Subject Alternative Name for **https://&lt;IP&gt;**:

```bash
mkdir -p certs && cd certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout tls.key -out tls.crt \
  -subj "/CN=$INGRESS_IP" \
  -addext "subjectAltName=IP:$INGRESS_IP"
cd ..
```

**3. Create or replace the TLS secret**

```bash
kubectl delete secret tot-debugging-tls -n tot-debugging --ignore-not-found
kubectl create secret tls tot-debugging-tls -n tot-debugging --cert=certs/tls.crt --key=certs/tls.key
```

**4. Apply the IP-only Ingress**

Replace the placeholder in the manifest with your IP, then apply:

```bash
sed -e "s/YOUR_INGRESS_IP/$INGRESS_IP/g" k8s/ingress-ip-only.yaml | kubectl apply -f -
```

**5. Open the app**

In the browser go to:

```
https://<INGRESS_IP>
```

(e.g. `https://34.120.45.67`). Accept the self-signed certificate warning (e.g. "Advanced" → "Proceed to …").

**Note:** If the Ingress controller's external IP ever changes (e.g. after recreate), repeat from step 1 with the new IP (new cert and update `k8s/ingress-ip-only.yaml` / TLS secret).

---

### Exact commands summary (Section 4 onwards, in order)

Run these after **Section 1** variables and **Section 3** (cluster + get-credentials). Replace placeholder values with your real secrets and hostname.

```bash
# --- 4. Secret (export real values first) ---
export JWT_SECRET="your-jwt-secret-at-least-32-characters"
export OPENAI_API_KEY="sk-your-openai-key"
export GROQ_API_KEY="gsk_your-groq-api-key"
export MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net/tot_debugging"

kubectl create namespace tot-debugging --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic tot-debugging-secret -n tot-debugging \
  --from-literal=JWT_SECRET="$JWT_SECRET" \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
  --from-literal=GROQ_API_KEY="$GROQ_API_KEY" \
  --from-literal=MONGODB_URI="$MONGODB_URI" \
  --dry-run=client -o yaml | kubectl apply -f -

# --- 5. Deployment, Service ---
export IMAGE=${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${IMAGE_NAME}:${IMAGE_TAG}
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
sed -e "s|REGISTRY_IMAGE_PLACEHOLDER|${IMAGE}|g" k8s/deployment.yaml | kubectl apply -f -
kubectl apply -f k8s/service.yaml
kubectl get pods,svc -n tot-debugging

# --- 6. TLS (self-signed) + Ingress ---
mkdir -p certs && cd certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout tls.key -out tls.crt -subj "/CN=tot-debugging.example.com/O=ToT Debugging"
cd ..
kubectl create secret tls tot-debugging-tls -n tot-debugging --cert=certs/tls.crt --key=certs/tls.key
# Edit k8s/ingress.yaml: set host to your domain, then:
kubectl apply -f k8s/ingress.yaml
kubectl get ingress -n tot-debugging
```

---

## 7. Session affinity (pin session to one pod)

- The app sends **`X-Session-ID`** on API requests when a session is active.
- **NGINX Ingress:** The provided `k8s/ingress.yaml` uses:
  - `nginx.ingress.kubernetes.io/upstream-hash-by: "$http_x_session_id"` so the same session id goes to the same backend.
  - Cookie affinity as a fallback.
- **GKE Ingress (GCE):** Configure [session affinity](https://cloud.google.com/kubernetes-engine/docs/how-to/ingress-features#session_affinity) on the backend service (e.g. generated by the Ingress) so that once a user hits a pod, subsequent requests go to the same pod.

With **1 replica** (default in `k8s/deployment.yaml`), all traffic goes to one pod; affinity matters when you scale to multiple replicas.

---

## 8. Verify

```bash
kubectl get pods,svc,ingress -n tot-debugging
kubectl logs -n tot-debugging -l app=tot-debugging -f
```

Open the app URL (LoadBalancer EXTERNAL-IP or Ingress host). You should see the login screen; sign in and create a board to confirm API and MongoDB work.

---

## 9. Scaling and in-memory engines

- **Single replica:** All sessions run on one pod; no cross-pod issues.
- **Multiple replicas:** In-memory engines are per-pod. Use session affinity (above) so that requests for a given session go to the same pod. The frontend sends `X-Session-ID`; configure your Ingress/LB to use it for stickiness.

---

## 10. Cleanup

```bash
kubectl delete namespace tot-debugging
# Optionally delete cluster:
# gcloud container clusters delete tot-debugging-cluster --region=$GCP_REGION --project=$GCP_PROJECT_ID --quiet
```

---

## 11. Redeploy after code changes

When you change app or frontend code, rebuild the image, push it, and restart the deployment so the cluster runs the new image. You do **not** need to re-create Secrets, ConfigMap, or Ingress unless you changed those.

**1. Set variables (same as Section 1)**

```bash
export GCP_PROJECT_ID=tot-tool
export GCP_REGION=us-central1
export IMAGE_NAME=tot-debugging
export IMAGE_TAG=latest
export ARTIFACT_REGISTRY_REPO=your-repo
```

**2. Build the Docker image**

From the project root. Use the same image URL as in your initial deploy.

**Option A – Local Docker (use linux/amd64 if building on Apple Silicon)**

```bash
docker build --platform linux/amd64 -t ${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${IMAGE_NAME}:${IMAGE_TAG} .
```

**Option B – Cloud Build**

```bash
gcloud builds submit --tag ${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${IMAGE_NAME}:${IMAGE_TAG} .
```

**3. Push the image**

```bash
docker push ${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${IMAGE_NAME}:${IMAGE_TAG}
```

(Skip this step if you used Cloud Build; it already pushed.)

**4. Restart the deployment so the cluster pulls the new image**

```bash
kubectl rollout restart deployment/tot-debugging -n tot-debugging
```

**5. (Optional) Watch the rollout**

```bash
kubectl rollout status deployment/tot-debugging -n tot-debugging
# or
kubectl get pods -n tot-debugging -w
```

When new pods are **Running** and old ones are gone, the new code is live. Open your app URL to confirm.
