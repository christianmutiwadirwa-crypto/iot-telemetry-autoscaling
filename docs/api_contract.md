# Ingest API Contract & Specification

## 1. Base URL & Protocol
* **Protocol:** HTTPS (HTTP for local Docker / kind testing)
* **Default Port:** `8000`
* **Content-Type:** `application/json`

---

## 2. Authentication
Every request from a sensor node (or the simulation fleet) must include a valid per-device API key in the request headers:

```http
X-Device-API-Key: <secret-device-api-key>
```

* If header is missing or key is invalid: Return `401 Unauthorized`.

---

## 3. Endpoints

### 3.1 Ingest Telemetry Batch
* **Method:** `POST`
* **Path:** `/api/v1/telemetry`
* **Description:** Asynchronously accepts a telemetry batch (either `summary` or `waveform`). Upon schema validation, the payload is published to the appropriate RabbitMQ queue (`telemetry.live` or `telemetry.backfill`).

#### Request Headers:
```http
Content-Type: application/json
X-Device-API-Key: dev-secret-key-123
```

#### Request Body:
Conforms strictly to [`schemas/telemetry_schema.json`](../schemas/telemetry_schema.json).

#### Responses:
* **`202 Accepted`**
  * **Meaning:** Batch validated and enqueued to RabbitMQ for processing.
  * **Body:**
    ```json
    {
      "status": "accepted",
      "batch_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
      "queue": "telemetry.live",
      "received_at": "2026-10-27T09:40:00.123Z"
    }
    ```
* **`400 Bad Request`**
  * **Meaning:** Malformed JSON or schema validation failure.
  * **Body:**
    ```json
    {
      "status": "error",
      "code": "VALIDATION_FAILED",
      "detail": "Field 'sent_at' is required."
    }
    ```
* **`401 Unauthorized`**
  * **Meaning:** Missing or invalid `X-Device-API-Key`.
  * **Body:**
    ```json
    {
      "status": "error",
      "code": "UNAUTHORIZED",
      "detail": "Invalid or missing device API key."
    }
    ```
* **`429 Too Many Requests`**
  * **Meaning:** Service backpressure. Returned when memory threshold is reached or internal buffer queue is saturated.
  * **Headers:** `Retry-After: 5`
  * **Body:**
    ```json
    {
      "status": "error",
      "code": "RATE_LIMIT_EXCEEDED",
      "detail": "Server under heavy load. Retry after 5 seconds."
    }
    ```

---

### 3.2 Health & Readiness Probes (Kubernetes)

* **Liveness Probe:**
  * **Method:** `GET`
  * **Path:** `/healthz`
  * **Response:** `200 OK`
  * **Body:** `{"status": "alive"}`
  * **Usage:** Kubernetes restarts container if this fails.

* **Readiness Probe:**
  * **Method:** `GET`
  * **Path:** `/readyz`
  * **Response:** `200 OK` (if RabbitMQ connection is healthy) or `503 Service Unavailable`
  * **Usage:** Kubernetes directs traffic only to ready pods.

* **Prometheus Metrics:**
  * **Method:** `GET`
  * **Path:** `/metrics`
  * **Usage:** Scraped by Prometheus for requests/sec, 429 errors, and latency percentiles.
