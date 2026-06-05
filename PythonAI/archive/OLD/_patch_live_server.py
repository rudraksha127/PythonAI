"""Patch live_server.py: add provider importing, state, and heartbeat broadcasting."""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

path = 'live_server.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# 1. Add import after massive_engine
old1 = 'try:\n    from src.data.massive_engine import MassiveWorkerEngine\nexcept ImportError:\n    MassiveWorkerEngine = None  # Will be handled gracefully\n\n# \u2500\u2500 HTTP Static File Server'
new1 = 'try:\n    from src.data.massive_engine import MassiveWorkerEngine\nexcept ImportError:\n    MassiveWorkerEngine = None  # Will be handled gracefully\n\ntry:\n    from src.data.apikeys import resolve_all, PROVIDER_LABELS, PROVIDER_TIERS\nexcept ImportError:\n    resolve_all = lambda: {}\n    PROVIDER_LABELS = {}\n    PROVIDER_TIERS = {}\n\n# \u2500\u2500 HTTP Static File Server'
if old1 in content:
    content = content.replace(old1, new1, 1)
    changes += 1
    print('OK edit1: added import')
else:
    print('FAIL edit1')

# 2. Add providers to SYSTEM_STATE
old2 = '        "teacher": {"status": "idle", "last_action": ""},\n    },\n    "cost_usd": 0.0,\n}\n\n\nasync def broadcast'
new2 = '        "teacher": {"status": "idle", "last_action": ""},\n    },\n    "cost_usd": 0.0,\n    "providers": {},\n}\n\n\nasync def broadcast'
if old2 in content:
    content = content.replace(old2, new2, 1)
    changes += 1
    print('OK edit2: added providers state')
else:
    print('FAIL edit2')

# 3. Add provider update + providers to heartbeat
old3 = '        await broadcast("HEARTBEAT", {\n            \"uptime_s\": round(time.time() - SYSTEM_STATE["uptime_start"]),\n            "stats": SYSTEM_STATE["stats"],\n            "agents": SYSTEM_STATE["agents"],\n            "status": SYSTEM_STATE["status"],\n        })'
new3 = '        # Update provider status\n        try:\n            keys = resolve_all()\n            providers_data = {}\n            for prov, key in keys.items():\n                label = PROVIDER_LABELS.get(prov, prov)\n                tier = PROVIDER_TIERS.get(prov, "standard")\n                providers_data[prov] = {\n                    "label": label,\n                    "tier": tier,\n                    "has_key": True,\n                    "status": "online",\n                }\n            SYSTEM_STATE["providers"] = providers_data\n        except Exception:\n            pass\n\n        await broadcast("HEARTBEAT", {\n            "uptime_s": round(time.time() - SYSTEM_STATE["uptime_start"]),\n            "stats": SYSTEM_STATE["stats"],\n            "agents": SYSTEM_STATE["agents"],\n            "providers": SYSTEM_STATE["providers"],\n            "status": SYSTEM_STATE["status"],\n        })'
if old3 in content:
    content = content.replace(old3, new3, 1)
    changes += 1
    print('OK edit3: added provider heartbeat')
else:
    print('FAIL edit3')

if changes > 0:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('\nDONE: %d changes applied to live_server.py' % changes)
else:
    print('\nNO changes applied')
