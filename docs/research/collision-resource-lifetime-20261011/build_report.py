"""Write bounded claims; raw captures remain untouched."""
import hashlib,json
from pathlib import Path
H=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
def dump(name,value):(H/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
e=read(H/'evidence.json');by={f['addr']:f for f in e['functions']}
claims=[]
def claim(rva,finding,limitations,related=()):
    addr=hex(0x140000000+int(rva,16));assert addr in by
    claims.append({'addr':addr,'Finding':finding,'Evidence':[f'evidence.json#functions[addr={a}]' for a in [addr,*[hex(0x140000000+int(x,16)) for x in related]]], 'Limitations':limitations})
claim('1613C0','After obtaining a BAR owner at39CC40 and calling160DE0, stores the owner at map+64. If BAR type6 is present, it decodes entry+8 and stores the borrowed payload at map+104. The later wrapper path receives this payload through161320.',
      'Only the selected type6 branch and immediate caller chain are claimed. Other BAR entries, reset-helper semantics and all resource-cache lifetimes are not established.', ['161320','16FFA0'])
claim('161320','Returns the QWORD at map+104 directly; there is no local acquisition, span validation or retained reference.',
      'A pointer getter alone does not establish allocation ownership or the payload length.')
claim('1722F0','Initializes a248-byte collision context using the supplied resource pointer. Table addresses come from sign-extended DWORD offsets at24,32,40,48,56,64,72; corresponding byte lengths are sign-extended to64 bits, divided using unsigned arithmetic by32,20,16,16,16,12,4, then narrowed toDWORD counts. When the narrowed leaf count is positive as signed32, it clears byte+16 for each entry in that count in the shared20-byte leaf table and sets it for selected mask bits whose group ID equals leaf byte+17. The loop considers groups0..63. No private copy of the resource tables is allocated here.',
      'The selected instruction model covers the straight-line header bindings, not matrix helpers or the entire constructor. Native code does not receive a payload length. Negative or overflowing fields in synthetic cases do not prove malformed retail reachability. Shared-buffer interference is conditional on two contexts receiving the same resource.')
claim('16FFA0','For a nonnull map+104 payload, allocates248 bytes, calls1722F0 with the caller mask, publishes the resulting context in ABD448 and immediately calls172A30. It also constructs four other248-byte wrappers for separate optional map resources. If the first allocation returnsNULL, the selected branch still publishesNULL and reaches172A30.',
      'This identifies local construction and failure ordering. It does not establish ordinary allocation failure reachability, global scene synchronization or all resource owners.', ['1722F0','172A30'])
claim('172A30','Walks the signed-positive polygon count at context+72 in16-byte strides, indexes the DWORD attribute table at context+40 with polygon WORD+14 and registers polygons whose attribute bits17..18 are nonzero through189B60.',
      'There is no local attribute-index capacity check in this body. Registration-helper lifetime and all polygon semantics remain outside this claim.')
claim('1E7D30','Loads the map through1613C0 and calls162240 with R9D=FFFFFFFF, which zero-extends to the64-bit mask00000000FFFFFFFF.162240 forwards that mask to16FFA0;1722F0 therefore considers only lower32 set groups on this captured path.',
      'The constructor supports a64-bit mask; this concrete caller supplies32 set bits. Other callers and all gameplay conditions are not generalized.', ['162240','16FFA0','1722F0'])
claim('170340','Calls189BC0 and1717D0 before freeing global contexts ABD468,ABD460,ABD458,ABD450, then releasing/freeing ABD478, freeing ABD448 and finally invoking186670/free for ABD440. Each selected nonnull global is cleared after its release/free call.',
      'These are ordinary-return local ordering guarantees. The raw248-byte wrapper frees do not themselves release the borrowed BAR payload, drain every collision node, or prove no external borrower remains.', ['1717D0'])
claim('162420','Conditionally tears down the ABCC08 object when its active flag and2C4620 predicate permit, clears ABCBD0, then calls170340 for collision-wrapper cleanup.',
      'No whole-scene lifetime or synchronization guarantee follows from this wrapper.', ['170340'])
claim('1E7CA0','When AEA100 is nonnull, first calls162420, then161240 on map AE9700, and finally clears AEA100. Thus this path removes collision wrappers before releasing the map resource-cache reference.',
      'All callees must return normally. This ordering does not prove that other outstanding Actor, query or worker borrows have completed.', ['162420','161240'])
claim('161240','Releases and aligned-frees map+72 when nonnull and clears that field; then tail-calls39DA10 with map+64. It does not clear map+64 or collision payload fields in this body.',
      'The tail target decrements a cache reference; it is not an unconditional immediate free of the original map BAR.', ['39DA10'])
claim('39DA10','Traverses the encoded resource-cache list until entry+88 matches the supplied BAR, then addsFFFF to WORD entry+2. If traversal finds no entry, the captured terminal path still attempts the same WORD write through the null result.',
      'This is a narrow local release-helper contract; callers must supply an owned matching cache entry. No atomic reference counting, fault recovery or all-cache teardown behavior is established.')
claim('163C20','Clears moving-list head/tail, allocates2248 bytes for80 records of24 bytes followed by80 DWORD free indices and aDWORD free count. Initializes node IDs/context pointers/flags, writes indices0..79, sets count80 and publishes ABCCD0; a failed allocation publishesNULL.',
      'Not every record byte is initialized. This constructor does not establish all ownership, allocation-success or concurrent-access prerequisites.')
claim('1639B0','Pops the last free index by decrementing the pool count before allocating the248-byte context, initializes that node, calls1722F0 with all64 mask bits, and appends the node to the encoded moving list. The append also occurs when allocation returnsNULL and node+8 remainsNULL.',
      'No local free-count or successful-context predicate is present. This is a caller contract, not evidence that normal gameplay reaches an exhausted/failed allocation.', ['163C20','1722F0'])
claim('164120','Initializes a caller-supplied24-byte moving node, allocates its248-byte context with an all64 mask and appends it to the same ABCCC0/ABCCC8 list used by the pool allocator.',
      'The shared list can contain caller-supplied nodes. This does not prove those nodes may be passed to the pool-return function163A90.', ['1722F0'])
claim('163A90','Unlinks the supplied moving node, fixes the tail, clears its encoded next link, frees and clears node+8, computes its index relative to ABCCD0 using24-byte records and pushes that index back onto the free stack.',
      'Requires a current linked pool node. The local predecessor walk is unbounded and has no null/cycle check; no range/capacity validation protects the returned pool index.', ['163C20','1639B0'])
claim('163BE0','Frees the ABCCD0 pool when nonnull and clears only that global in this body. There is no traversal or clearing of ABCCC0/ABCCC8 here.',
      'A surrounding teardown may establish additional ordering. This body alone is not proof that every moving node/context was individually retired.')
claim('163B90','Starts at ABCCC0 for aNULL argument or advances via the supplied node\'s encoded next field, then skips nodes whose flagDWORD+16 contains mask2.',
      'Returns a borrowed raw node; it acquires no reference and performs no cycle, generation or resource-span validation.')
claim('163FC0','Initializes the output node toNULL and polygonWORD toFFFF, walks the moving list, filters flag2/identity/predicate173EF0, changes each tested context\'s shared filters through1745C0 and calls173B30. Every accepted result overwrites the output point, overwrites the mutable segment endpoint with that returned point and stores the borrowed node.',
      'Only the immediate call/write ordering is claimed. This is not a pure query, retained result, universal hit-validity guarantee or proof that every later node remains valid.')
dump('claims.json',{'schema':1,'Domain':'native','claims':claims,'completeSemanticReview':False})
verification=read(H/'verification.json')
dump('summary.json',{'schema':1,'status':'AUTHOR_VERIFIED_PENDING_INDEPENDENT_REVIEW','claims':len(claims),
     'freshCompleteCaptures':len(by),'bytes':verification['originalBytes'],'instructions':verification['instructions'],
     'note':'Fresh captures include revisited legacy functions; these counts are not new unique semantic coverage.',
     'productChanged':False,'gameExecuted':False,'idbModified':False,
     'next':['Validate geometry spans and hierarchy topology before any collision query wrapper.',
             'Bind resource lifetime and context revisions before retaining collision results or integrating scale cleanup.',
             'Use current native scene lifecycle and caller ownership; do not infer it from a nonnull pointer.']})
print(f'Wrote {len(claims)} bounded claims for {len(by)} captured bodies.')
