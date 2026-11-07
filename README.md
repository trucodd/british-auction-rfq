# British Auction in RFQ System

A simplified RFQ (Request for Quotation) system supporting **British
Auction–style open bidding**, with anti-sniping time extensions and forced
close rules. Suppliers compete openly by undercutting bids; qualifying
activity near the end time extends the auction - never past the forced close.

## Quick Start

```bash
docker compose up -d --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API / Swagger | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 (rfq/rfq) |

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/rfqs` | create RFQ + auction config |
| `GET` | `/api/rfqs` | list (lowest bid, closes, status) |
| `GET` | `/api/rfqs/{id}` | detail: ranked bids, logs, config |
| `POST` | `/api/rfqs/{id}/bids` | place bid (may trigger extension) |
| `GET` | `/api/rfqs/stream` | SSE: real-time updates for the list page |
| `GET` | `/api/rfqs/{id}/stream` | SSE: real-time updates for the auction page |
| `GET` | `/api/health` | health check |

## Documentation

- [HLD.md](./HLD.md) - architecture diagram, auction engine flow, lifecycle
- [SCHEMA_DESIGN.md](./SCHEMA_DESIGN.md) - ER diagram and design decisions

## Stack

FastAPI · SQLAlchemy · PostgreSQL 16 · APScheduler · React + TypeScript (Vite) · Tailwind · Docker Compose
