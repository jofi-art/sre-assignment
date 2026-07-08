# City Population API

A containerized REST API that manages city population data, built with Python/FastAPI, backed by Elasticsearch, and deployable on Kubernetes via Helm charts.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Development Setup](#local-development-setup)
- [Building the Container Image](#building-the-container-image)
- [Kubernetes Deployment](#kubernetes-deployment)
- [API Usage](#api-usage)
- [Running Tests](#running-tests)
- [Reflection](#reflection)

## Prerequisites

- Python 3.12+
- Docker
- A Kubernetes cluster (e.g., minikube, kind, Docker Desktop with K8s enabled)
- Helm 3
- `curl` (for API testing)

## Local Development Setup

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Start Elasticsearch

Start a local Elasticsearch instance using Docker:

```bash
docker run -d \
  --name elasticsearch \
  -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  elasticsearch:8.12.0
```

Wait a few seconds for Elasticsearch to become ready:

```bash
curl -s http://localhost:9200/_cluster/health | python -m json.tool
```

### 3. Set environment variables

```bash
export ELASTICSEARCH_HOST=localhost
export ELASTICSEARCH_PORT=9200
```

On Windows (PowerShell):

```powershell
$env:ELASTICSEARCH_HOST = "localhost"
$env:ELASTICSEARCH_PORT = "9200"
```

### 4. Run the application

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 5. Verify

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "ok"}
```

## Building the Container Image

```bash
docker build -t city-population-api:latest .
```

Run the container locally (assuming Elasticsearch is accessible at the host):

```bash
docker run -d \
  --name city-api \
  -p 8000:8000 \
  -e ELASTICSEARCH_HOST=host.docker.internal \
  -e ELASTICSEARCH_PORT=9200 \
  city-population-api:latest
```

## Kubernetes Deployment

### 1. Update Helm dependencies

```bash
helm dependency update helm/city-population-api
```

### 2. Deploy with Helm

```bash
helm install city-population helm/city-population-api
```

This deploys both the API service and an Elasticsearch instance via the Bitnami subchart.

### 3. Verify the deployment

Wait for pods to become ready:

```bash
kubectl get pods -l app.kubernetes.io/name=city-population-api --watch
```

Once running, port-forward to test the health endpoint:

```bash
kubectl port-forward svc/city-population-city-population-api 8000:8000
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "ok"}
```

## API Usage

### Health Check

**GET /health**

Check service availability:

```bash
curl -s http://localhost:8000/health
```

Successful response (200):

```json
{"status": "ok"}
```

Error response when Elasticsearch is unavailable (503):

```json
{"status": "unavailable", "detail": "Database unreachable"}
```

### Upsert City Population

**PUT /city/{city_name}**

Create or update a city's population:

```bash
curl -s -X PUT http://localhost:8000/city/London \
  -H "Content-Type: application/json" \
  -d '{"population": 9000000}'
```

Successful response for a new city (201):

```json
{"city": "London", "population": 9000000}
```

Successful response for an update (200):

```json
{"city": "London", "population": 9100000}
```

Error response for invalid population (422):

```bash
curl -s -X PUT http://localhost:8000/city/London \
  -H "Content-Type: application/json" \
  -d '{"population": -1}'
```

```json
{"detail": "population: Input should be greater than or equal to 0"}
```

Error response for invalid city name (422):

```bash
curl -s -X PUT http://localhost:8000/city/%20 \
  -H "Content-Type: application/json" \
  -d '{"population": 500000}'
```

```json
{"detail": "City name must not be empty"}
```

### Query City Population

**GET /city/{city_name}**

Retrieve a city's population:

```bash
curl -s http://localhost:8000/city/London
```

Successful response (200):

```json
{"city": "London", "population": 9000000}
```

Case-insensitive lookup (returns original stored casing):

```bash
curl -s http://localhost:8000/city/london
```

```json
{"city": "London", "population": 9000000}
```

Error response for non-existent city (404):

```bash
curl -s http://localhost:8000/city/Atlantis
```

```json
{"detail": "City 'Atlantis' not found"}
```

## Running Tests

```bash
pytest tests/ -v
```

Run only property-based tests:

```bash
pytest tests/test_properties.py -v
```

## Reflection

### Challenges Faced

- **Elasticsearch async lifecycle management**: Coordinating the async Elasticsearch client with FastAPI's lifespan required careful handling of startup verification and graceful shutdown. The client must be fully initialized and connected before the application begins accepting traffic.
- **Case-insensitive city name handling**: Implementing case-insensitive lookup while preserving the original stored casing required a design decision to use the lowercased name as the Elasticsearch document ID and store the display name as a separate field.
- **Input validation ordering**: Ensuring that path parameter validation (city name) runs before body parsing required manual validation rather than relying solely on Pydantic model validators, since FastAPI processes them in a specific order.
- **Helm subchart coordination**: Configuring the Bitnami Elasticsearch subchart to work seamlessly with the API service required careful wiring of service names and environment variables so the API can locate Elasticsearch at startup without manual intervention.
- **Elasticsearch memory consumption during local development**: Running Elasticsearch in Docker Desktop with its default JVM heap settings (1-2GB) caused the container to OOM and froze the host machine entirely, requiring a hard restart. This was resolved by limiting the JVM heap to 256MB via `ES_JAVA_OPTS=-Xms256m -Xmx256m` and setting a hard Docker memory limit with `-m 512m`, which is more than sufficient for development and testing with small datasets.
- **Elasticsearch client version incompatibility**: The Python `elasticsearch[async]` client v9.x sends an `Accept` header with `compatible-with=9`, which Elasticsearch 8.x rejects with a `media_type_header_exception`. The API container would start but immediately exit because the health ping failed. This was fixed by pinning the client to `elasticsearch[async]>=8.0.0,<9.0.0` in `requirements.txt` to match the server version.

### Production Scaling Suggestions

**High-Availability Elasticsearch**
- Deploy a multi-node Elasticsearch cluster with at least 3 master-eligible nodes and dedicated data nodes.
- Configure index replicas (1+ replicas) for data redundancy and read scalability.
- Use persistent volumes with appropriate storage classes to survive node failures.

**Observability (Metrics, Logging, Tracing)**
- Integrate Prometheus metrics via `prometheus-fastapi-instrumentator` for request latency, error rates, and throughput.
- Ship structured JSON logs to a centralized logging platform (e.g., ELK stack, Loki) for search and alerting.
- Add distributed tracing with OpenTelemetry to trace requests across the API and Elasticsearch for latency debugging.
- Set up alerts on key SLIs: error rate > threshold, p99 latency spikes, Elasticsearch cluster health degradation.

**Security Hardening**
- Enable TLS between the API and Elasticsearch, and for external API traffic via an ingress controller with TLS termination.
- Add authentication/authorization (e.g., API keys, OAuth2) to protect write endpoints.
- Enable Elasticsearch security features (X-Pack) with role-based access control.
- Use Kubernetes Network Policies to restrict traffic between pods.
- Run regular vulnerability scans on the container image.
- Implement rate limiting to prevent abuse.

**Horizontal Pod Autoscaling**
- Configure a Kubernetes HorizontalPodAutoscaler (HPA) based on CPU/memory utilization or custom metrics (request rate).
- Run multiple Uvicorn workers behind Gunicorn for better CPU utilization per pod.
- Use pod disruption budgets to ensure availability during rolling updates.
- Consider a PodDisruptionBudget for Elasticsearch nodes as well.
