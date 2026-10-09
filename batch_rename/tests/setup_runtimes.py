"""Fetch hash-verified official Windows bpy wheels into isolated test runtimes."""
import concurrent.futures as cf
import hashlib,json,urllib.request,zipfile,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]/"blender_validation_runtime"
ROOT.mkdir(exist_ok=True)
def fetch(url):
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=60) as response:
        return response.read()
def wheel(project,version=None):
    data=json.loads(fetch(f"https://pypi.org/pypi/{project}/"+(f"{version}/" if version else "")+"json"))
    candidates=[v for v in data['urls'] if v['filename'].endswith('.whl') and any(x in v['filename'] for x in ('cp313-cp313-win_amd64','py3-none-any','py2.py3-none-any'))]
    item=candidates[0];size=item['size'];url=item['url'];path=ROOT/item['filename']
    if not path.exists():
        def part(start):
            end=min(size,start+1048576)-1
            for attempt in range(4):
                try:
                    req=urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}'})
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=45) as response:
                        assert response.status==206
                        assert response.headers['Content-Range']==f'bytes {start}-{end}/{size}'
                        payload=response.read();assert len(payload)==end-start+1
                        return payload
                except Exception:
                    if attempt==3:raise
        with cf.ThreadPoolExecutor(max_workers=32) as pool,path.open('wb') as out:
            for payload in pool.map(part,range(0,size,1048576)):out.write(payload)
    hasher=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):hasher.update(block)
    actual=hasher.hexdigest()
    assert actual==item['digests']['sha256'],path
    print('VERIFIED',path.name,flush=True)
    return path
embed=ROOT/'python.zip'
if not embed.exists():embed.write_bytes(fetch('https://www.python.org/ftp/python/3.13.7/python-3.13.7-embed-amd64.zip'))
deps=[wheel('numpy','2.2.6')]+[wheel(p) for p in ('cattrs','attrs','typing_extensions','requests','urllib3','certifi','charset_normalizer','idna','zstandard','cython')]
for name,version in [('bpy51','5.1.0'),('bpy52','5.2.2')]:
    dest=ROOT/name;dest.mkdir(exist_ok=True)
    for archive in [embed,wheel('bpy',version),*deps]:
        with zipfile.ZipFile(archive) as z:z.extractall(dest)
    (dest/'python313._pth').write_text('python313.zip\n.\nimport site\n',encoding='utf-8')
    print('READY',name,flush=True)
