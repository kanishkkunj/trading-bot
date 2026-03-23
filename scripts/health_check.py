#!/usr/bin/env python3
"""Health check script for diagnostics."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import httpx


async def check_backend() -> dict:
    """Check backend health."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/api/v1/admin/health")
            return {"status": "ok", "data": response.json()}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def check_frontend() -> dict:
    """Check frontend health."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:3000")
            return {"status": "ok", "code": response.status_code}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def main() -> None:
    """Run health checks."""
    print("🏥 TradeCraft Health Check")
    print("=" * 40)

    # Check backend
    print("\n🔌 Checking backend...")
    backend_health = await check_backend()
    if backend_health["status"] == "ok":
        print("✅ Backend is healthy")
        print(f"   Services: {backend_health['data'].get('services', {})}")
    else:
        print(f"❌ Backend error: {backend_health.get('error')}")

    # Check frontend
    print("\n🌐 Checking frontend...")
    frontend_health = await check_frontend()
    if frontend_health["status"] == "ok":
        print("✅ Frontend is responding")
    else:
        print(f"❌ Frontend error: {frontend_health.get('error')}")

    print("\n" + "=" * 40)
    print("Health check complete!")


if __name__ == "__main__":
    asyncio.run(main())
