#!/usr/bin/env python3
import json, sys
for line in sys.stdin:
    try:
        req=json.loads(line)
    except Exception:
        continue
    method=req.get('method')
    rid=req.get('id')
    if method=='server/discover':
        out={'jsonrpc':'2.0','id':rid,'result':{'resultType':'complete','supportedVersions':['2026-07-28'],'capabilities':{'tools':{}},'tools':{}}}
    elif method=='tools/list':
        out={'jsonrpc':'2.0','id':rid,'result':{'resultType':'complete','tools':[{'name':'echo','description':'Echo arguments','inputSchema':{'type':'object'}}]}}
    elif method=='tools/call':
        args=(req.get('params') or {}).get('arguments') or {}
        out={'jsonrpc':'2.0','id':rid,'result':{'resultType':'complete','content':[{'type':'text','text':json.dumps(args,sort_keys=True)}]}}
    elif method=='initialize':
        out={'jsonrpc':'2.0','id':rid,'result':{'protocolVersion':'2025-11-25','capabilities':{'tools':{}},'serverInfo':{'name':'mock','version':'1'}}}
    elif rid is None:
        continue
    else:
        out={'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'not found'}}
    sys.stdout.write(json.dumps(out)+'\n'); sys.stdout.flush()
