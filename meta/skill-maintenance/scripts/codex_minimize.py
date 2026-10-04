"""Minimization from the successful fixed-turn reader; no live connection on import."""
import json, re
from collections import Counter
from urllib.parse import urlparse
from common import require, SENSITIVE
from codex_proxy import iter_pages

PRIVATE_LINE=re.compile(r'(?i)(password|secret|credential|access[_-]?token|api[_-]?key|authorization|cookie|client[_-]?secret|private[_-]?key)\s*[:=]|(?:AKIA|ASIA)[A-Z0-9]{16}|-----BEGIN.*(?:PRIVATE KEY|CERTIFICATE)|gh[pousr]_[A-Za-z0-9]{12}|sk-[A-Za-z0-9]{12}')

OPAQUE=re.compile(r'(?<![\w])[A-Za-z0-9_+/=-]{60,}(?![\w])')

DIAGNOSTIC=re.compile(r'(?i)error|fatal|exception|traceback|denied|not permitted|no such|not found|failed|failure|invalid|unsupported|assert|expected|received|exit code|exit status|rejected|timeout|timed out|PASS:|Matching (?:key|value location)|unrecognized|unknown (?:option|argument)|usage:')

VERIFY=re.compile(r'(?i)passed|passing|tests? |test files|checks?|validated|verification|success|clean|up.to.date|already|removed|deleted|not installed|not running|exit code|HTTP|status(?:_code)?|insufficient|balance|credits|\b(?:200|401|402|403|404|429|500|502)\b|\back\b|check-stream|queue|cron')

def clean(text):
    require(isinstance(text,str),'non-text evidence')
    lines=[];redactions=0
    for line in text.splitlines():
        if SENSITIVE.search(line) or PRIVATE_LINE.search(line): lines.append('[sensitive line omitted]');redactions+=1;continue
        line=re.sub(r'/Users/[^\s`"\'\)\],:]+','[local-path]',line)
        line=re.sub(r'https?://[^\s)\]"\']+',lambda m: urlparse(m.group()).scheme+'://'+(urlparse(m.group()).hostname or '[host]')+urlparse(m.group()).path,line)
        line=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[email]',line)
        line=OPAQUE.sub('[opaque value omitted]',line)
        lines.append(line)
    value='\n'.join(lines)
    require(not SENSITIVE.search(value),'sensitive normalized text')
    return value,redactions

def command_facts(item):
    command=item.get('command','');output=item.get('aggregatedOutput') or ''
    require(isinstance(command,str) and isinstance(output,str),'invalid command strings')
    # Even a short first line can contain raw arguments or an unknown secret.
    head='記録されたコマンド実行。生コマンド・引数は保存しない。'
    cr=1
    failed=item.get('status')=='failed' or item.get('exitCode') not in (None,0)
    lines=output.splitlines()
    selected=[line for line in lines if (DIAGNOSTIC if failed else VERIFY).search(line) or not failed and DIAGNOSTIC.search(line)]
    diff_omitted='diff --git ' in output
    if diff_omitted: selected=[line for line in selected if not line.startswith(('+','-','@@','diff --git ','index '))]
    # Short failure output is necessary evidence, not discarded just because no marker matched.
    if failed and len(output)<=1200 and not selected and not any(x in output for x in ('trust_level','[mcp_servers','default_permissions')): selected=lines
    excerpt,redactions=clean('\n'.join(selected))
    bounded=len(excerpt)<=2500
    if not bounded:
        selected=[line for line in lines if DIAGNOSTIC.search(line)][:12]
        excerpt,redactions=clean('\n'.join(selected));excerpt=excerpt if len(excerpt)<=2500 else '[diagnostic exceeds safe summary budget]'
    return {'command_context':head,'command_context_is_partial':len(command.splitlines())>1 or cr>0,
            'exit_code':item.get('exitCode'),'execution_status':item.get('status'),
            'output_bytes':len(output.encode()),'diagnostic_excerpt':excerpt or '[no selected diagnostic/verification output]',
            'diagnostic_has_omission':not bounded or cr>0 or redactions>0 or diff_omitted,
            'diagnostic_not_available':failed and (not output or not excerpt or excerpt=='[diagnostic exceeds safe summary budget]')}

def tool(item):
    kind=item['type'];ident=item['id'];status=item.get('status')
    require(status in {'completed','failed','declined'},'unfinished tool')
    success=status=='completed';summary={};tool_name=kind
    if kind=='commandExecution':
        require(item.get('exitCode') is None or type(item['exitCode']) is int,'invalid exit')
        summary=command_facts(item);success=success and item.get('exitCode') in (None,0)
    elif kind=='fileChange':
        require(isinstance(item.get('changes'),list),'missing file result')
        # Do not retain patches; basenames/kinds suffice for locating a later safe reproduction.
        summary={'execution_status':status,'changed_files':len(item['changes']),'change_kinds':[x.get('kind') if isinstance(x.get('kind'),str) else 'structured' for x in item['changes']]}
    elif kind=='collabAgentToolCall':
        require(isinstance(item.get('agentsStates'),dict),'missing collaboration state')
        summary={'execution_status':status,'operation':item.get('tool'),'agent_status_counts':dict(Counter(x.get('status','unknown') for x in item['agentsStates'].values())),'child_histories_not_fetched':True}
        if any(x.get('status')=='errored' for x in item['agentsStates'].values()):
            success=False
            summary['diagnostic_excerpt']=clean('\n'.join(str(x.get('message','')) for x in item['agentsStates'].values() if x.get('status')=='errored'))[0]
    elif kind=='mcpToolCall':
        require(item.get('result') is not None or item.get('error') is not None or status=='declined','missing MCP result')
        result_error=(item.get('result') or {}).get('isError') is True
        success=success and item.get('error') is None and not result_error
        tool_name=kind+':'+item.get('tool','unknown')
        summary={'execution_status':status,'result_present':item.get('result') is not None,'result_is_error':result_error}
        if item.get('error') is not None:
            detail=clean(json.dumps(item['error'],ensure_ascii=False))[0]
            summary['diagnostic_excerpt']=detail if len(detail)<=2500 else '[error exceeds safe summary budget]'
            summary['diagnostic_has_omission']=len(detail)>2500
        elif status=='failed' or result_error:
            content=(item.get('result') or {}).get('content',[])
            texts=[x.get('text','') for x in content if isinstance(x,dict) and x.get('type')=='text']
            detail=clean('\n'.join(texts))[0]
            summary['diagnostic_excerpt']=detail if len(detail)<=2500 else '[error exceeds safe summary budget]'
            summary['diagnostic_not_available']=not detail or len(detail)>2500
    elif kind=='dynamicToolCall':
        require(type(item.get('success')) is bool or status=='declined','missing dynamic result')
        success=success and item.get('success') is True
        summary={'execution_status':status,'success':item.get('success'),'result_items':len(item.get('contentItems') or [])}
        tool_name=kind+':'+item.get('tool','unknown')
    else: raise ValueError('unsupported tool')
    summary_text=json.dumps(summary,ensure_ascii=False)
    require(len(summary_text)<=4096 and not SENSITIVE.search(summary_text),'unsafe or oversized summary')
    return [{'id':ident,'kind':'tool-call','tool':tool_name,'summary':summary.get('command_context') or '記録された'+tool_name+'操作。生引数・差分・外部本文は保存しない。'},
            {'id':ident+':result','kind':'tool-result','call_id':ident,'status':'cancelled' if status=='declined' else 'success' if success else 'error','summary':summary_text}]

def read_turn(proxy,thread_id,t,start,end,max_pages=20):
    START,END=start,end
    ids=set();counts=Counter();messages=[];events=[];missing=[];pages=0;excluded_reasoning=0;excluded_nonessential=Counter();orphan_results=[]
    params={'threadId':thread_id,'turnId':t['id'],'limit':20,'sortDirection':'asc'}
    for page in iter_pages(proxy,'thread/items/list',params,max_pages):
        pages+=1
        for entry in page:
            require(entry.get('turnId')==t['id'],'returned turn mismatch')
            item=entry.get('item');require(isinstance(item,dict),'invalid item')
            kind=item.get('type')
            if kind=='reasoning':
                # No reasoning ID, text, summary or content is inspected/analyzed/persisted.
                excluded_reasoning+=1
                continue
            for field in ('startedAtMs','completedAtMs'):
                ts=entry.get(field)
                require(ts is None or type(ts) is int and START*1000<=ts<=END*1000,'item outside window')
            ident=item.get('id');require(isinstance(ident,str) and ident and ident not in ids,'duplicate/missing item')
            ids.add(ident);counts[kind]+=1
            if kind in {'userMessage','agentMessage'}:
                if kind=='userMessage':
                    require(all(x.get('type')=='text' for x in item.get('content',[])),'nontext message cannot minimize')
                    value='\n'.join(x['text'] for x in item['content'])
                else:value=item['text']
                require(len(value)<=16000,'message review budget exceeded')
                value,removed=clean(value)
                messages.append({'id':ident,'kind':kind,'phase':item.get('phase'),'text':value,'redacted_lines':removed})
            elif kind in {'commandExecution','fileChange','mcpToolCall','dynamicToolCall','collabAgentToolCall'}:events.extend(tool(item))
            elif kind=='webSearch':
                results=item.get('results');require(results is None or isinstance(results,list),'invalid web result')
                if results is None:missing.append({'id':ident,'kind':kind,'reason':'API result payload absent'})
                else:events.extend([{'id':ident,'kind':'tool-call','tool':'webSearch','summary':'記録されたWeb検索。外部本文とクエリ・URLは保存しない。'},
                    {'id':ident+':result','kind':'tool-result','call_id':ident,'status':'success','summary':json.dumps({'returned_results':len(results),'external_content_not_adopted':True})}])
            elif kind=='functionCallOutput':
                name=item.get('name');require(isinstance(name,str),'missing function name')
                output=item.get('output')
                value=output if isinstance(output,str) else json.dumps(output,ensure_ascii=False)
                safe,removed=clean(value)
                lines=[x for x in safe.splitlines() if DIAGNOSTIC.search(x)]
                excerpt='\n'.join(lines)
                if not excerpt and len(safe)<=1800:excerpt=safe
                orphan_results.append({'id':ident,'tool':name,'diagnostic_excerpt':excerpt if len(excerpt)<=2500 else '[result exceeds safe summary budget]',
                    'redacted_lines':removed,'original_call_input_missing':True})
                missing.append({'id':ident,'kind':kind,'reason':'API result-only item has no original call input/link; no call is fabricated'})
            elif kind in {'contextCompaction','enteredReviewMode','exitedReviewMode','hookPrompt','plan','subAgentActivity','sleep','imageView'}:
                excluded_nonessential[kind]+=1
            else:raise ValueError('unsupported item minimizer: '+str(kind) if kind in {'imageGeneration'} else 'unknown item minimizer')
    require(counts['userMessage']>=1 and counts['agentMessage']>=1,'request/response missing')
    if len(events)>256: missing.append({'kind':'evidence-budget','reason':'more than 256 events; all private tool facts retained but not representable in current trace contract'})
    return {'thread_id':thread_id,'turn_id':t['id'],'completed_at':t['completedAt'],'messages':messages,'events':events,
            'missing_tool_results':missing,'orphan_results':orphan_results,'excluded_nonessential':dict(excluded_nonessential),'pages':pages,'item_types':dict(counts),'retained_items':len(ids),'excluded_reasoning_count':excluded_reasoning,
            'pagination_complete':True,'trace_complete':not missing,'scope':'only this approved completed turn'}
