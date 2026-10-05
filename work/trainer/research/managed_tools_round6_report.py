"""Assemble per-body findings after reading all remaining original-verified IL."""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib
import json

ROOT=Path(__file__).resolve().parents[3]
P=ROOT/'work/trainer/research'
meta=json.loads((P/'managed_tools_round6_metadata.json').read_text())
verify=json.loads((P/'managed_tools_round6_verification.json').read_text())
bodies={b['addr']:b for b in json.loads((P/'managed_tools_round6_evidence.json').read_text())}
selection={r['address']:r for r in json.loads((P/'managed_tools_round6_selection.json').read_text())}
fields={f['token']:f for f in meta['referencedFields']}
field_locations={f['token']:f for f in meta['fields']}
manual={}
def add(addr,finding,limit):
    manual[addr]=(finding,limit)

add('0x340','Forwards the original byte-string pointer and integer character to native strrchr at VA0x140471A48 and returns its borrowed pointer unchanged.',
    'No length bound, ownership transfer, path normalization or allocation. Exact MethodDef callers connect it to model/sound/telop and animated-texture path parsing; their semantics are not re-claimed here.')
add('0x350','Returns nonpositive signed32 input unchanged; for a positive input returns (input & 65535) | 0x80070000, the Win32-facility failure HRESULT conversion.',
    'Pure conversion with no GetLastError call or throwing. Values with the signed high bit set follow the unchanged branch.')
add('0x370','Calls native RaiseException with the supplied exception code and flags, zero argument count and a null argument pointer.',
    'No local catch or error dialog. Known CIL callers use code0xC000008C and flag1 for noncontinuable array bounds failure.')
add('0x380','Stores the supplied signed32 HRESULT in the four-byte CAtlException object and returns the object pointer.',
    'No allocation or message formatting; the caller supplies valid storage.')
add('0x390','Constructs a stack CAtlException from the HRESULT and passes its address plus the native _TI1?AVCAtlException@ATL@@ throw-info field to _CxxThrowException.',
    'This crosses to the native C++ exception ABI; the trailing ret does not establish normal return from the throw helper.')
add('0x3b0','Zeroes exactly40 bytes of supplied CComCriticalSection storage with initblk, then returns that storage pointer.',
    'Zeroing is not InitializeCriticalSection. A caller must separately invoke Init before using the lock.')
add('0x3c0','Contains only ret; this CComCriticalSection destructor performs no cleanup.',
    'Critical-section destruction is explicit in Term/AtlWinModuleTerm. Replacing those with this destructor would leak native synchronization state.')
add('0x3d0','Calls native ATL._AtlInitializeCriticalSectionEx(this,0,0). Success returns0; failure fetches GetLastError and converts positive signed32 errors to a Win32-facility HRESULT while retaining nonpositive values.',
    'No independent ownership flag or guard against repeated initialization. Fresh native VA0x140145780 is a tail jump through0x140471EBC to KERNEL32.InitializeCriticalSectionEx; no extra ATL fallback executes in that body.')
add('0x400','Passes the supplied lock to native DeleteCriticalSection and returns0.',
    'No initialized-state, concurrent-user or pointer check; only a caller with live lock ownership may use it.')
add('0x410','Returns the QWORD at CAtlBaseModule+8.',
    'This is a borrowed module-instance value, not a new module load or reference.')
for a in ['0x420','0x440']:
    add(a,'Copies the interface QWORD from the supplied wrapper into destination; if nonnull invokes vtable+8 with that interface pointer once, discards the unsigned32 result and returns destination.',
        'The indirect signature is preserved as token0x11000001. This is COM AddRef-style copy ownership; even the CComQIPtr<IUnknown> copy body does not call QueryInterface.')
for a in ['0x460','0xb80','0xbc0']:
    add(a,'Reads the owned interface QWORD and, if nonnull, invokes vtable+16 with the interface pointer once and discards the unsigned32 result.',
        'COM Release-style destruction does not clear the wrapper field. Calling it twice on the same stale storage is not supported; exact COM object lifetime remains the caller responsibility.')
add('0x480','Calls CComBSTR.Copy on the source wrapper, stores the returned BSTR pointer in destination, and throws CAtlException(0x8007000E) only when a nonnull source produced a null allocation.',
    'A null source is a valid null destination. Destination is constructor storage; this body does not first free any previous BSTR.')
add('0x4b0','Returns null for a null source BSTR; otherwise calls SysStringByteLen then SysAllocStringByteLen to copy exactly that byte length, retaining embedded null bytes.',
    'No encoding conversion or null-terminated scan. A redundant later null branch would allocate an empty BSTR, but the earlier null return makes that branch unreachable in this body.')
add('0x4e0','Returns a one-byte Boolean indicating whether the wrapper BSTR pointer is null.',
    'A nonnull empty string is not treated as null; no content or length read occurs.')
add('0x6f0','Initializes destination VARIANT type WORD to0, then calls VariantCopy. On negative HRESULT it writes type10 and the error DWORD at+8 before throwing the same HRESULT through AtlThrowImpl.',
    'Only the type WORD is initialized before VariantCopy; failure is not converted to a normal return. Metadata identifies24-byte CComVariant/tagVARIANT storage.')
add('0x720','Forwards destination and source VARIANT pointers to VariantCopy and returns its signed32 HRESULT unchanged.',
    'Unlike InternalCopy and the copy constructor, this wrapper does not throw or stamp a type10 error variant.')
add('0x730','Calls VariantCopy; on negative HRESULT stamps destination WORD type10 and DWORD error+8, then throws through AtlThrowImpl. Success returns void.',
    'It does not initialize the destination type before VariantCopy; the destination must already satisfy that API ownership contract.')
add('0x750','Transfers the source wrapper handle QWORD into the destination and clears the source QWORD to0, then returns destination.',
    'This is destructive move-style ownership despite the constructor name. It does not DuplicateHandle or CloseHandle.')
add('0x760','Stores the supplied handle QWORD directly into wrapper storage.',
    'No CloseHandle of a previous value and no null/invalid-handle validation. Reusing a nonempty wrapper can lose the previous handle; this is a caller precondition, not demonstrated game misuse.')
add('0x770','Returns the current handle QWORD and clears the wrapper to0.',
    'Detaches ownership without closing the handle.')
for a,cleanup in [('0x780','0x7a0'),('0x1940','0x1960')]:
    add(a,f'Constructs the shared ATL._AtlComModule through native VA0x140147070, then registers its matching CIL cleanup body {cleanup} with _atexit_m and discards the registration result.',
        'Both translation-unit copies reference the same FieldDef. Only the first copy occurs in the captured managed process initializer table; absent direct/table edges do not prove the second body unreachable from every native path.')
for a in ['0x7a0','0x1960']:
    add(a,'Passes the shared ATL._AtlComModule address to native CAtlComModule destructor VA0x140147110.',
        'No extra CIL guard or pointer clearing; this body is a registered lifetime callback, not a COM browser or application command.')
add('0x7b0','Constructs _ATL_WIN_MODULE70, writes byte-size DWORD72 and null create-window list+48, then initializes its lock+8. A negative result sets global m_bInitFailed=true and size0; returns the object in either normal case.',
    'The decoded EH clause is fault, not finally: base cleanup is invoked only while unwinding an exception. A size0 object is rejected/skipped by the corresponding module Term logic.')
add('0x7f0','Calls AtlWinModuleTerm(this, global BaseModule+8), then RemoveAll on its ushort array+56. Two fault clauses arrange base/lock-subobject unwind cleanup if the preceding operations throw.',
    'The base lock destructor is empty. Normal native lock deletion belongs to AtlWinModuleTerm; the second RemoveAll is harmless after Term already cleared the array.')
add('0x830','Calls AtlWinModuleTerm with this and the shared BaseModule instance at+8, ignoring its HRESULT.',
    'The wrapper does not surface invalid size or unregister failures to a UI.')
add('0x840','Zeroes the40-byte lock subobject at+8, then initializes array data pointer+56 and signed32 count/capacity+64/+68 to0; returns this.',
    'Does not set the leading module size or initialize the OS lock. The fault clause invokes the empty lock destructor if array construction unwinds.')
add('0x880','Calls ushort-array RemoveAll on this+56; its fault handler invokes the empty lock destructor for this+8.',
    'Does not unregister window classes or DeleteCriticalSection; those actions require the outer module Term step.')
for a,cleanup in [('0x8a0','0x920'),('0x1970','0x19f0')]:
    add(a,f'Initializes the shared72-byte ATL._AtlWinModule: clears lock40 bytes, array pointer/count/capacity and create-window pointer, writes size72, initializes the lock, marks global init failure and size0 on negative HRESULT, then registers cleanup {cleanup} with _atexit_m.',
        'A fault clause performs base cleanup only on unwind; atexit registration result is ignored. Both copies target the same native FieldDef; only the first is in the captured managed process initializer table.')
for a in ['0x920','0x19f0']:
    add(a,'Terminates the shared window module using BaseModule+8, then conditionally frees any remaining ushort atom array and clears its pointer/count/capacity. A fault clause runs the base destructor if termination unwinds.',
        'Normal Term already frees the array, so the subsequent null check prevents a normal double free. These are shutdown callbacks and are unsuitable as user-triggered refresh commands.')
add('0x980','Returns the supplied object pointer without reading or writing it.',
    'The class-factory cleanup guard constructor has no registration side effect; registration occurs in its separate static initializer.')
for a in ['0x990','0x9b0','0x1a60']:
    add(a,'Calls native CAtlComModule.Term at VA0x140146330 on the shared ATL._AtlComModule.',
        'This requests class-factory cleanup, with no independent CIL idempotence/lock guard. Full native Term semantics are outside this wrapper claim.')
for a,cleanup in [('0x9a0','0x9b0'),('0x1a50','0x1a60')]:
    add(a,f'Registers cleanup delegate {cleanup} with _atexit_m and discards the integer result.',
        'No factory is created here. Only the first translation-unit initializer appears in the captured managed process initializer table.')
add('0x9c0','Transfers the source CRegKey handle QWORD+0, access DWORD+8 and transaction-manager QWORD+16 into destination, clearing all three source fields, then returns destination.',
    'No registry key is opened, duplicated, closed or modified. Padding is not copied; the24-byte object layout comes from original metadata.')
add('0xa00','Returns the registry handle QWORD and clears handle+0, access DWORD+8 and transaction-manager QWORD+16.',
    'Detach performs no RegCloseKey; ownership passes to the caller.')
add('0xa20','Attaches a registry handle at+0 and clears access+8 and transaction-manager+16.',
    'No old handle is closed. Supplying a nonempty destination can lose prior ownership; no actual game misuse is established.')
add('0xa40','Rejects null or a nonzero size other than72 with0x80070057; size0 returns0. For a valid module it walks the signed-count ushort atom array, calls UnregisterClassA(atom,hInst) for each, frees/resets the array, deletes lock+8, clears size and returns0.',
    'Array-index checks raise noncontinuable0xC000008C, but do not validate physical allocation size. UnregisterClassA results are discarded. No synchronization excludes live users; this is a serialized shutdown contract. The leading size0 makes completed Term repeatable.')
add('0xad0','Rejects null or a leading size different from72 with0x80070057; otherwise clears create-window pointer+48 and returns the lock+8 Init HRESULT.',
    'Does not set the size, initialize the atom array or guard repeated lock initialization. Caller must supply a correctly constructed module.')
add('0xb00','Checks index>=0 and index<signed32 count at+8; returns dataPointer+2*index. An invalid index calls RaiseException(0xC000008C,1,0,null), followed by a nominal null return.',
    'Returns an element address rather than the ushort value. Arithmetic uses64-bit index*2, but the data pointer/count are trusted; no allocation-capacity or pointer check.')
add('0xb30','If the array pointer is nonnull, frees it and clears it; always clears signed32 count+8 and capacity+12.',
    'No per-element destructor is required for ushort values. The backing pointer must belong to the paired native allocator.')
add('0xb50','Returns the signed32 array count at+8.',
    'No validity or nonnegative check is performed by this getter.')
add('0xb60','Clears the array data QWORD+0 and signed32 count/capacity at+8/+12, then returns this.',
    'Only initializes empty16-byte container state; no allocation or old-buffer cleanup.')
for a in ['0xba0','0xbe0','0xc00']:
    add(a,'Stores the supplied raw interface pointer in destination; if nonnull invokes its vtable+8 once with that interface pointer and ignores the unsigned32 return, then returns destination.',
        'COM AddRef-style ownership differs from the wrapper-copy variants by receiving the raw interface directly. No QueryInterface or old destination Release.')
add('0xd90','Calls RemoveAll on the supplied ushort-array object and returns.',
    'The exact free-and-reset behavior is at CIL0xb30; no independent destructor loop or synchronization.')
add('0xda0','Forwards byte-string pointer and integer character to native strchr at VA0x140471A42 and returns its pointer result unchanged.',
    'No bounds or path-specific interpretation. Exact token callers include folder creation, sound export and animated-texture parsing; those existing tool bodies are not re-claimed.')
add('0xdb0','Forwards haystack and needle byte-string pointers to native strstr at VA0x140471A4E and returns its pointer result unchanged.',
    'No size bound or case folding in this wrapper. Existing export/checker callers give context, not a new safe scanner API.')
add('0x16e0','Dispatches scalar or array deletion for32-byte CSJointListT<EntryTex>. Flag2 reads uint64 count at this-8 and calls __ehvec_dtor(this,32,count,native dtor129B60); flag1 additionally sized-deletes the cookie block using count*32+8. Scalar path calls one native destructor and optionally delete(this). Fresh native129B60 only writes vtable5AA010; it does not unlink or destroy contained textures.',
    'Array cookie, count and allocation ownership are trusted; multiply/add are unchecked64-bit arithmetic. This is a compiler deletion helper, not a safe texture eviction command. No malformed-cookie game path is demonstrated.')
add('0x1730','Forwards all seven original arguments to native FormatMessageA at VA0x140471E8C and returns the uint32 result.',
    'The A entry point selects byte-string Windows message formatting. Flags, buffer, argument list and allocation ownership are entirely supplied by the caller; no new game-message catalog exists here.')
add('0x1cf0','For unsigned64 count iterations, calls the supplied constructor function pointer on the current element, discards its void-pointer result and increments the element pointer by the supplied stride.',
    'Zero count does nothing. The stored indirect signature is default-managed void*(void*), token0x11000079. No overflow checks, null checks or EH rollback of already constructed elements; intended trusted array-construction contract, with no direct MethodDef caller found.')
add('0x31e0','Writes one zero WORD to the one-element unsigned-short BITFLAG storage and returns this.',
    'Exactly two bytes are written; this is not a global gameplay unlock operation.')
add('0x3380','Writes one zero WORD to the supplied BITFLAG storage.',
    'No range, owner or persistence validation; its body does not identify a gameplay flag target.')
add('0x4270','Calls native Axa.ScratchPad.Top at VA0x1402D61C0 and stores its returned pointer bits in static YW.SCRATCH_PAD (native field VA0x142B81010). The complete native body returns the fixed address0x142B047D0.',
    'This records a native scratch-memory base; it does not allocate or establish caller ownership. In the process initializer table it precedes the end-pointer initializer.')
add('0x4280','Reads static YW.SCRATCH_PAD, adds32768 with unchecked64-bit arithmetic and stores static YW.SCRATCH_PAD_END (native field VA0x142B81008).',
    'The resulting32KiB span is a recorded native convention, not a heap reservation or general allocation API. Requires prior base initialization.')
add('0xebf0','Forwards destination and source exception_ptr storage to native copy constructor VA0x140386170 and discards the returned destination pointer.',
    'Generated marshaling copy helper for a16-byte native exception_ptr, not a bytewise memcpy. Fresh native code calls0x14043AD16, whose PE-IAT import is MSVCP140.__ExceptionPtrCopy, then returns original RCX.')
add('0xec00','Forwards exception_ptr storage to native destructor VA0x14038C950.',
    'Generated marshaling destroy helper; fresh native code tail-jumps0x14043AD1C, whose PE-IAT import is MSVCP140.__ExceptionPtrDestroy. Cannot be used as a general exception reset on arbitrary bytes.')

table_refs=defaultdict(list)
for table in verify['initializerTables']:
    if table['kind']!='managed-method-tokens':continue
    for e in table['entries']:
        table_refs[e['method']['token']].append(dict(table=table['startField'],slot=e['slot'],rva=e['rva']))

findings=[]
for m in meta['methodBodies']:
    addr=m['idaSyntheticAddress']; b=bodies[addr];ins=[x['instruction'] for x in b['asm']['lines']]
    assert not selection[addr]['claims']
    field=None
    if 'pmField@' in m['name']:
        assert len(ins)==4 and ins[0].startswith('ldsflda ') and ins[1:]==['ldc.i4.8','stind.i4','ret']
        token=hex(int.from_bytes(bytes.fromhex(m['codeHex'])[1:5],'little'))
        field={**fields[token],**field_locations[token]}
        finding=f"Writes signed32 value8 into pointer-to-member FieldDef {token} ({field['name']}); returns without any other action. This records the byte offset of the corresponding VARIANT union member."
        limit='The target member-pointer type is four bytes in metadata. This is a layout constant, not a live VARIANT value, conversion routine or COM call. The parallel translation-unit body writes the same FieldDef; only the first set appears in the captured managed process initializer table.'
        family='VARIANT member-offset initializer'
    elif 'CTraceCategoryEx<' in m['name']:
        assert ins==['ldarg.0','ret'] and bytes.fromhex(m['codeHex'])==bytes([2,42])
        finding='Returns the incoming object pointer without reading fields, writing category bits, registering a logger or emitting output.'
        limit='The template mask in the symbol name is not executed. This specific retail constructor body cannot activate tracing; no full logging subsystem availability is inferred.'
        family='Empty trace-category constructor'
    else:
        assert addr in manual,(addr,m['name'])
        finding,limit=manual[addr];family='ATL / native interop / lifetime'
    callers=[dict(addr=e['callerSyntheticAddress'],token=e['caller']['token'],name=e['caller']['name'],ilOffset=e['ilOffset'],opcode=e['opcode'])
        for e in verify['incomingCallEdges'] if e['targetToken']==m['token']]
    row=dict(addr=addr,Domain='cil',Name=m['display'],MethodDef=m['token'],OriginalHeaderRva=m['headerRva'],
        CodeBytes=m['codeSize'],CodeSha256=m['codeSha256'],Family=family,Finding=finding,
        Evidence=['managed_tools_round6_evidence.json','managed_tools_round6_metadata.json','managed_tools_round6_cil_bytes.json','managed_tools_round6_verification.json','managed_tools_round6_deep_verification.json'],
        DirectCallers=callers,CallReferences=[e for e in meta['callEdges'] if e['cilAddress']==addr],
        InitializerTableReferences=table_refs[m['token']],
        ExceptionClauses=[e for e in verify['exceptionClauses'] if e['addr']==addr],
        Limitations='Synthetic CIL address, not a native RVA or process-call address. '+limit)
    if field:row['WrittenField']=field
    if addr in ['0x3d0','0x16e0','0x4270','0xebf0','0xec00']:row['Evidence'].append('managed_tools_round6_native_evidence.json')
    findings.append(row)
assert len(findings)==154 and len({f['addr'] for f in findings})==154
assert len(manual)==67, len(manual)
families=Counter(f['Family'] for f in findings)
groups=defaultdict(list)
for m in meta['methodBodies']:groups[m['codeSha256']].append(m['idaSyntheticAddress'])
report=dict(Date='2026-10-04',Status='All154 selected real CIL bodies read and original-byte verified; research only.',
    SourceSha256=meta['sourceSha256'],
    Scope='The previously unclaimed ATL/COM/window/scratchpad/compiler-helper bodies only. No existing285 CIL claims are repeated; six RVA0 declarations remain outside executable-body counts.',
    Counts=dict(cilBodies=154,fullIlInstructions=1356,originalIlBytes=2381,exceptionClauses=9,directMethodDefCallerEdges=91,outgoingCallOperands=94,nativeBoundaryBodies=5,nativeBoundaryBytes=52,
        familyCounts=dict(families)),
    AddressPolicy='addr in Findings is synthetic CIL. OriginalHeaderRva locates stored IL. Explicit nativeVa/VA fields identify native image addresses. Never add imagebase to a synthetic CIL address.',
    Findings=findings,
    BodylessDeclarations=meta['bodylessImports'],
    DuplicateByteGroups=[dict(codeSha256=h,addresses=a) for h,a in groups.items() if len(a)>1],
    Validation='Each original IL byte stream was independently walked using the installed System.Reflection.Emit opcode table without loading the target assembly. All opcode names, instruction boundaries, call tokens, branch targets and EH boundaries match fresh complete IDA IL. Five complete native bodies match original PE bytes; three import thunk destinations were resolved from original import descriptors.',
    Conclusions=[
        'The remaining real bodies contain no additional model/texture/animation editor UI or safe new user command. Their value is precise interop, initialization and teardown documentation.',
        '64 VARIANT member-offset initializer bodies form 32 byte-identical translation-unit pairs writing the same 32 FieldDefs. Only the first set is in the managed process initializer table. Separate bodies remain separately documented without claiming 64 distinct tools.',
        'All 23 remaining trace-category constructors are exactly ldarg.0;ret. The symbol masks do not imply a working retail trace toggle.',
        'All 9 exception clauses in this round have flags 4 (fault). Treating the IL endfinally instruction as proof of a normal finally path would misstate cleanup behavior.',
        'Window-module Term has a size 0 completion guard, clears its atom list, deletes the lock and ignores class-unregistration errors. The empty base lock destructor is not an equivalent cleanup path.',
        'Array indexing has signed index/count guards and raises noncontinuable bounds failure, while compiler vector helpers trust allocation cookies/strides. These are different contracts and should not be exposed to arbitrary trainer input.',
        'Known string-wrapper callers connect to previously analyzed asset tools; the wrappers add no length bounds or safe offline scanning behavior.'
    ],
    PotentialMisuse=[
        dict(addresses=['0x760','0xa20'],issue='Attaching over a nonempty wrapper drops the prior owned handle without closing it.',classification='Verified API precondition; no caller violation demonstrated.'),
        dict(addresses=['0x460','0xb80','0xbc0'],issue='COM Release helpers retain stale pointer bits in wrapper storage.',classification='Expected destructor contract; repeated arbitrary invocation is unsafe, not proven ordinary game double-release.'),
        dict(addresses=['0x16e0','0x1cf0'],issue='Trusted count/stride/cookie arithmetic has no overflow guard, and generic __vec_ctor has no unwind cleanup.',classification='Compiler-helper preconditions; no untrusted-input path or exploitable game defect established.'),
        dict(addresses=['0xa40'],issue='UnregisterClassA failures are ignored before the atom list and lock are discarded.',classification='Observable error-reporting limitation at teardown; no observed leaked live window or crash.'),
        dict(addresses=['0x3b0','0x3c0'],issue='Zeroed lock storage plus an empty destructor does not supply OS initialization/termination.',classification='Lifecycle distinction important to modded callers; actual Init/Term are separate bodies.')
    ],
    PracticalUse=dict(recommendation='Keep these records as an offline mixed-mode ABI/lifetime reference. No new trainer action is justified by these remaining bodies.',
        activation='No live activation contract. Do not manually rerun module constructors, atexit registration, window/COM teardown or compiler delete helpers.',
        optionalOfflineTool='An evidence viewer could show a MethodDef token, synthetic CIL address, original header RVA, complete IL, decoded fault regions, native-call edges and whether an initializer table references it. This is a documentation proposal only, not implemented or required for an existing asset feature.'),
    Limits=[
        'Each claim is the specific behavior of a read body; reaching a claim for every known CIL body would not establish complete semantics of the binary or every existing claim.',
        'Direct MethodDef-token calls and managed initializer tables were enumerated. Native-to-managed stubs, reflection, runtime delegates and arbitrary external callers are not an exhaustive reachability proof.',
        'No original/game/save/UI/product/package changes, runtime tests, debug-tool execution or IDB mutations occurred.',
        'Original PE byte equality and full IDA cursor counts verify captured material, not runtime object ownership or all imported API implementation semantics.'
    ])
(P/'managed_tools_round6_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
lines=['CIL-Runde6 — verbleibende ATL-/COM-/Laufzeitkörper',
    '=================================================',
    'Stand: 2026-10-04. Ausschließlich statische Forschung; Trainer 0.10 unverändert.',
    '',
    'Ergebnis',
    '--------',
    'Die 154 zuvor unbeanspruchten echten CIL-Körper wurden vollständig gelesen:',
    '1.356 IL-Instruktionen, 2.381 Original-Codebytes, 9 Fault-Klauseln. Zusätzlich',
    'sind 91 eingehende MethodDef-Verweise und 94 ausgehende direkte/indirekte',
    'Aufrufoperanden dokumentiert. Sechs RVA0-Deklarationen sind ausgeschlossen.',
    '',
    'Die Gruppe enthält 67 ATL-/Interop-/Lifetime-Helfer, 64 VARIANT-Initializer',
    '(32 bytegleiche Paare) und 23 leere Trace-Konstruktoren. Es ist keine weitere',
    'benutzbare Modell-, Animations- oder Textur-Editor-Oberfläche enthalten.',
    '',
    'Wichtigste Präzisierungen',
    '------------------------',
    '* Alle 23 CTraceCategoryEx-Konstruktoren bestehen nur aus ldarg.0;ret.',
    '  Ihre Namen und Masken begründen keinen aktivierbaren Logging-Schalter.',
    '* Der native EntryTex-Listen-Destruktor 0x140129B60 schreibt nur seine VTable.',
    '  Er entfernt keine Texturen. Der CIL-Delete-Helfer erwartet originale',
    '  Arraycookies und 32-Byte-Elemente; er ist kein Cache-Leeren-Befehl.',
    '* CComQIPtr-Kopie ruft AddRef, nicht QueryInterface. Release-Helfer lassen',
    '  Pointerbits stehen. CHandle/CRegKey-Kopien übertragen Besitz und leeren',
    '  die Quelle; Attach schließt keinen vorherigen Handle.',
    '* BSTR.Copy verwendet eine Byte-Länge, erhält damit eingebettete Nullbytes',
    '  und führt keine Zeichenkonvertierung aus. VARIANT-Fehlerpfade setzen',
    '  Typ 10/Error bei +8 und werfen teilweise C++-Exceptions statt HRESULTs.',
    '* Fenster-Modulgröße 72 beziehungsweise 0 trennt gültigen Zustand und',
    '  abgeschlossenen/fehlgeschlagenen Zustand. Term leert die Atomliste und',
    '  löscht die OS-Sperre; deren Basisklassen-Destruktor ist selbst leer.',
    '* Die 9 EH-Klauseln sind ausdrücklich Fault, keine normalen Finally-Blöcke.',
    '* ScratchPad.Top liefert den festen Speicheranfang 0x142B047D0. Die zwei',
    '  CIL-Initializer speichern Anfang und Anfang+32768; sie reservieren nichts.',
    '* exception_ptr-MarshalCopy/Destroy delegieren über belegte Importthunks an',
    '  MSVCP140.__ExceptionPtrCopy/Destroy, nicht an eine rohe Speicherkopie.',
    '',
    'Fehler und Grenzen',
    '------------------',
    'Bestätigt sind harte Aufrufvoraussetzungen, kein neuer demonstrierter',
    'Spielabsturz: Attach über einem belegten Handle verliert dessen Besitz;',
    'Delete-/Vector-Helfer vertrauen Cookies, Stride und ungeprüfter Arithmetik;',
    'Fensterklassen-Term ignoriert UnregisterClassA-Fehler. Kein tatsächlich',
    'verletzender Spielpfad oder kontrollierbarer Eingabepfad wurde festgestellt.',
    '',
    'Die direkten MethodDef-Aufrufe und Initializer-Tabellen sind keine',
    'vollständige Laufzeit-Erreichbarkeitsanalyse. Nur der erste Satz der 32',
    'VARIANT-Initializer und der ATL-Initialisierer steht in der erfassten',
    'Prozess-Tabelle. Andere Wege zur zweiten Übersetzungseinheit bleiben offen.',
    '',
    'Adressen und Prüfung',
    '--------------------',
    'Die nachstehenden kleinen CIL-Adressen sind synthetisch. Header-RVA benennt',
    'gespeichertes IL in der PE, keine direkt aufrufbare x64-Funktion. Nur explizit',
    'als native VA bezeichnete Adressen sind native Imageadressen.',
    '',
    'Vollständige Cursor-/Zeilenzahlen und IDA-Bytes wurden frisch gelesen.',
    'Ein separater Decoder mit der lokalen .NET-Opcode-Tabelle prüft sämtliche',
    'Instruktionsgrenzen, Operanden, Verzweigungen und EH-Grenzen. Die Ziel-Assembly',
    'wurde dazu nicht geladen. Fünf native Grenzfunktionen / 52 Bytes sind ebenfalls',
    'originalgleich; drei Importziele wurden anhand der PE-IAT aufgelöst.',
    '',
    'Nutzung',
    '-------',
    'Diese Runde ergänzt eine belastbare Offline-Referenz für Modder: Token→IL,',
    'Fault-Regionen, native Übergänge und Initializer-Herkunft. Ein optionaler',
    'Metadaten-/IL-Betrachter könnte diese vorhandenen Datensätze anzeigen.',
    'Es gibt keinen begründeten neuen Trainerknopf. Modul-Initialisierung,',
    'atexit-Registrierung und native Teardown-Helfer werden nicht manuell gestartet.',
    '',
    'Einzelbefunde (englischer auditierbarer Originaltext)',
    '--------------------------------------------------']
for f in findings:
    lines += ['',f"CIL {f['addr']} | {f['Name']}",f"MethodDef {f['MethodDef']} | original header RVA {f['OriginalHeaderRva']} | {f['CodeBytes']} IL bytes",
        f['Finding'],'Limit: '+f['Limitations']]
lines += ['', 'Neue Claims: 154. Das beseitigt die ausgewählte CIL-Inventarlücke, beweist aber',
    'keine vollständige Semantik aller älteren Claims oder der gesamten EXE.',
    'Kein Produkt-/Paket-/Spiel-/Save-/UI-Zugriff, keine Builds oder IDB-Mutationen.']
(P/'managed_tools_round6_report.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(dict(claims=len(findings),families=dict(families),manual=len(manual),byteDuplicateGroups=len(report['DuplicateByteGroups'])),indent=2))
