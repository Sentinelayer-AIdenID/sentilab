"""Bounded localhost-only serving check on the same frozen20fixture prompts."""
import json
from pathlib import Path
import sys
import time
import urllib.request

root=Path('/home/dell/sentilab/preflight-20261031')
output=Path(sys.argv[1])
rows=[json.loads(line) for line in (root/'fixtures/eval.jsonl').read_text().splitlines()]
assert len(rows)==20
with urllib.request.urlopen('http://127.0.0.1:18018/v1/models',timeout=5) as response:
    models=json.load(response)
(output/'http-models.json').write_text(json.dumps(models,indent=2)+'\n')
ids={m['id'] for m in models['data']}
assert {'base','fixture'}<=ids
results=[]
for model in ['base','fixture']:
    for row in rows:
        if (root/'STOP').exists() or time.time()>=1793440800:
            raise RuntimeError('STOP/deadline')
        body={'model':model,'messages':[{'role':'system','content':row['system']},
              {'role':'user','content':row['instruction']}],'temperature':0,'seed':818,'max_tokens':80}
        request=urllib.request.Request('http://127.0.0.1:18018/v1/chat/completions',
                  data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        started=time.monotonic()
        with urllib.request.urlopen(request,timeout=60) as response:
            result=json.load(response)
        text=result['choices'][0]['message']['content']
        try: parsed=json.loads(text)
        except (ValueError,TypeError): parsed=None
        receipt={'model':model,'row_id':row['row_id'],'response':result,
                 'exact_json_match':parsed==json.loads(row['output']),
                 'elapsed_seconds':time.monotonic()-started}
        results.append(receipt)
        with (output/'http-responses.jsonl').open('a') as handle:
            handle.write(json.dumps(receipt)+'\n')
(output/'http-result.json').write_text(json.dumps({
    'requests':40,'base_exact':sum(r['exact_json_match'] for r in results if r['model']=='base'),
    'adapter_exact':sum(r['exact_json_match'] for r in results if r['model']=='fixture'),
    'claim':'Localhost serving of base and fixture adapter; not a physical-learning benchmark'},indent=2)+'\n')
