import asyncio, urllib.request, json
from sqlalchemy import text
from app.core.security import create_access_token
from app.db.session import make_tenant_session

async def main():
    async with make_tenant_session("t_mauriciovelez") as db:
        await db.execute(text("SET search_path TO t_mauriciovelez, public"))
        row = (await db.execute(text("SELECT id FROM agents WHERE role=:r AND active=true LIMIT 1"), {"r":"admin"})).first()
    token = create_access_token({"sub": str(row[0]), "role": "admin", "tenant_slug": "mauriciovelez"}, expires_minutes=5)
    req = urllib.request.Request("http://127.0.0.1:8000/api/v1/conversations/counts", headers={"Authorization": "Bearer "+token, "X-Tenant-ID": "mauriciovelez"})
    with urllib.request.urlopen(req, timeout=10) as response:
        print("status=", response.status, "body=", json.load(response))

asyncio.run(main())
