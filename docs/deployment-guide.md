# Deployment guide

Deployment to Microsoft Azure is a future task; this repository does not provision Azure resources.

The intended architecture is a Django REST API hosted on an Azure application compute service, a managed Azure Database for PostgreSQL instance, and the dashboard's static production assets served through an appropriate Azure static hosting/CDN service. The Capacitor mobile clients would use a secured HTTPS API endpoint and platform-specific app distribution processes.

Before production deployment, define secret storage, network access, database backups and migrations, TLS, logging/monitoring, CORS origins, static/media storage, CI/CD, and tenant isolation controls. Do not use the development `.env` values in production.
