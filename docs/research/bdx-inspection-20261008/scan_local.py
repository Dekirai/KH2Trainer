"""Read-only local loose BAR scan. Evidence of disk bytes, not package identity."""
from pathlib import Path
import hashlib, json, struct
from bdx_inspect import inspect, path_to

HERE = Path(__file__).resolve().parent
ASSETS = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\Modding\openkh\data\kh2')

def run():
    results, failures, hits, inventory = [], [], [], []
    paths = [ASSETS/'00common.bdx'] + sorted((ASSETS/'obj').glob('*.mdlx'))
    for path in paths:
        data = path.read_bytes()
        asset_name = path.relative_to(ASSETS).as_posix()
        asset_sha = hashlib.sha256(data).hexdigest()
        inventory.append(dict(asset=asset_name, bytes=len(data), sha256=asset_sha))
        script_spans = []
        if path.suffix == '.bdx':
            script_spans.append((None, None, 0, len(data)))
        elif data[:4] == b'BAR\x01' and len(data) >= 16:
            count, = struct.unpack_from('<i', data, 4)
            if not 0 <= count <= 4096 or 16 + count * 16 > len(data):
                failures.append(dict(asset=path.relative_to(ASSETS).as_posix(), error='invalid BAR table'))
                continue
            for ordinal in range(count):
                typ, link, tag, offset, length = struct.unpack_from('<HH4sII', data, 16 + ordinal * 16)
                if typ == 3 and length:
                    if offset < 16 + count * 16 or offset + length > len(data):
                        failures.append(dict(asset=path.relative_to(ASSETS).as_posix(), error='invalid BAR span'))
                    else:
                        script_spans.append((ordinal, tag.hex(), offset, length))
        for ordinal, tag, offset, length in script_spans:
            ident = dict(asset=asset_name, assetSha256=asset_sha,
                         barOrdinal=ordinal, barTag=tag, offset=offset, length=length)
            try:
                doc = inspect(data[offset:offset+length])
            except ValueError as e:
                failures.append(dict(**ident, error=str(e)))
                continue
            matched = [i for i in doc['instructions'] if i.get('bank') == 2 and i.get('index') in (9, 95)]
            event27 = [e for e in doc['header']['events'] if e['id'] == 27 and not e['shadowed']]
            row = dict(**ident, scriptSha256=doc['sha256'], name=doc['header']['name'],
                       instructionCount=len(doc['instructions']), diagnostics=doc['diagnostics'],
                       traps=[dict(pc=i['pc'], index=i['index']) for i in matched], hasEvent27=bool(event27))
            results.append(row)
            if matched:
                witnesses = []
                for ins in matched:
                    routes=[]
                    for event in doc['header']['events']:
                        if event['shadowed']:continue
                        route = path_to(doc,event['pc'],ins['pc'])
                        if route is not None:
                            route_info = dict(eventId=event['id'], entryPc=event['pc'], edgeCount=len(route),
                                              pathSha256=hashlib.sha256(json.dumps(route,sort_keys=True).encode()).hexdigest())
                            if asset_name in ('obj/B_AL020.mdlx', 'obj/B_EX400.mdlx'):
                                route_info['path'] = route
                            routes.append(route_info)
                    witnesses.append(dict(instruction=ins,routes=routes))
                hits.append(dict(**ident, scriptSha256=doc['sha256'], header=doc['header'],
                                 diagnostics=doc['diagnostics'], witnesses=witnesses))
    return dict(schema=1, scanScope='00common.bdx and direct type3 entries of all obj/*.mdlx loose files',
                sourceRoot=str(ASSETS), fileCount=len(paths), inventory=inventory, scripts=results, failures=failures, hits=hits,
                limits='Local loose bytes only until selected source is independently compared with a retail package. Syntactic CFG paths do not prove execution, operand validity, or motion-event use.')

if __name__=='__main__':
    import sys
    report=run()
    output=json.dumps(report,indent=2)+'\n'
    if '--check' in sys.argv:
        assert (HERE/'loose-scan.json').read_text(encoding='utf-8')==output, 'scan output changed'
    else:
        (HERE/'loose-scan.json').write_text(output,encoding='utf-8')
    print('files',report['fileCount'],'scripts',len(report['scripts']),'failures',len(report['failures']),'hits',len(report['hits']))
    for h in report['hits'][:30]:
        print(h['asset'],h['barOrdinal'],h['offset'],h['length'],h['scriptSha256'],
              [(w['instruction']['pc'],w['instruction']['index'],[r['eventId'] for r in w['routes']]) for w in h['witnesses']],
              'diagnostics',len(h['diagnostics']))
