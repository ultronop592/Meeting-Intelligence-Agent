import urllib.request, json, time

time.sleep(6)
runs = json.loads(urllib.request.urlopen(urllib.request.Request(
    'https://api.github.com/repos/ultronop592/Meeting-Intelligence-Agent/actions/runs',
    headers={'User-Agent': 'python'}
)).read())
run = runs['workflow_runs'][0]
run_id = run['id']
print(f"Run {run_id}: {run['status']} / {run['conclusion']}")

for i in range(25):
    time.sleep(15)
    data = json.loads(urllib.request.urlopen(urllib.request.Request(
        f'https://api.github.com/repos/ultronop592/Meeting-Intelligence-Agent/actions/runs/{run_id}',
        headers={'User-Agent': 'python'}
    )).read())
    print(f"  [{i+1}] {data['status']} / {data['conclusion']}")
    if data['status'] == 'completed':
        print("FINAL:", data['conclusion'].upper())
        break

