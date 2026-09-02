# Data Relay Server

Independent observability and accountability service for authorized infrastructure.

Purpose: collect telemetry and audit events asynchronously without sitting in the critical path of monitored services. The server records system metrics, application logs, user actions, database activity, API calls, security events, errors, communications metadata, file-transfer audit events, alerts and predictions.

Core accountability model: **who did what, when, where, how, to what resource, and with what result**.

Operational principle: monitored services must continue operating normally if this server is unavailable. Collectors should buffer locally and forward asynchronously.
