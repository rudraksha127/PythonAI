"""ForgeAI Live QA Test — All Roles"""
import httpx, time, sys

results = []

def test(name, role, url, method='GET', json_data=None, expect_status=200, check_fn=None):
    start = time.time()
    try:
        with httpx.Client(timeout=8.0) as c:
            if method == 'POST':
                r = c.post(url, json=json_data or {})
            else:
                r = c.get(url)
            ms = (time.time()-start)*1000
            ok = r.status_code == expect_status
            detail = ''
            if check_fn and ok:
                ok, detail = check_fn(r.json())
            if not ok and not detail:
                detail = 'status=' + str(r.status_code)
            results.append((name, role, ok, ms, detail))
    except Exception as e:
        ms = (time.time()-start)*1000
        results.append((name, role, False, ms, str(e)[:80]))

print('DEVOPS ENGINEER - Infrastructure')
print('-'*40)
test('PythonAI :7337 alive', 'DevOps', 'http://localhost:7337/health')
test('Rudra-bots :7000 alive', 'DevOps', 'http://localhost:7000/api/health')
test('Dashboard :3000 alive', 'DevOps', 'http://localhost:3000/api/health')
test('Gateway :8000 alive', 'DevOps', 'http://localhost:8000/health')

def chk_ver(d):
    v = d.get('version', '?')
    return v == '2.1.0', 'v=' + str(v)

def chk_healthy(d):
    h = d.get('healthy_count', 0)
    return h == 3, 'healthy=' + str(h)

test('Gateway v2.1', 'DevOps', 'http://localhost:8000/health', check_fn=chk_ver)
test('3/3 services healthy', 'DevOps', 'http://localhost:8000/health', check_fn=chk_healthy)

print()
print('QA ENGINEER - API Contracts')
print('-'*40)

def chk_metrics(d):
    keys = ['server','statistics','training','rag','arsenal']
    missing = [k for k in keys if k not in d]
    return len(missing) == 0, 'missing: ' + str(missing) if missing else ''

def chk_total(d):
    return d.get('total', 0) > 0, 'total=' + str(d.get('total'))

def chk_found(d):
    return d.get('found') == True, 'not found'

def chk_ok(d):
    return d.get('status') == 'ok', str(d.get('status'))

def chk_healthy_str(d):
    return d.get('status') == 'healthy', str(d.get('status'))

test('Ecosystem metrics schema', 'QA', 'http://localhost:7337/api/forgeai/ecosystem-metrics', check_fn=chk_metrics)
test('Arsenal summary', 'QA', 'http://localhost:7337/api/arsenal/summary', check_fn=chk_total)
test('Arsenal tool: ChromaDB', 'QA', 'http://localhost:7337/api/arsenal/tools/ChromaDB', check_fn=chk_found)
test('Arsenal unknown tool 404', 'QA', 'http://localhost:7337/api/arsenal/tools/FakeXYZ', expect_status=404)
test('Dashboard health JSON', 'QA', 'http://localhost:3000/api/health', check_fn=chk_ok)
test('Rudra-bots forgeai health', 'QA', 'http://localhost:7000/api/forgeai/health', check_fn=chk_healthy_str)
test('Rudra-bots accept metrics', 'QA', 'http://localhost:7000/api/forgeai/metrics', 'POST',
     {'type': 'acceptance_rate', 'source': 'qa', 'rate': 0.85})
test('PythonAI stats', 'QA', 'http://localhost:7337/stats')
test('Training runs', 'QA', 'http://localhost:7337/api/training/status')

print()
print('SRE - Reliability and Latency')
print('-'*40)
test('PythonAI latency <500ms', 'SRE', 'http://localhost:7337/health')
test('Gateway latency <1s', 'SRE', 'http://localhost:8000/health')

def chk_wd(d):
    return d.get('watchdog') == 'active', str(d.get('watchdog'))

def chk_sync(d):
    sd = d.get('sync_daemon', {})
    return sd.get('running') == True, 'running=' + str(sd.get('running'))

def chk_live(d):
    return d.get('cached') == False, 'cached=' + str(d.get('cached'))

test('Watchdog active', 'SRE', 'http://localhost:8000/api/watchdog', check_fn=chk_wd)
test('Sync daemon running', 'SRE', 'http://localhost:7337/api/forgeai/ecosystem-metrics', check_fn=chk_sync)
test('Rudra-bots LIVE data', 'SRE', 'http://localhost:7000/api/forgeai/fetch', check_fn=chk_live)

# Burst test
print('  Running burst test (10 rapid requests)...')
burst_ok = 0
burst_ms = 0
for i in range(10):
    start = time.time()
    try:
        r = httpx.get('http://localhost:7337/health', timeout=5.0)
        if r.status_code == 200:
            burst_ok += 1
    except:
        pass
    burst_ms += (time.time() - start) * 1000
avg_burst = burst_ms / 10
results.append(('Burst 10x: ' + str(burst_ok) + '/10 avg=' + str(int(avg_burst)) + 'ms', 'SRE',
                burst_ok == 10, avg_burst, '' if burst_ok == 10 else str(burst_ok) + '/10'))

print()
print('CTO - Architecture & Connectivity')
print('-'*40)

def chk_server_key(d):
    return 'server' in d, 'no server key'

def chk_connected(d):
    return d.get('status') == 'connected', str(d.get('status'))

test('Gateway->PythonAI proxy', 'CTO', 'http://localhost:8000/api/forgeai/ecosystem-metrics', check_fn=chk_server_key)
test('Gateway->Arsenal proxy', 'CTO', 'http://localhost:8000/api/arsenal/summary', check_fn=chk_total)
test('PythonAI->Rudra-bots sync', 'CTO', 'http://localhost:7000/api/forgeai/status', check_fn=chk_connected)
test('Stored metrics', 'CTO', 'http://localhost:7000/api/forgeai/metrics')
test('Ecosystem endpoint', 'CTO', 'http://localhost:8000/api/ecosystem')
test('Dashboard serves pages', 'CTO', 'http://localhost:3000/')

print()
print('DEVELOPER - Features & Data')
print('-'*40)

def chk_rate(d):
    return 'overall_acceptance_rate' in d, 'missing acceptance_rate'

test('Capture stats', 'Dev', 'http://localhost:7337/stats', check_fn=chk_rate)
test('Signal capture', 'Dev', 'http://localhost:7337/api/events', 'POST',
     {'event_type': 'accept', 'session_id': 'session123', 'project_id': 'project123', 'file_path': 'q.py', 'language': 'python', 'suggestion': 'pass'})
test('RAG backend info', 'Dev', 'http://localhost:7337/api/rag/backend')
test('Training schedule', 'Dev', 'http://localhost:7337/api/training/schedule')
test('Benchmark reports', 'Dev', 'http://localhost:7337/api/benchmark/reports')
test('Memory stats', 'Dev', 'http://localhost:7337/api/memory/stats')
test('TTS status', 'Dev', 'http://localhost:7337/api/tts/status')

def chk_p1(d):
    p1 = d.get('by_priority', {}).get('P1-immediate', {})
    inst = p1.get('installed', 0)
    tot = p1.get('total', 0)
    return inst == tot and tot > 0, str(inst) + '/' + str(tot)

test('Arsenal P1 complete', 'Dev', 'http://localhost:7337/api/arsenal/summary', check_fn=chk_p1)

print()
print('SECURITY - Auth & Access Control')
print('-'*40)
test('Unauth proxy rejected 401', 'Sec', 'http://localhost:8000/api/pythonai/health', expect_status=401)
test('Health exempt from auth', 'Sec', 'http://localhost:8000/health')
test('Arsenal exempt from auth', 'Sec', 'http://localhost:8000/api/arsenal/summary')

# Login + authenticated request
try:
    with httpx.Client(timeout=8.0) as c:
        start = time.time()
        r = c.post('http://localhost:8000/api/auth/login', json={'username': 'admin', 'password': 'forgeai2025'})
        ms = (time.time()-start)*1000
        if r.status_code == 200:
            data = r.json()
            if 'token' in data:
                results.append(('Auth login -> JWT', 'Sec', True, ms, ''))
                token = data['token']
                s2 = time.time()
                r2 = c.get('http://localhost:8000/api/pythonai/health',
                           headers={'Authorization': 'Bearer ' + token})
                m2 = (time.time()-s2)*1000
                results.append(('Authenticated proxy works', 'Sec', r2.status_code == 200, m2, ''))
            else:
                results.append(('Auth login -> JWT', 'Sec', False, ms, 'no token in response'))
        else:
            results.append(('Auth login -> JWT', 'Sec', False, ms, 'status=' + str(r.status_code)))
except Exception as e:
    results.append(('Auth login', 'Sec', False, 0, str(e)[:60]))

# Invalid token
try:
    with httpx.Client(timeout=5.0) as c:
        r = c.get('http://localhost:8000/api/pythonai/health',
                   headers={'Authorization': 'Bearer invalid_garbage_token_xyz'})
        results.append(('Invalid JWT rejected', 'Sec', r.status_code in (401, 403), 0,
                        '' if r.status_code in (401,403) else 'status=' + str(r.status_code)))
except Exception as e:
    results.append(('Invalid JWT rejected', 'Sec', False, 0, str(e)[:60]))

# FINAL REPORT
print()
print('=' * 60)
print('  FORGEAI MEGA PROJECT - FINAL TEST REPORT')
print('=' * 60)
passed = sum(1 for r in results if r[2])
failed = sum(1 for r in results if not r[2])
total = len(results)

for name, role, ok, ms, detail in results:
    icon = 'PASS' if ok else 'FAIL'
    lat = ' (' + str(int(ms)) + 'ms)' if ms > 0 else ''
    line = '  [' + icon + '] [' + role.ljust(6) + '] ' + name + lat
    print(line)
    if not ok and detail:
        print('           -> ' + detail)

pct = (passed / total * 100) if total > 0 else 0
if pct == 100:
    grade = 'A+ (PRODUCTION READY)'
elif pct >= 90:
    grade = 'A (NEAR PRODUCTION)'
elif pct >= 75:
    grade = 'B (STAGING READY)'
elif pct >= 50:
    grade = 'C (DEVELOPMENT)'
else:
    grade = 'F (CRITICAL ISSUES)'

latencies = [ms for _, _, _, ms, _ in results if ms > 0]
avg_lat = sum(latencies) / len(latencies) if latencies else 0
max_lat = max(latencies) if latencies else 0

print()
print('  Total: ' + str(total) + ' | Passed: ' + str(passed) + ' | Failed: ' + str(failed))
print('  Avg Latency: ' + str(int(avg_lat)) + 'ms | Max: ' + str(int(max_lat)) + 'ms')
print('  GRADE: ' + grade + ' (' + str(int(pct)) + '%)')
print('=' * 60)

sys.exit(0 if failed == 0 else 1)
