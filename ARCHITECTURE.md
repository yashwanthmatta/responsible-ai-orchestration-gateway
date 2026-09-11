# Architecture Notes

## Core components

| Component | Responsibility | Production counterpart |
| --- | --- | --- |
| Safety gate | Blocks explicitly prohibited requests | Versioned moderation service |
| PII redactor | Removes common sensitive identifiers | DLP service with tenant policies |
| Policy router | Selects a model profile | Rules/experimentation control plane |
| Model adapter | Provides a stable inference boundary | Multi-provider inference clients |
| Review queue | Tracks uncertain or high-risk results | Durable HITL workflow system |
| Audit trail | Records the decision path | Immutable event stream and warehouse |

## Production request lifecycle

1. Authenticate the tenant and validate the request schema.
2. Assign an idempotency key and distributed trace identifier.
3. Apply versioned safety, privacy, and routing policies.
4. Invoke the selected provider with deadlines and circuit breaking.
5. Evaluate confidence, groundedness, and task-specific quality signals.
6. Return an accepted response or create a durable human-review task.
7. Emit privacy-safe events for audit, evaluation, billing, and observability.

## Scaling considerations

- Stateless gateway replicas scale horizontally behind a load balancer.
- Partition review and audit events by tenant and request identifier.
- Apply backpressure and admission control before constrained model capacity.
- Cache only policy-safe, tenant-scoped results with explicit expiry.
- Treat policy versions and model versions as required audit dimensions.

