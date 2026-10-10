#!/usr/bin/env python3
import json, sys
for line in sys.stdin:
    try: req=json.loads(line)
    except Exception: continue
    method=req.get('method'); rid=req.get('id')
    if method=='server/discover':
        out={'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Method not found'}}
    elif method=='initialize':
        out={'jsonrpc':'2.0','id':rid,'result':{'protocolVersion':'2025-11-25','capabilities':{'tools':{}},'serverInfo':{'name':'legacy-mock','version':'1'}}}
    elif method=='notifications/initialized':
        continue
    elif method=='tools/list':
        out={'jsonrpc':'2.0','id':rid,'result':{'tools':[{'name':'legacy_echo','description':'Legacy echo'}]}}
    else:
        out={'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'not found'}}
    sys.stdout.write(json.dumps(out)+'\n'); sys.stdout.flush()
