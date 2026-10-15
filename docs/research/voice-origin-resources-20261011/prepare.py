"""Author bounded findings and fixed instruction anchors from verified original bytes."""
import json, hashlib
from pathlib import Path
import verify
HERE=Path(__file__).resolve().parent
def save(n,x): (HERE/n).write_bytes(verify.encoded(x))
pe,functions,data,ins,listing,gaps=verify.build()
anchors={
 '14036daf7':'Producer reads original SeBlock WORD metadata through 1E0D70.',
 '14036db0f':'Producer stores extracted metadata at ORIGIN+12.',
 '14036db4e':'VAG/IopVoice producer stores zero at ORIGIN+12.',
 '14036db65':'Producer clears the third 16-byte block before filename copy.',
 '14036db85':'Producer copies extension-stripped name with computed, unchecked count.',
 '14036db9a':'Producer emits a 48-byte wrapper.',
 '14036e486':'Importer opens original path for write.',
 '14036e572':'Importer calls the ORIGIN producer.',
 '1401e0dad':'ORIGIN metadata reader reads DWORD+12.',
 '1401e0e5b':'SEDBSSCF reader reads unsigned WORD+54.',
 '1401e0e6a':'Other formats reader sign-extends WORD+8.',
 '1403a6519':'Already-decoded BAR+8 bypasses prepare.',
 '1403a65eb':'Prepare reads entry type WORD.',
 '1403a65fc':'Prepare maps type through 48-byte selector table.',
 '1403a6674':'Replacement-disabled gate.',
 '1403a673a':'Formats basename.win32.scd.',
 '1403a6757':'Package mode3 selects embedded name instead.',
 '1403a6763':'Lookup of already-loaded replacement by exact name.',
 '1403a676f':'Load replacement payload QWORD+96.',
 '1403a6773':'Store ORIGIN payload QWORD+32.',
 '1403a6777':'Load replacement DWORD+80.',
 '1403a677a':'Store ORIGIN payload-size DWORD+40.',
 '1403a677d':'Successful lookup terminates name at wrapper+31.',
 '1403a6782':'Missing replacement clears payload pointer.',
 '1403a6786':'Missing replacement clears payload size.',
 '14012db50':'ResourceEntry replacement-list head is QWORD+1648.',
 '14012db88':'Exact byte comparison of requested and stored names.',
 '14012d13f':'Constructor stores replacement size at+80.',
 '14012d143':'Constructor stores owned replacement allocation at+96.',
 '14012cd5a':'Alternate constructor retains supplied replacement size.',
 '14012cd5e':'Alternate constructor retains supplied replacement pointer.',
 '1403a0d76':'Worker prepares the BAR before status2 publication.',
 '1403a0d7b':'Worker writes status2 after prepare returns.',
 '1403daa88':'BTLOBJ constructor selects BAR type34.',
 '1403daac4':'VOICE_EE stores decoded BAR payload as component+32.',
 '1403daad5':'Actor+2996 binding publication.',
 '1403ce560':'VOICE_EE forwards component+32 resource.',
 '1401de2f6':'Request retains the resource QWORD at+24.',
 '1401dfdc5':'ORIGIN Start reads payload+32.',
 '1401dfdcc':'Null payload returns before key overwrite/registration.',
 '1401dfdd2':'ORIGIN Start overwrites DWORD+12 with low32 payload.',
 '1401dfdd7':'ORIGIN Start invalidates previous bank for key/group2.',
 '1401dfe25':'Start supplies registration mode2.',
 '14013b3ce':'BankEntry retains supplied payload QWORD+88.',
 '14013b3d9':'BankEntry stores registration mode DWORD+112.',
 '14013b3de':'Any nonzero mode selects synchronous path.',
 '14013b410':'Synchronous registration passes payload to078810.',
 '14013b427':'Bank-existence query result is ignored.',
 '14013c279':'Mode0 transfer allocates a replacement buffer.',
 '14013c29d':'Transfer copies payload before lower registration.',
 '14013643e':'Invalidator compares matching SoundRecord group.',
 '1401364d0':'Invalidator marks matching BankEntry key asFFFF.',
 '14013c5b0':'Bank collector recognizes DWORD FFFF marker.',
 '14013c5bc':'Collector additionally queries lower bank retirement predicate.',
 '14013c626':'Collector calls selected bank deleting destructor.',
 '1401360a5':'Deleting destructor can wait for transfer completion.',
 '1401360fd':'Mode2 bypasses payload free and pointer clearing.',
 '140136108':'Other modes free the retained bank payload.',
 '1403a6acf':'Release uses a different 48-byte type selector.',
 '1403a6b45':'BAR cleanup reads ORIGIN DWORD+12.',
 '1403a6b4b':'Zero ORIGIN key skips bank invalidation.',
 '1403a6b52':'BAR cleanup invalidates matching bank before owner release.',
 '1403a6bb5':'BAR cleanup retires ResourceEntry after per-entry cleanup.',
 '14012e58c':'ResourceEntry retirement invokes deleting virtual target.',
 '14012d987':'ResourceEntry destructor invokes replacement deleting target.',
 '140129d52':'ReplaceEntry frees retained payload through aligned_free.',
 '140129d58':'ReplaceEntry clears only its own payload pointer.',
 '1401de43b':'Bulk EE stop invalidates ORIGIN key after request stop.',
 '1401de639':'Resource-selected EE stop invalidates matching ORIGIN key.',
 '1400894d2':'ActualBank stores supplied payload as base+8.',
 '14008951d':'ActualBank starts with alternate sequence storage NULL.',
 '140089528':'Constructed runtime type is ActualBank.',
 '1400896a9':'Driver invokes concrete ActualBank initialization vtable+16.',
 '14009fbf3':'ActualBank reads a WORD header displacement from payload+14.',
 '14009fc6f':'Sequence table displacement is retained at bank+136.',
 '14009fc97':'Initializer sets alternate sequence storage to NULL.',
 '14009fcad':'Flag8 skips sequence marker writes.',
 '14009fcc8':'Initializer resolves each sequence via vtable+24.',
 '14009fccd':'Initializer writes FF to sequence+15 in supplied payload.',
 '14009fd39':'Sequence helper compares signed index against zero-extended count.',
 '14009fd9a':'Sequence offsets are signed DWORDs in supplied payload.',
 '14009fd9e':'Resolved sequence pointer is payload base plus signed offset.',
 '140089012':'Driver-handle lookup checks recorded handle as well as list membership.',
 '1400889f9':'Bucket initializer starts at first bucket+16.',
 '140088a3a':'Each bucket node offset is initialized to104.',
 '140088dce':'Last unrolled node-offset store for the group of32 buckets.',
 '140088dd9':'Initializer advances to the next32 buckets.',
 '140088de2':'Initializer repeats until all64 buckets are initialized.',
 '1400913a6':'SoundDriver constructor calls the bucket initializer.',
 '14008c1e3':'Insertion reads node offset from the selected bucket+24.',
 '14008c1f4':'Insertion stores bucket owner at node+16.',
 '14008c202':'Insertion clears node next+8.',
 '14008c20e':'Insertion links previous tail through the same node offset.'
}
fixed=[]
for text,note in anchors.items():
 a=int(text,16);i=ins[a]
 fixed.append(dict(addr=hex(a),bytes=i.bytes.hex(),mnemonic=i.mnemonic,operands=i.op_str,meaning=note))
save('anchors.json',fixed)

claims=[]
def claim(a,text,also=(),limits='Valid memory, intact metadata/lists, sequential calls and normal external returns are assumed. No complete all-writers, concurrency, exception or runtime reachability proof.'):
 if isinstance(also,str):also=(also,)
 addrs=[a,*also]
 assert all(any(verify.num(f['addr'])==verify.num(x) for f in functions) for x in addrs)
 claims.append(dict(addr=a,Finding=text,Evidence=[f'evidence.json#functions[addr={x}]' for x in addrs]+['verification.json'],Limitations=limits))
claim('0x14036d8b0','A concrete serializer produces 48-byte ORIGIN wrappers for selected BAR types31/34/48 when a matching replacement-list record exists. For SeBlock it writes the result of1E0D70 at+12; for VAG/IopVoice matches it writes zero. It clears bytes16..47 before copying the replacement name without its final extension. This is a file-import producer, not proof that a particular runtime resource was generated by it.',('0x1401e0d70','0x14036e230'), 'The name copy uses the last-dot displacement without a local capacity check. Payload+32/+40 are zero only if the copied name does not reach those bytes; do not claim all produced wrappers are initialized to zero. Input size, slash/dot presence and valid C strings are external preconditions. The importer was not invoked.')
claim('0x1401e0d70','The metadata accessor reads ORIGIN DWORD+12 through optional endian conversion, SEDBSSCF unsigned WORD+54, or signed WORD+8 for the other branch. Start1DFD70 later overwrites the ORIGIN field with a pointer-derived bank key. Its meaning is phase-dependent; it is not an immutable sound-count or stable resource ID.',('0x1401dfd70'), 'Only the non-ORIGIN SeBlock input branch is needed to explain the serializer. The generic endian helper and all format semantics are not expanded here.')
claim('0x1403a64f0','BAR preparation handles sound types31/34/48 only when entry size is nonzero, alias-bit0 is clear, the BAR is unresolved, replacement-disable global79CFD0 is zero and the first seven bytes equal ORIGIN including NUL. Matching ReplaceEntry+96 and+80 become wrapper+32 and+40. A successful lookup clears byte+31; a missing lookup nulls+32/+40. This path does not rewrite ORIGIN+12.',('0x14012db50'), 'This pass uses relative BAR offsets before relocation. Filename construction and recursive containers still require valid input. The disabled/already-resolved/alias paths retain prior bytes rather than clearing fields. No global writer exclusion is claimed.')
claim('0x14012db50','The replacement lookup walks ResourceEntry+1648 and next+8 and returns the first exact NUL-terminated name match at entry+16. It does not load a file, retain a reference or validate payload size/signature. Mode3 chooses the embedded wrapper name, while other modes construct basename.win32.scd before this lookup.',('0x1403a64f0'), 'A filename match is not a resource-generation or payload-validity proof. The directory arguments are unused in this captured implementation.')
claim('0x14012cd80','The ResourceEntry constructor retains replacement allocations in objects whose native vtable is ReplaceEntry; payload QWORD+96 and length DWORD+80 later feed ORIGIN preparation. The constructor also has region rejection paths that call aligned_free. The alternate12CD00 constructor stores the full R8 payload pointer, despite its misleading inferred pseudocode parameter widths.',('0x14012cd00','0x1403a64f0'), 'Primary storage and replacement allocations have different lifetimes. This is not complete provider selection, allocation failure, exception cleanup or filesystem stability analysis; existing provider studies cover related paths.')
claim('0x1403a0c60','The selected resource worker calls BAR preparation for request kind1 with nonzero load result at request+80, then writes request status2. ORIGIN population is therefore visible before that publication on this normal path.',('0x1403a64f0'), 'This establishes local instruction order only. It does not prove memory-order synchronization, task ownership, every consumer path or successful native loading.')
claim('0x1403da940','The selected constructor takes BAR type34 from Actor+2344, decodes its entry data pointer into embedded VOICE_EE+32 and binds Actor+2996. VOICE_EE3CE560 forwards this wrapper pointer, and EE request admission retains that same pointer at request+24. These stores do not acquire a distinct resource lease or copy the payload.',('0x1403a6420','0x1403ce560','0x1401de230'), 'The previously selected N_EX650_BTL10 row may leave Actor+2344 and the Voice binding absent; this study does not establish an actual bound BTLNPC instance. Any transitive or external resource retention remains open.')
claim('0x1401dfd70','For an ORIGIN wrapper, Start requires a nonzero payload+32, writes its low32 bits to wrapper+12 and uses that key with group2. It invalidates matching older banks, registers the payload with mode2, then attempts creation/play. Distinct64-bit payload pointers can have equal low32 keys. A nonzero pointer with low32 zero still proceeds here, whereas BAR release skips key0.',('0x1403a6a10'), 'The alias and zero-key cases are arithmetic possibilities, not observed retail allocations or live failures. Registration and creation return values remain unchecked in this adapter.')
claim('0x14013b2e0','BankEntry retains payload+88, length+84, key+72, group+76 and mode+112. Nonzero mode selects synchronous registration, including Voice mode2. Mode0 instead schedules13C250, which allocates and copies the payload before lower registration. The synchronous07DEC0 call only checks lower bank lookup and its result is discarded.',('0x14013c250','0x14007dec0','0x140088fc0'), 'Captured explicit rejection gates are absent sound-system global, wrong SEDBSSCF signature and insufficient bank capacity. Size validation, lower parse success, async lifetime and exception/allocator failure are not established.')
claim('0x1401363b0','Invalidation scans banks matching key and group; it stops/unlinks/destroys matching SoundRecords and sets each matching BankEntry key to DWORD0xFFFF. It does not directly unlink or destroy those BankEntry objects. The later13C470 bank pass requires this marker and078BE0 success before unlinking and invoking the deleting destructor.',('0x14013c470','0x140078be0'), 'The collector also processes other audio lists whose complete behavior is outside this claim. Lower driver predicates and virtual targets may have further effects. Invalidation is not a guarantee that all payload use has ended.')
claim('0x140136060','The selected BankEntry deleting destructor waits on transfer state+108, issues lower bank-release operations, and skips both aligned_free(payload+88) and clearing that pointer when mode+112 equals2. Other modes reach that free/clear block after the waits. Voice mode2 therefore does not transfer the replacement allocation to this destructor.',('0x14013b2e0','0x140078b50','0x14007d3f0'), 'Wait termination is not proven. This is a local allocation responsibility conclusion; it does not establish every lower driver resource lifetime or safe simultaneous teardown.')
claim('0x1403a6a10','Normal BAR cleanup includes ORIGIN bank invalidation for types34/48, but not type31. It reads wrapper+12 and skips invalidation when that key is zero. After the entry pass it retires the associated ResourceEntry and clears the BAR association. The wrapper+32/+40 fields are not cleared in these selected cleanup bodies.',('0x14012e460','0x14012d8e0','0x140129d30'), 'BAR flag0x40 takes a separate external cleanup path; aliases and the early pointer-order break can bypass per-entry cleanup. The absence of wrapper clearing is restricted to selected bodies, not all callbacks or writers.')
claim('0x14012e460','ResourceEntry retirement may invoke a registered callback, removes the entry from its list and calls its deleting virtual target. The native ResourceEntry vtable resolves to12D8E0; its replacement entries resolve to129D30, which aligned_frees payload+96 and clears that field. This is the concrete release of the allocation borrowed by ORIGIN+32.',('0x14012d8e0','0x140129d30'), 'The callback and replacement-name-table writer can have side effects. No all-path timing relationship with Actor destruction or bank retirement is established. The primary BAR storage is not freed by this selected replacement destructor.')
claim('0x1401de3d0','Bulk EE stop walks type6 requests, stops each and invalidates the resource-derived ORIGIN key. The selected-resource variant1DE5C0 additionally requires request+24 equal its supplied wrapper pointer. Neither path clears wrapper+32/+40 or frees the replacement payload in the captured bodies.',('0x1401de5c0','0x1401de320'), 'These cleanup helpers mark requests for later retirement. Exact callers, invocation order, queued-request lifetime and lower Stop behavior beyond the pinned prior study remain open.')
claim('0x140089390','The default SoundDriver registration constructs ActualBank with the supplied SCD pointer stored at+8, alternate sequence storage+40 initiallyNULL, and vtable61C9F0. The concrete vtable+16 call reaches09FBD0. This path does not copy the SCD into a separate owned buffer before initialization.',('0x140078810','0x14009fbd0'), 'Driver replacement by a different vtable takes another path. Pool validity, all failure cleanup and concurrent ownership are not established.')
claim('0x14009fbd0','ActualBank initialization reads header offsets and counts from the retained SCD. With flag+128 bit3 clear and nonzero sequence count, it calls concrete09FD20 for each index and writes byte+15=0xFF to the returned sequence. If the64 bucket offsets initialized by0889B0 remain104 and all bank/list objects are intact and nonoverlapping,08C1A0 writes only bank+104/+112/+120 and previous-bank+112. It then preserves payload+8, NULL alternate storage+40, vtable, flags and sequence count. Under those explicit premises09FD20 resolves payload base plus a signed DWORD offset, so the subsequent sequence marker writes target the supplied replacement payload.',('0x14009fd20','0x14008c1a0','0x140089390','0x1400889b0','0x140091250'), 'No local overall payload-length check protects these indexed accesses. Valid writable SCD structure, unchanged initialized bucket offsets and intact/nonoverlapping bank objects are explicit premises. Uninitialized or changed bucket offsets can invalidate the +8/+40 preservation argument. No all-writers exclusion, general runtime guarantee or observed crash is claimed.')
claim('0x14009fd20','The sequence accessor uses signed index<count comparison and defaults an index at/above count to zero. Negative indices satisfy that comparison and are sign-extended for addressing; there is no lower-bound check here. The initializer supplies indices from zero to count-1, so this specific caller does not introduce negative indices.',('0x14009fbd0'), 'This is a bounded helper contract, not evidence of an exploitable or reachable negative-index call.')
claim('0x1400889b0','The SoundDriver constructor091250 calls0889B0. Its two passes of32 unrolled stores initialize64 buckets starting at2B81340, stride32, setting each bucket+24 node offset to104. In08C1A0 this offset locates the24-byte intrusive node at bank+104..127, separate from bank vtable+0, payload+8, alternate sequence storage+40, flags+128 and sequence count+152. This is a concrete initializer witness, not proof that its state cannot later change.',('0x140091250','0x14008c1a0'), 'The claim requires the initializer to have completed and the selected bucket offset to remain104. Other later or indirect writers and concurrent mutation are not excluded. An invalid previous-bank pointer can also invalidate the nonoverlap argument.')
save('claims.json',claims)
pins=[]
for relative in ['docs/research/voice-request-lifecycle-20261008/manifest.json','docs/research/voice-request-lifecycle-20261008/report.json','docs/research/timer-audience-operation-20261008/manifest.json','docs/research/timer-audience-operation-20261008/retail-witnesses.json','docs/research/drive-provider-binding-20261007/report.json','docs/research/actor-free-closure-20261008/report.json']:
 p=verify.ROOT/relative;pins.append(dict(path=relative,sha256=verify.digest(p.read_bytes())))
save('provenance.json',dict(schema=1,originalSha256=verify.SHA,files=pins,reuse='Previous claims/witnesses are context only; all42 selected native bodies were freshly captured through IDA on2026-10-11. No game code or importer was run.'))
print(json.dumps({'claims':len(claims),'anchors':len(fixed)},ensure_ascii=True))
