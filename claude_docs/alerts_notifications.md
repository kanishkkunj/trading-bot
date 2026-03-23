# Alerts & Notifications

This file explains how alerts and notifications are handled.

## Location
- Alert modules are in `backend/app/alerts/`.

## Types of Alerts
- **Email**: Sent via `email.py`.
- **Telegram**: Sent via `telegram.py`.
- **WhatsApp**: Sent via `whatsapp.py`.

## How Alerts Work
- Alerts are triggered by trading events, errors, or risk breaches.
- Each module implements sending logic for its channel.

## Extending Alerts
- Add new alert modules to `alerts/`.

---
See backend overview and risk docs for integration.