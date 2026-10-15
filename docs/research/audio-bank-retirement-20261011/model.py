"""Bounded synthetic models of selected captured branches; no native execution."""
import itertools

def signed16(value):
    value &= 0xffff
    return value if value < 0x8000 else value - 0x10000

def eligible(present, player_busy, refs, stream_flag, kind, stream_busy):
    if not present: return True
    if player_busy: return False
    if signed16(refs) > 0: return False
    if not stream_flag: return True
    if kind == 3: return True
    return not stream_busy

def wrapper_eligibility(driver, layout, driver_result, layout_result):
    # 078BE0: either missing object bypasses both predicates.
    if not driver or not layout: return True, []
    if not driver_result: return False, ['driver']
    return layout_result, ['driver', 'layout']

def wrapper_delete(force, driver, layout, layout_result, driver_result):
    # 078B50: false layout result blocks nonforced deletion.
    events=[]
    if not force and layout:
        events.append('layout')
        if not layout_result: return False, events
    if driver:
        events.append('driver-delete')
        return driver_result, events
    return True, events

def stream_busy(pending, active_matches, state, reader_ready):
    if pending: return True
    if not active_matches: return False
    return state == 1 or not reader_ready

def cancel(pending_keys, active_key, state, reader_ready, key=7):
    kept=[]; recycled=[]
    for record,key_value in enumerate(pending_keys):
        if key_value == key: recycled.append(record)
        else: kept.append(record)
    active_marked=active_key == key
    success=not active_marked or (state == 0 and reader_ready)
    return dict(success=success, kept=kept, recycled=recycled, activeMarked=active_marked)

def remove_bank(stream_flag, stream_member, kind, cancellation):
    state=dict(streamMember=stream_member, flag20=True, hashMember=True,
               liveMember=True, destroyed=False, returnedToPool=False)
    events=[]
    if stream_flag:
        if stream_member:
            state['streamMember']=False; events.append('unlink-stream')
        if kind == 3:
            state['flag20']=False; events.append('clear-flag20')
        events.append('cancel')
        if not cancellation: return False,state,events
    state.update(hashMember=False,liveMember=False,destroyed=True,returnedToPool=True)
    events.extend(['unlink-hash','unlink-live','free-aux-if-any','destruct-flag0','return-pool'])
    return True,state,events

def admission(free_nodes, sedb, version, sscf, tool):
    pool=list(free_nodes); events=[]
    if not pool: return 0,pool,events
    node=pool.pop(0);events.append('pop')
    if not sedb: return 0,pool,events
    if (version & 0xffffffff) > 4: return 0,pool,events
    events.append('generation')
    if not sscf: return 0,pool,events
    events.extend(['tool' if tool else 'actual','link-live','initialize','count-increment'])
    return node,pool,events

def generation(previous, wrapped, live_low20):
    candidate=previous+1
    if candidate >= 0x100000:
        candidate=1;wrapped+=1
    if wrapped:
        # Limited fixtures leave a free candidate. No universal termination proof.
        while candidate in live_low20:
            candidate+=1
            if candidate >= 0x100000: candidate=1;wrapped+=1
    return candidate,wrapped

def run():
    cases=[]
    def case(group, inputs, result): cases.append(dict(group=group,input=inputs,result=result))
    refs=[0,1,0x7ffe,0x7fff,0x8000,0xfffe,0xffff]
    for present,player,ref,flag,kind,busy in itertools.product([False,True],[False,True],refs,[False,True],[1,3],[False,True]):
        got=eligible(present,player,ref,flag,kind,busy)
        blocked=present and (player or 0<(ref if ref<32768 else ref-65536) or flag and kind!=3 and busy)
        assert got == (not blocked)
        case('eligibility',[present,player,ref,flag,kind,busy],got)
    for driver,layout,dr,lr in itertools.product([False,True],repeat=4):
        result,events=wrapper_eligibility(driver,layout,dr,lr)
        assert result == (not driver or not layout or dr and lr)
        assert events == ([] if not driver or not layout else ['driver','layout'] if dr else ['driver'])
        case('wrapper-eligibility',[driver,layout,dr,lr],[result,events])
        for force in [False,True]:
            result,events=wrapper_delete(force,driver,layout,lr,dr)
            allowed=force or not layout or lr
            assert result == (allowed and (not driver or dr))
            assert ('driver-delete' in events) == (allowed and driver)
            case('wrapper-delete',[force,driver,layout,lr,dr],[result,events])
    pending_fixtures=[[],[7],[8],[7,8,7]]
    for pending,active,state,ready in itertools.product(pending_fixtures,[None,7,8],[-1,0,1,2],[False,True]):
        b=stream_busy(7 in pending,active==7,state,ready)
        out=cancel(pending,active,state,ready)
        assert out['kept']==[i for i,k in enumerate(pending) if k!=7]
        assert out['recycled']==[i for i,k in enumerate(pending) if k==7]
        assert out['activeMarked']==(active==7)
        assert out['success']==(active!=7 or state==0 and ready)
        if active==7 and state in [-1,2] and ready and 7 not in pending:
            assert not b and not out['success']
        case('stream-predicate-cancel',[pending,active,state,ready],[b,out])
    for flag,member,kind,cancelled in itertools.product([False,True],[False,True],[1,3],[False,True]):
        ok,state,events=remove_bank(flag,member,kind,cancelled)
        assert ok == (not flag or cancelled)
        assert state['returnedToPool']==ok and state['destroyed']==ok
        if flag and not cancelled:
            assert not state['streamMember'] and state['liveMember'] and state['hashMember']
            assert state['flag20'] == (kind!=3)
        case('partial-removal',[flag,member,kind,cancelled],[ok,state,events])
    for value,step in itertools.product(refs,[-1,1]):
        result=(value+step)&0xffff
        assert result==int.from_bytes(((value+step)%65536).to_bytes(2,'little'),'little')
        if value==0x7fff and step==1: assert signed16(result)<0
        if value==0 and step==-1: assert signed16(result)==-1
        case('word-reference-arithmetic',[value,step],dict(raw=result,signed=signed16(result),blocks=signed16(result)>0))
    for nodes,sedb,version,sscf,tool in itertools.product([[],[17,18]],[False,True],[-1,0,1,4,5],[False,True],[False,True]):
        handle,pool,events=admission(nodes,sedb,version,sscf,tool)
        accepted=bool(nodes) and sedb and 0<=version<=4 and sscf
        assert bool(handle)==accepted
        assert pool==(nodes[1:] if nodes else [])
        if nodes and not accepted:
            assert events[0]=='pop' and 'return-pool' not in events
        if accepted and version==0:
            assert 'initialize' in events # factory gate accepts0; initializer validity is separate.
        case('factory-admission',[nodes,sedb,version,sscf,tool],[handle,pool,events])
    for previous,wrapped,live in itertools.product([0,1,0xffffe,0xfffff],[0,1],[[],[1],[1,2],[0xfffff]]):
        v,w=generation(previous,wrapped,live)
        assert 1<=v<0x100000
        if w: assert v not in live
        case('generation',[previous,wrapped,live],[v,w])
    # A generation may be reused after wrap when an old bank is no longer live.
    assert generation(0xfffff,0,[])[0]==generation(0,0,[])[0]==1
    case('generation-reuse',[],1)
    for mode,release,transfer_changed in itertools.product([0,1,2,3],[False,True],[False,True]):
        # After the first transfer wait has returned, the second loop may exit
        # because release succeeds OR transfer+108 becomes nonzero again.
        exits=release or transfer_changed
        free_clear=exits and mode!=2
        assert not free_clear or mode!=2
        case('destructor-loop-boundary',[mode,release,transfer_changed],dict(exits=exits,freeClear=free_clear,borrowedPointerPreserved=mode==2))
    totals={}
    for x in cases:totals[x['group']]=totals.get(x['group'],0)+1
    return dict(status='PASS',cases=len(cases),groups=totals,results=cases,
                scope='Finite Python state models of selected branch conditions and ordered side effects. No original code, allocator, filesystem, audio thread or game execution; no reachability or concurrency proof.')

if __name__=='__main__':
    import json
    print(json.dumps(run(),sort_keys=True))
