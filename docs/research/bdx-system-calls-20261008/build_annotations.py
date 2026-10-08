"""Emit reviewed descriptive labels; never modifies product/catalog sources."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
descriptors={d['index']:d for d in json.loads((HERE/'ida-capture.json').read_text())['selectedDescriptors']}
annotations={}
def add(index,name,summary,notes,helpers):
    d=descriptors[index]
    evidence='bdx-system-calls-20261008/evidence.json#functions[addr='+d['addr']+']; helpers '+', '.join('RVA 0x'+h.upper() for h in helpers.split())+'; bdx-system-calls-20261008/report.txt'
    annotations['0:'+str(index)]={'bank':0,'index':index,'name':name,'summary':summary,'notes':notes,'evidence':evidence,'declaredOperandCount':d['flags']&0xffff,'hasReturnSlot':bool(d['flags']&0x40000000),'helperRvas':helpers.split()}

add(9,'Create child VM context',
    'Creates a child of the current VM context and returns its encoded address as @ADR. Operand 0 is stored as the child mask; when nonzero, existing children satisfying (childMask & operand0) == operand0 are first destroyed. Operand 1 initializes the child PC. Nonzero operand 2 replaces its exit-PC field at +64. Non-NULL decoded operand 3 causes that tagged value to be copied onto the child stack.',
    'Uses the current-context global at RVA 0x2A25048 and VM allocator at RVA 0x2A250A0. Child destruction can run exit script code before freeing memory. Allocation failure is not safely returned by the captured creator: it dereferences the resulting child without a NULL guard. No script-PC, pointer-lifetime or concurrency validation is established.',
    '3e1f00 3e1e30 3e1240 41b320 3e1410')
add(11,'Resource queue pending',
    'Returns @INT indicating whether the resource-request list at RVA 0x2A0D628 is nonempty. The worker changes request states and the completion path invokes stored callbacks before unlinking and freeing requests.',
    'This is a list-presence test, not a global I/O completion fence. A completed request awaiting callback dispatch still keeps the list nonempty; the adapter takes no lock.',
    '3a0a30 3a0710 3a0790 3a0c60')
add(12,'Repack resource regions',
    'Calls the resource-region rebuild path at RVA 0x39D460 with a NULL argument. It recalculates placements, relocates retained resources, and unlinks/frees selected region records; BAR release callbacks can be reached.',
    'No VM return slot. This is mutating resource maintenance, not a general unload-all or lifetime barrier. It can enqueue loads and modify addresses; the complete transitive resource/callback graph is outside this annotation.',
    '39d460 39d590 39e690 39e2a0')
add(14,'Apply indexed flag action record',
    'Sets the grouped flag for operand 0 and interprets its variable-length action record from the table rooted at RVA 0xBF30B0. Actions can change other flags, apply further records recursively, modify stored state and trigger native follow-up functions.',
    'This is not a plain bit-setter. Three hard-coded IDs also call RVA 0x210540, and the path includes additional rule propagation. It does not check the ID/table bounds or record length before dereferencing them. The complete meanings of all action opcodes and downstream callbacks remain open.',
    '39afc0 39a980 3f0ea0')
add(15,'Read grouped flag',
    'For ID 65535, returns zero. Otherwise reads bit (id & 31) from DWORD index 8*(signed(id)>>10) + ((id & 1023)>>5), based at RVA 0x9AB540. Returns @INT.',
    'The signed shift and overlapping grouped indexing are native behavior. IDs other than the explicit 65535 sentinel receive no bounds check; a negative ID is not rejected.',
    '39a980')
add(19,'Set queued flag',
    'Sets the unsigned-indexed bit in the array at RVA 0x9AD8E8 if it is not already set. For IDs 37, 42, 45 and 46, an additional preexisting flag can suppress the operation. A table lookup then decides whether the low byte of the ID is appended to the notification queue.',
    'The byte queue cursor at RVA 0x9ADA07 increments with wraparound. The table lookup uses a key encoded as a pointer value and dereferences its result without a NULL check; valid table contents and a matching ID are required. ID 0 becomes a NULL search key; external CRT argument-validation behavior is outside this capture. No guessed game feature name is assigned.',
    '3df2e0 3deee0 3deab0 39ac80')
add(20,'Read queued flag',
    'Returns @INT for bit (unsignedId & 31) in DWORD array RVA 0x9AD8E8 at index unsignedId >> 5.',
    'No array-bound or semantic-ID check is present. This reads the flag array modified by 0:19; it does not consume the associated notification queue.',
    '3deab0')
add(28,'Initialize screen-effect parameters',
    'Initializes the decoded caller buffer: QWORD +0=0, DWORD +8=112, DWORD +12=1, QWORD +16=1 and DWORD +24=1. No VM return slot.',
    'Writes 28 bytes to caller-owned memory without a NULL guard. The later activation path also writes interpolation fields at +28/+32, so activation requires storage beyond these initialized 28 bytes. This call alone does not enable the global effect.',
    '3f7850 3f7880')
add(29,'Enable shared screen effect',
    'Sets bit 0 in the decoded parameter buffer and enables the shared rendering state at RVA 0xABC690. It applies mode from +4, alpha byte from +8, position from +12/+16 and float rate from +20 and signed integer duration/count from +24. It also initializes the buffer interpolation pair at +28/+32.',
    'The adapter explicitly supplies zero as the interpolation duration; the helper clamps it to one, initializing the pair to (0,1). Coordinate additions use 16-bit wraparound before scaling to current render dimensions. State is shared globally; the caller buffer is also mutated. No NULL or size guard.',
    '3f7880 15f1d0 15f160 15f1e0 15f1a0 15f170 3b7810 15f250')
add(30,'Disable shared screen effect',
    'Clears bit 0 in the decoded parameter buffer and disables the shared screen-effect state. Disabling also resets its global rate, elapsed value and duration.',
    'No VM return slot or NULL guard. The global effect is shared, so this can disable state previously configured through a different parameter buffer.',
    '3f7900 15f170')
for index,white,increasing in [(31,True,True),(32,True,False),(87,False,True),(88,False,False)]:
    add(index,('Increase ' if increasing else 'Decrease ')+('white' if white else 'black')+' overlay opacity',
        'Divides the float operand by 2, truncates to a signed 32-bit integer and configures the shared overlay at RVA 0xABB3B0. '+('RGB bytes become 255 and the render-mode field becomes 72. ' if white else 'RGB bytes become 0 and the render-mode field becomes 68. ')+('State 3 increases alpha toward 128. ' if increasing else 'State 1 first performs its native two-pass delay before state 2 decreases alpha toward zero. ')+ 'The update subtracts the native float delta at RVA 0x717484.',
        'No finite/range validation. The helper doubles the converted value modulo 2^32 and then converts that zero-extended DWORD to float; negative inputs can therefore become large positive durations, and wrapped zero can reach a reciprocal divide by zero. An originally zero converted value instead selects duration 2 and slope 1. Units are native update units, not proven wall seconds. State 4 can invoke another native continuation after reaching alpha 128; its full effect remains open.',
        '156dc0 156ce0 156c90 156d00 156f10 160a50 160a70')
add(47,'Allocate from current region',
    'Sign-extends the low 32-bit operand to a 64-bit byte count and calls vtable slot +8 of the active allocator at RVA 0x9BA920 with the third argument zero. Returns the encoded result as @ADR.',
    'No adapter size-range or active-owner check. Negative input becomes a negative 64-bit request. The current allocator can be replaced during region transitions; the returned address is not a stable cross-transition allocation contract.',
    '152430 152680 4ad240')
add(48,'Free through current region',
    'Decodes operand 0 and calls vtable slot +16 on the allocator currently stored at RVA 0x9BA920. No VM return slot.',
    'The adapter neither checks for NULL nor identifies the allocator that originally produced the pointer. The active allocator can change during region transitions, so allocation provenance and lifetime remain required.',
    '152570 152680 4ad270')
for index,down in [(55,True),(56,False)]:
    add(index,'Start '+('countdown' if down else 'count-up')+' timer',
        'Uses 32-bit arithmetic to multiply the integer operand by 60 and store the timer limit. '+('Initializes the displayed count to that limit and selects countdown mode. ' if down else 'Initializes the displayed count to zero and selects count-up mode. ')+ 'Snapshots counter RVA 0xABB850 and sets state 1; the next unpaused timer task changes it to state 2 before updating the count.',
        'Counter progress is driven by the installed timing callback and can be paused through RVA 0xABB854. The factor 60 establishes the native conversion, not exact elapsed wall seconds. Countdown clamps at zero; count-up clamps at 215999 and otherwise stops on a positive configured limit. Limit completion dispatches native call 3AABE0(74,0). Input multiplication can wrap; no argument bounds are checked.',
        '157140 157170 157190 1571b0 1570f0 154700')
add(63,'Add indexed inventory entry',
    'Uses operand 0 as an entry ID and operand 1 as a destination selector. The native policy chooses global storage (selector 100) or a mapped character record. It can set a unique-entry bit, increment a byte quantity, or insert into character slots. Returns @INT indicating a nonzero policy result.',
    'The global quantity policy caps ordinary additions at 99. Character selectors 14/15 map to 1/6; an invalid destination mapping can fall back to global storage. Unknown entry IDs are dereferenced without a NULL guard. Type 19 insertion searches 80 slots, but a full array does not cause the outer function to report failure. Other entry types can trigger equipment/default-selection and notification side effects. This is not a general successful-insertion guarantee.',
    '3c3f00 3c4d50 3c3fe0 3e39a0 3a14e0 3e60c0 3a1330 3a1380 3c47a0')
add(64,'Block pooled native requests',
    'Sets the admission gate byte at RVA 0xAD93C0 to one. The captured request-allocation paths test this byte and return without allocating a request when it is set.',
    'No VM return slot. This does not walk or stop already queued records. The exact in-game name of the pooled subsystem is left open; setup clears the gate. This is not a global game pause.',
    '1dd4e0 1dd510 1ddf10 1de230 1de7c0')
add(65,'Play sound from bank 2',
    'Passes operand 0 as the sound number to the native SslSePlay path with bank 2 and ID 0. The adapter supplies zero for the second wrapper parameter; the wrapper supplies scale value 16383 before conversion to a float.',
    'No VM return slot or success result. Playback depends on the sound-system singleton, a matching loaded bank and the backend handle checks. The native path allocates a playback object, starts a handle and adds it to a global list; missing bank/invalid count can produce no playback. Diagnostic text establishes the sound meaning, without guessing an audible sound name.',
    '1dd170 1df790 1398e0')
add(69,'Set rule-linked flag',
    'Sets bit (unsignedId & 31) at DWORD index unsignedId >> 5 in array RVA 0x9ABC40, then runs the rule evaluator at RVA 0x3F0EA0.',
    'No bit-array bounds check. The evaluator counts satisfied conditions across three flag families and can apply further grouped action records, queued flags or rule-linked flags recursively. This can have effects beyond the requested bit.',
    '3e3930 3f0ea0')
add(70,'Read grouped flag bit 0x800',
    'Returns @INT indicating whether DWORD RVA 0x9AB5C4 has mask 0x800 set. No operand.',
    'A direct read of stored state; no stronger game-mode or completion label is assigned. The native code does not synchronize this read.',
    '39ac80')
add(73,'Clear rule-linked flag',
    'Clears bit (unsignedId & 31) at DWORD index unsignedId >> 5 in array RVA 0x9ABC40. No VM return slot.',
    'No bit-array bounds check. Unlike 0:69, this helper returns immediately after the clear and does not run the rule evaluator.',
    '3e3910')
add(77,'Start task-based screen blend',
    'Divides the float operand by 2 and schedules transition work with mode byte 1. The initializer doubles that value into task storage, replaces prior transition tasks and schedules rendering work. The update advances two shared blend values in the range 0..128 using native delta RVA 0x717480.',
    'This is asynchronous task setup, not a blocking wait. It allocates task state and can cancel/replace earlier work. It has no finite, zero-duration or allocation-failure guard on the captured path; a helper divides 128 by the stored duration. Exact wall-clock timing and all rendering callbacks remain outside the contract.',
    '163590 163040 163110 163540 163630 1635a0')
for index,edge in [(80,False),(81,True)]:
    add(index,'Read '+('newly pressed' if edge else 'held')+' input bit',
        'Reads '+('the newly-set-bit mask at +8 of' if edge else 'the current mask in')+' the mapped input record selected by index zero at RVA 0xBF31A0. Returns the chosen bit as @INT. The register BT instruction uses operand 0 modulo 64.',
        'Input update computes current and rising/falling-edge masks from native mapping tables; this is the mapped mask, not a declared keyboard scan code or physical controller button number. Disabled/reset records clear the masks, and resynchronization can suppress edge detection. The adapter performs no refresh or locking.',
        '39b780 39bf00 39c720 39b640')
add(89,'Read rule-linked flag',
    'Returns @INT for bit (unsignedId & 31) at DWORD index unsignedId >> 5 in array RVA 0x9ABC40.',
    'No array-bound check or rule evaluation. Reads the same flag family modified by 0:69 and 0:73.',
    '3e38f0')
add(97,'Remove indexed inventory entry',
    'For destination selector 100, clears a unique-entry bit or subtracts one from a byte quantity with a zero floor. Other selectors resolve a character record and search its ordinary slot array backward, clearing the last matching entry.',
    'The native helper produces an internal success value, but the descriptor has no VM return slot. The character path dereferences the mapped record without a NULL check. It does not perform the type-19 80-slot search used by the add path, so this is not a universal inverse of 0:63.',
    '3c49c0 3c4a40 3a14e0 3e60c0')
add(100,'Increment saturating counter',
    'Increments the unsigned WORD at RVA 0x9AD880 only while its current value is below 999. No operands and no VM return slot.',
    'Values already at or above 999 are left unchanged, not clamped downward. The semantic name of this stored counter is not established; this is a shared-memory write without synchronization.',
    '3e6a10')
add(101,'Check three grouped flags',
    'Returns @INT for the short-circuit conjunction of grouped flag IDs 4215, 9289 and 11325.',
    'Uses the grouped-flag reader at RVA 0x39A980. The exact named milestone represented by the conjunction is not established.',
    '3e6b00 39a980')
add(103,'Check difficulty-dependent completion',
    'Reads the stored difficulty selector. Selector 0 and unknown selectors return false. Selector 1 requires native completion percentage ==100 and an additional 27-value aggregate ==100; selector 2 requires only the percentage. Selector 3 requires positive global inventory counts for IDs 593, 594 and 595. Returns @INT.',
    'This is not a pure read: the percentage branch can lazily initialize managers, allocate temporary region/heap objects, mutate global completion totals and then free resources. The exact in-game reward/ending gated by this predicate is not proved. The full completion-table algorithm and allocation-failure behavior remain open.',
    '3e6a60 152350 2f3ab0 348b30 2c7760 3c4380 3c4720')
add(104,'Toggle type-2 request flag',
    'Walks the shared list at RVA 0xAD93B0. For records whose byte +53 equals 2, positive signed operand 0 clears mask 8 in DWORD +40; zero or negative operands set that mask.',
    'No VM return slot. Follows encoded next links at +32 and changes existing records without validating their lifetime or locking. The full behavioral meaning of flag 8 is left open; no generic pause/resume claim is made.',
    '1df060 1df0a0 1deb50')

assert set(annotations)=={'0:'+str(i) for i in descriptors}
(HERE/'annotations.json').write_text(json.dumps({'schema':1,'originalSha256':'9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed','annotations':annotations},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print({'annotations':len(annotations)})
