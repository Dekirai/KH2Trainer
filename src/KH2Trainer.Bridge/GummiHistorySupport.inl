// Read-only structural support, not permission to call native Undo/Redo.
// Include after GummiEditorFeatures.inl. No IPC commands or game allocations.
// See gummi_round7_contract.json for the separate resource/heap/HUD obligations.
namespace gummi_history {
using gummi_editor::F;
using gummi_editor::ReadSpan;
using gummi_editor::Global;
enum class Direction : unsigned { Inspect, Undo, Redo };
enum class Error : unsigned { None, Host, Owner, Phase, Grid, History, Parameter, ObjectList, Part, Topology, Memory, Changed, Unavailable };
template<class T> struct Buffer {
    T* data=nullptr; size_t count=0,capacity=0;
    Buffer()=default; Buffer(const Buffer&)=delete; Buffer& operator=(const Buffer&)=delete;
    ~Buffer(){if(data)HeapFree(GetProcessHeap(),0,data);}
    bool Resize(size_t n) {
        count=0;if(n>SIZE_MAX/sizeof(T))return false;
        if(n>capacity) {
            T* p=static_cast<T*>(HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,n*sizeof(T)));
            if(!p)return false;if(data)HeapFree(GetProcessHeap(),0,data);data=p;capacity=n;
        }
        count=n;if(n)memset(data,0,n*sizeof(T));return true;
    }
    T& operator[](size_t i){return data[i];} const T& operator[](size_t i)const{return data[i];}
};
struct Cell { BYTE bytes[208]; };
struct HistoryRecord { BYTE bytes[176]; };
struct Parameter { BYTE bytes[128]; };
struct Object { uintptr_t address; uint32_t next,flags; };
struct Task { uintptr_t address; BYTE bytes[152]; };
struct Part {
    uintptr_t address,parameter,task,camera; uint32_t next,flags,objectFlags,id,anchor,palette,taskGroup;
    int layer; float position[4],scale[4],rotation[16],size[4];
    int variant,subtype,field2516; uint16_t appearance[2];
};
struct HistorySlot { int logical,side,counts[2]; size_t starts[2]; };
struct Header {
    gummi_editor::View owner{};
    uintptr_t cells=0,indices=0,scratch=0,parameters=0,partHead=0,partTail=0,objectHead=0,objectTail=0,deleteHead=0,deleteTail=0;
    uintptr_t cursorTasks[2]{},cursorCells[4]{},ghost=0,group=0,detail=0;
    int dimensions[3]{},parameterCount=0,begin=0,end=0,current=0,selected=-1,cursorMode=0,nextMode=0,previousPhase=0;
    unsigned cursorFlags=0,cursorObjectFlags=0,cursorMotionFlags=0; BYTE cursorLatch=0,initialLock=0;
    float cellSize[4]{},center[4]{}; uint32_t palette[32]{};
    size_t cellCount=0; Direction direction=Direction::Inspect;
};
struct Snapshot {
    Header header{}; HistorySlot slots[4]{}; size_t slotCount=0;
    Buffer<Cell> cells; Buffer<uint16_t> indices; Buffer<Parameter> parameters;
    Buffer<Part> parts; Buffer<Object> objects,deleting; Buffer<Task> tasks; Buffer<HistoryRecord> history;
    bool valid=false;
    // This type deliberately has no NativeCallReady flag or callable action.
};
bool Finite(const void* p,size_t n) {
    const auto f=static_cast<const float*>(p);for(size_t i=0;i<n;++i)if(!isfinite(f[i]))return false;return true;
}
bool CellIndex(const Header& h,uintptr_t p,size_t& index) {
    if(p<h.cells || (p-h.cells)%208)return false;index=(p-h.cells)/208;return index<h.cellCount;
}
bool OptionalCell(const Header& h,uintptr_t p){size_t i=0;return !p || CellIndex(h,p,i);}
template<class T> const T& Local(const void* p,size_t offset=0){return *reinterpret_cast<const T*>(static_cast<const BYTE*>(p)+offset);}
bool NativeToolMode(int mode,uintptr_t cornerA,uintptr_t cornerB) {
    switch(mode) {case 2:case 3:case 4:case 11:case 13:case 17:case 19:case 21:return true;
    case 15:return !cornerA || !cornerB;default:return false;}
}
bool TransientTasks(Header& h) {
    if(!Global(0xAFCA38,h.cursorTasks[0]) || !Global(0xAFCA40,h.cursorTasks[1]))return false;
    if(h.owner.phase==1)return !h.cursorTasks[0] && !h.cursorTasks[1];
    if(!h.cursorTasks[0] || !h.cursorTasks[1] || h.cursorTasks[0]==h.cursorTasks[1])return false;
    unsigned found[2]{};auto node=F<uintptr_t>(h.owner.manager,16);
    for(unsigned count=0;node;++count) {
        if(count==2048 || !ReadSpan(node,152))return false;
        for(unsigned i=0;i<2;++i)if(node==h.cursorTasks[i]) {
            if(F<uintptr_t>(node)!=g_base+(i?0x27F700:0x27F8A0) || F<uintptr_t>(node,24)!=h.owner.cursor ||
               F<uintptr_t>(node,88)!=h.owner.manager || F<unsigned>(node,96) ||
               F<int>(node,100)!=(i?46001:49000) || F<uintptr_t>(node,104) || F<uintptr_t>(node,112))return false;
            ++found[i];
        }
        node=F<uintptr_t>(node,120);
    }
    return found[0]==1 && found[1]==1;
}
// Reuses the frozen owner helpers; Build itself accepts preview, not tool phase6.
bool Owners(Header& h) {
    using namespace gummi_editor;
    auto& v=h.owner;uintptr_t moduleVtable=0,moduleManager=0,moduleHeap=0,callback=0;int id=0;
    if(!HostReady() || !Global(Module,moduleVtable) || moduleVtable!=g_base+ModuleVtable ||
       !Global(Module+8,moduleManager) || !Global(Module+16,id) || id!=71 ||
       !Global(Module+36,v.moduleState) || v.moduleState!=1 || !ModuleListed() ||
       !Global(0xAFBEF0,v.work) || !Global(0xAFC118,v.editor) || !Global(0xAF9F08,v.manager) || v.manager!=moduleManager ||
       !Global(0xAFA700,v.objects) || v.objects==v.manager || !Global(0xAFB420,v.heap) ||
       !Global(0x9A8800,moduleHeap) || v.heap!=moduleHeap || !ReadSpan(v.heap,16) ||
       !Global(0xAFBA60,v.partHeap) || !ReadSpan(v.partHeap,16) ||
       !Global(0xAFD1D8,v.inputLock) || v.inputLock || !Global(0xAFC0C0,v.tiny) || v.tiny>1 ||
       !Global(0xAFBEE8,v.material) || v.material<0 || v.material>1 ||
       !ReadSpan(v.work,WorkBytes) || !ReadSpan(v.editor,EditorBytes) ||
       F<uintptr_t>(v.work)!=g_base+0x5B7330 || F<BYTE>(v.editor,8)!=1)return false;
    v.editorVtable=F<uintptr_t>(v.editor);
    if(v.editorVtable!=g_base+(v.tiny?0x5B7920:0x5B78D0) || !ReadSpan(v.editorVtable,24) ||
       F<uintptr_t>(v.editorVtable,16)!=g_base+0x26CBB0 || F<int>(v.editor,12272)!=v.material ||
       F<uintptr_t>(v.work,1414576)!=v.editor+12016 || F<uintptr_t>(v.work,1414584)!=v.editor+1456)return false;
    v.phase=F<int>(v.editor,12276);h.previousPhase=F<int>(v.editor,12280);
    v.camera=F<uintptr_t>(v.work,1414552);v.cursor=F<uintptr_t>(v.work,1414568);
    if((v.phase!=1 && v.phase!=6) || !ReadSpan(v.camera,CameraBytes) || !ReadSpan(v.cursor,CursorBytes) ||
       F<uintptr_t>(v.camera)!=g_base+0x5B7D48 || F<uintptr_t>(v.cursor)!=g_base+0x5B7AC0 ||
       (F<unsigned>(v.camera,2352)&1) || (F<unsigned>(v.cursor,16)&2) ||
       F<uintptr_t>(v.cursor,1344)!=v.camera || F<uintptr_t>(v.cursor,2824)!=v.camera ||
       !Global(0x5B7D50,callback) || callback!=g_base+0x290D00)return false;
    const uintptr_t p[]={v.work,v.editor,v.camera,v.cursor};const size_t sizes[]={WorkBytes,EditorBytes,CameraBytes,CursorBytes};
    for(unsigned i=0;i<4;++i)for(unsigned j=0;j<i;++j)if(!Disjoint(p[i],sizes[i],p[j],sizes[j]))return false;
    v.mode=F<int>(v.camera,2356);v.remaining=F<int>(v.camera,2604);v.cameraFlags=F<unsigned>(v.camera,2612);
    v.fov=F<float>(v.camera,84);v.pitch=F<float>(v.camera,2448);v.yaw=F<float>(v.camera,2452);
    return !v.mode && TaskList(v,false) && TaskList(v,true) && NamedCamera(v);
}
bool Phase(Header& h) {
    const auto& v=h.owner;const auto c=v.cursor;
    h.cursorObjectFlags=F<unsigned>(c,16);h.cursorMotionFlags=F<unsigned>(c,2272);h.cursorFlags=F<unsigned>(c,2976);
    h.cursorMode=F<int>(c,2840);h.nextMode=F<int>(c,2848);h.cursorLatch=F<BYTE>(c,2833);h.initialLock=F<BYTE>(c,2834);
    for(unsigned i=0;i<4;++i)h.cursorCells[i]=F<uintptr_t>(c,2736+8*i);
    h.ghost=F<uintptr_t>(c,2784);h.group=F<uintptr_t>(c,2792);h.detail=F<uintptr_t>(c,2776);
    if(F<BYTE>(v.editor,9072) || !TransientTasks(h))return false;
    if(v.phase==1) {
        // 282A40 hides the cursor but deliberately does not zero its mode.
        return (h.cursorObjectFlags&4) && !(h.cursorObjectFlags&8);
    }
    return (h.previousPhase==1 || h.previousPhase==2 || h.previousPhase==3) &&
        (h.cursorObjectFlags&1) && !(h.cursorObjectFlags&(4|8)) &&
        !(h.cursorMotionFlags&2) && !(h.cursorFlags&8) && !h.cursorLatch && !h.initialLock &&
        !(v.cameraFlags&0x10) && h.cursorMode==h.nextMode &&
        NativeToolMode(h.cursorMode,h.cursorCells[1],h.cursorCells[2]);
}
bool Grid(Snapshot& s) {
    auto& h=s.header;const auto work=h.owner.work;
    for(unsigned i=0;i<3;++i)h.dimensions[i]=F<int>(work,112+4*i);
    uint64_t n=1;for(int d:h.dimensions){if(d<=0 || d>32768 || n>32768/unsigned(d))return false;n*=unsigned(d);}
    // Covered-cell words encode anchor | 0x8000. This is the representable index bound.
    h.cellCount=static_cast<size_t>(n);h.cells=F<uintptr_t>(work,1414536);h.indices=F<uintptr_t>(work,1414544);h.scratch=F<uintptr_t>(work,1414560);
    if(h.cells<8 || h.scratch<8 || !ReadSpan(h.cells-8,8+n*208) || F<uint64_t>(h.cells-8)!=n ||
       !ReadSpan(h.indices,4*n) || !ReadSpan(h.scratch-8,8+16*n) || F<uint64_t>(h.scratch-8)!=2*n)return false;
    const uintptr_t starts[]={h.cells-8,h.indices,h.scratch-8,h.owner.work,h.owner.editor,h.owner.camera,h.owner.cursor};
    const size_t sizes[]={size_t(8+n*208),size_t(4*n),size_t(8+16*n),gummi_editor::WorkBytes,gummi_editor::EditorBytes,gummi_editor::CameraBytes,gummi_editor::CursorBytes};
    for(unsigned i=0;i<7;++i)for(unsigned j=0;j<i;++j)if(!gummi_editor::Disjoint(starts[i],sizes[i],starts[j],sizes[j]))return false;
    memcpy(h.cellSize,reinterpret_cast<const void*>(work+16),16);memcpy(h.center,reinterpret_cast<const void*>(work+32),16);
    if(!Finite(h.cellSize,4) || !Finite(h.center,4))return false;
    for(unsigned i=0;i<3;++i)if(h.cellSize[i]<=0 || !isfinite(float(h.dimensions[i])*h.cellSize[i]))return false;
    if(!s.cells.Resize(h.cellCount) || !s.indices.Resize(2*h.cellCount))return false;
    memcpy(s.cells.data,reinterpret_cast<const void*>(h.cells),h.cellCount*208);memcpy(s.indices.data,reinterpret_cast<const void*>(h.indices),4*h.cellCount);
    const size_t dx=unsigned(h.dimensions[0]),dy=unsigned(h.dimensions[1]);
    for(size_t i=0;i<h.cellCount;++i) {
        const auto p=s.cells[i].bytes;if(Local<int>(p,16)!=int(i) || !Finite(p,4))return false;
        const size_t x=i%dx,y=(i/dx)%dy,z=i/(dx*dy);
        const size_t expected[]={y?i-dx:i,y+1<dy?i+dx:i,x?i-1:i,x+1<dx?i+1:i,z?i-dx*dy:i,z+1<unsigned(h.dimensions[2])?i+dx*dy:i};
        for(unsigned j=0;j<6;++j)if(Local<uintptr_t>(p,56+8*j)!=h.cells+208*expected[j])return false;
        for(unsigned layer=0;layer<2;++layer)if(!OptionalCell(h,Local<uintptr_t>(p,40+8*layer)))return false;
    }
    // Hidden cursors can retain stale selections after a normal grid rebuild.
    if(h.owner.phase==6)for(auto cell:h.cursorCells)if(!OptionalCell(h,cell))return false;
    if(h.owner.phase==6 && !h.cursorCells[0])return false;
    memcpy(h.palette,reinterpret_cast<const void*>(h.owner.editor+1456),sizeof(h.palette));return true;
}
bool Parameters(Snapshot& s) {
    auto& h=s.header;
    if(!Global(0x2B58B00,h.parameterCount) || h.parameterCount<=0 || !Global(0x2B58B08,h.parameters))return false;
    const size_t n=h.parameterCount<255?size_t(h.parameterCount):255;
    if(!ReadSpan(h.parameters,128*n) || !s.parameters.Resize(n))return false;
    const uintptr_t starts[]={h.cells-8,h.indices,h.scratch-8,h.owner.work,h.owner.editor,h.owner.camera,h.owner.cursor};
    const size_t sizes[]={8+208*h.cellCount,4*h.cellCount,8+16*h.cellCount,gummi_editor::WorkBytes,gummi_editor::EditorBytes,gummi_editor::CameraBytes,gummi_editor::CursorBytes};
    for(unsigned i=0;i<7;++i)if(!gummi_editor::Disjoint(h.parameters,128*n,starts[i],sizes[i]))return false;
    memcpy(s.parameters.data,reinterpret_cast<const void*>(h.parameters),128*n);return true;
}
int ParameterIndex(const Snapshot& s,uint32_t id) {
    if(id>=10000)return -1;
    for(size_t i=0;i<s.parameters.count;++i)if(Local<uint16_t>(s.parameters[i].bytes)==id)return int(i);
    // Do not emulate native fallback or 8-bit index aliases above row254.
    return -1;
}
bool ObjectList(uintptr_t head,uintptr_t tail,unsigned nextOffset,Buffer<Object>& out) {
    if(!out.Resize(4096))return false;size_t n=0;uintptr_t p=head,last=0;
    while(p) {
        if(n==4096 || !ReadSpan(p,64))return false;
        for(size_t i=0;i<n;++i)if(out[i].address==p)return false;
        auto& o=out[n++];o.address=p;o.flags=F<uint32_t>(p,16);o.next=F<uint32_t>(p,nextOffset);
        last=p;p=DecodePacked(o.next);
    }
    out.count=n;return last==tail;
}
bool Contains(const Buffer<Object>& list,uintptr_t p){for(size_t i=0;i<list.count;++i)if(list[i].address==p)return true;return false;}
bool Lists(Snapshot& s) {
    auto& h=s.header;
    if(!Global(0xAFBF40,h.partHead) || !Global(0xAFBF48,h.partTail) ||
       !Global(0xAFA780,h.objectHead) || !Global(0xAFA788,h.objectTail) ||
       !Global(0xAFA7A0,h.deleteHead) || !Global(0xAFA7A8,h.deleteTail) ||
       !ObjectList(h.objectHead,h.objectTail,40,s.objects) || !ObjectList(h.deleteHead,h.deleteTail,52,s.deleting))return false;
    for(size_t i=0;i<s.deleting.count;++i)if(Contains(s.objects,s.deleting[i].address))return false;
    if(!Contains(s.objects,h.owner.cursor) || Contains(s.deleting,h.owner.cursor) || !s.tasks.Resize(2048))return false;
    // Copy once; matching each part must not repeatedly call VirtualQuery for
    // every task. The final two-pass comparison includes the copied task data.
    uintptr_t p=F<uintptr_t>(h.owner.objects,16),previous=0;size_t count=0;int priority=INT32_MIN;
    while(p) {
        if(count==2048 || !ReadSpan(p,152))return false;
        auto& t=s.tasks[count++];t.address=p;memcpy(t.bytes,reinterpret_cast<const void*>(p),152);
        if(Local<uintptr_t>(t.bytes,88)!=h.owner.objects || Local<uintptr_t>(t.bytes,128)!=previous || Local<int>(t.bytes,100)<priority)return false;
        priority=Local<int>(t.bytes,100);previous=p;p=Local<uintptr_t>(t.bytes,120);
    }
    s.tasks.count=count;return previous==F<uintptr_t>(h.owner.objects,24);
}
bool PartTask(const Snapshot& s,uintptr_t part,uintptr_t& task) {
    unsigned found=0;
    for(size_t i=0;i<s.tasks.count;++i) {
        const auto& t=s.tasks[i];const auto p=t.bytes;
        if(Local<uintptr_t>(p,24)==part) {
            if(Local<uintptr_t>(p)!=g_base+0x24C180 || Local<uintptr_t>(p,104)!=g_base+0x24C360 ||
               Local<int>(p,100)!=20000 || Local<uintptr_t>(p,112))return false;
            ++found;task=t.address;
        }
    }
    return found==1;
}
bool Parts(Snapshot& s) {
    auto& h=s.header;size_t anchors=0;
    for(size_t i=0;i<s.cells.count;++i)for(unsigned layer=0;layer<2;++layer)if(Local<uintptr_t>(s.cells[i].bytes,24+8*layer))++anchors;
    if(!s.parts.Resize(anchors))return false;uintptr_t p=h.partHead,last=0;size_t n=0;
    while(p) {
        if(n==anchors || !ReadSpan(p,2576) || F<uintptr_t>(p)!=g_base+0x5B6FB0 ||
           !Contains(s.objects,p) || Contains(s.deleting,p))return false;
        const uintptr_t starts[]={h.cells-8,h.indices,h.scratch-8,h.owner.work,h.owner.editor,h.owner.camera,h.owner.cursor,h.parameters};
        const size_t sizes[]={8+208*h.cellCount,4*h.cellCount,8+16*h.cellCount,gummi_editor::WorkBytes,gummi_editor::EditorBytes,gummi_editor::CameraBytes,gummi_editor::CursorBytes,128*s.parameters.count};
        for(unsigned i=0;i<8;++i)if(!gummi_editor::Disjoint(p,2576,starts[i],sizes[i]))return false;
        for(size_t i=0;i<n;++i)if(!gummi_editor::Disjoint(p,2576,s.parts[i].address,2576))return false;
        auto& a=s.parts[n++];a.address=p;a.parameter=F<uintptr_t>(p,2264);a.camera=F<uintptr_t>(p,1344);
        a.next=F<uint32_t>(p,1444);a.flags=F<unsigned>(p,2272);a.objectFlags=F<unsigned>(p,16);
        a.id=F<uint32_t>(p,2544);a.anchor=F<uint32_t>(p,2528);a.palette=F<uint32_t>(p,2556);
        const int row=ParameterIndex(s,a.id);
        if(row<0 || a.parameter!=h.parameters+128*unsigned(row) || a.camera!=h.owner.camera ||
           a.anchor>=h.cellCount || a.palette>=32 || (a.objectFlags&2) || (a.flags&0x100) || !PartTask(s,p,a.task))return false;
        for(size_t i=0;i<s.tasks.count;++i)if(s.tasks[i].address==a.task)a.taskGroup=Local<unsigned>(s.tasks[i].bytes,96);
        a.layer=Local<BYTE>(s.parameters[size_t(row)].bytes,8)<=3?1:0;
        if(Local<uintptr_t>(s.cells[a.anchor].bytes,24+8*a.layer)!=p)return false;
        memcpy(a.position,reinterpret_cast<const void*>(p+1072),16);memcpy(a.scale,reinterpret_cast<const void*>(p+1104),16);
        memcpy(a.rotation,reinterpret_cast<const void*>(p+1448),64);memcpy(a.size,reinterpret_cast<const void*>(p+1672),16);
        if(!Finite(a.position,4) || !Finite(a.scale,4) || !Finite(a.rotation,16) || !Finite(a.size,4))return false;
        a.variant=F<int>(p,2552);a.subtype=F<int>(p,2540);a.field2516=F<int>(p,2516);
        memcpy(a.appearance,reinterpret_cast<const void*>(p+2560),4);last=p;p=DecodePacked(a.next);
    }
    return n==anchors && last==h.partTail;
}
const Part* FindPart(const Snapshot& s,uintptr_t p){for(size_t i=0;i<s.parts.count;++i)if(s.parts[i].address==p)return &s.parts[i];return nullptr;}
bool Topology(const Snapshot& s) {
    const auto& h=s.header;
    for(size_t i=0;i<s.cells.count;++i)for(unsigned layer=0;layer<2;++layer) {
        const auto p=s.cells[i].bytes;const auto owner=Local<uintptr_t>(p,24+8*layer),root=Local<uintptr_t>(p,40+8*layer);
        const uint16_t word=s.indices[layer*h.cellCount+i];
        if(owner) {
            const auto a=FindPart(s,owner);if(!a || a->anchor!=i || a->layer!=int(layer))return false;
            const int row=ParameterIndex(s,a->id);const auto cost=Local<uint16_t>(s.parameters[size_t(row)].bytes,12);
            if(word!=uint16_t(cost|((a->flags&0x20)?0x4000:0)) || Local<BYTE>(p,201+layer)!=a->palette)return false;
            if(a->flags&0x20){if(root)return false;}else if(root!=h.cells+208*i)return false;
        }else if(!root) {if(word)return false;}
        if(root) {
            size_t anchor=0;if(!CellIndex(h,root,anchor))return false;
            const auto a=FindPart(s,Local<uintptr_t>(s.cells[anchor].bytes,24+8*layer));
            if(!a || a->layer!=int(layer) || (a->flags&0x20) || (i!=anchor && word!=uint16_t(anchor|0x8000)))return false;
        }
    }
    // 2600A0 clears coverage by following equal-root neighbors. Detached islands
    // would survive owner removal; check reachability without native recursion.
    Buffer<BYTE> visited;Buffer<size_t> queue;
    if(!visited.Resize(h.cellCount) || !queue.Resize(h.cellCount))return false;
    for(unsigned layer=0;layer<2;++layer) {
        memset(visited.data,0,visited.count);
        for(size_t part=0;part<s.parts.count;++part) {
            const auto& a=s.parts[part];if(a.layer!=int(layer) || (a.flags&0x20))continue;
            size_t start=0,end=1;queue[0]=a.anchor;visited[a.anchor]=1;const auto root=h.cells+208*a.anchor;
            while(start<end) {
                const auto p=s.cells[queue[start++]].bytes;
                for(unsigned neighbor=0;neighbor<6;++neighbor) {
                    size_t index=0;if(!CellIndex(h,Local<uintptr_t>(p,56+8*neighbor),index))return false;
                    if(!visited[index] && Local<uintptr_t>(s.cells[index].bytes,40+8*layer)==root) {
                        if(end==h.cellCount)return false;visited[index]=1;queue[end++]=index;
                    }
                }
            }
        }
        for(size_t i=0;i<h.cellCount;++i)if(Local<uintptr_t>(s.cells[i].bytes,40+8*layer) && !visited[i])return false;
    }
    return true;
}
bool Histories(Snapshot& s) {
    auto& h=s.header;const auto work=h.owner.work;
    h.begin=F<int>(work,1414644);h.end=F<int>(work,1414648);h.current=F<int>(work,1414652);
    if(h.begin<0 || h.begin>=4 || h.end<h.begin || h.end>h.begin+4 || h.current<h.begin-1 || h.current>=h.end)return false;
    if(h.direction==Direction::Undo)h.selected=h.current;
    if(h.direction==Direction::Redo)h.selected=h.current+1;
    if(h.direction!=Direction::Inspect && (h.selected<h.begin || h.selected>=h.end))return false;
    size_t total=0;s.slotCount=size_t(h.end-h.begin);
    for(size_t i=0;i<s.slotCount;++i) {
        auto& slot=s.slots[i];slot.logical=h.begin+int(i);const auto p=work+6256+352064*(slot.logical%4);
        slot.side=F<int>(p,352052);if(slot.side!=(slot.logical<=h.current?1:0))return false;
        for(unsigned group=0;group<2;++group){slot.counts[group]=F<int>(p,28+4*group);if(slot.counts[group]<0 || slot.counts[group]>1000)return false;slot.starts[group]=total;total+=size_t(slot.counts[group]);}
    }
    if(!s.history.Resize(total))return false;
    for(size_t i=0;i<s.slotCount;++i)for(unsigned group=0;group<2;++group) {
        const auto& slot=s.slots[i];const auto p=work+6256+352064*(slot.logical%4)+64+176000*group;
        if(slot.counts[group])memcpy(s.history.data+slot.starts[group],reinterpret_cast<const void*>(p),176*size_t(slot.counts[group]));
        for(int j=0;j<slot.counts[group];++j) {
            const auto r=s.history[slot.starts[group]+size_t(j)].bytes;const auto id=Local<uint32_t>(r,116);const int row=ParameterIndex(s,id);
            size_t anchor=0;
            if(!Finite(r,28) || row<0 || Local<uintptr_t>(r,120)!=h.owner.camera ||
               Local<BYTE>(r,131)>1 || Local<BYTE>(r,133)>1 || Local<BYTE>(r,136)>=32 || Local<BYTE>(r,137)>1 ||
               !CellIndex(h,Local<uintptr_t>(r,144),anchor))return false;
            const unsigned layer=Local<BYTE>(r,131)?0:1;
            if(layer!=(Local<BYTE>(s.parameters[size_t(row)].bytes,8)<=3?1u:0u))return false;
            // Only the group's selected removal plan must match today's owners.
            if(slot.logical==h.selected && group==(h.direction==Direction::Undo?1u:0u)) {
                const auto a=FindPart(s,Local<uintptr_t>(s.cells[anchor].bytes,24+8*layer));
                if(!a || a->id!=id)return false;
                for(int k=0;k<j;++k) {
                    const auto old=s.history[slot.starts[group]+size_t(k)].bytes;
                    if(Local<uintptr_t>(old,144)==Local<uintptr_t>(r,144) && Local<BYTE>(old,131)==Local<BYTE>(r,131))return false;
                }
            }
        }
    }
    return true;
}
bool Capture(Direction direction,Snapshot& out,Error& error) {
    out.valid=false;memset(&out.header,0,sizeof(out.header));memset(out.slots,0,sizeof(out.slots));out.slotCount=0;error=Error::None;
    if(unsigned(direction)>unsigned(Direction::Redo)){error=Error::History;return false;}
    out.header.direction=direction;out.header.selected=-1;out.header.owner.registry=-1;
    if(!gummi_editor::HostReady()){error=Error::Host;return false;}
    if(!Owners(out.header)){error=Error::Owner;return false;}
    if(!Phase(out.header)){error=Error::Phase;return false;}
    if(!Grid(out)){error=Error::Grid;return false;}
    if(!Parameters(out)){error=Error::Parameter;return false;}
    if(!Lists(out)){error=Error::ObjectList;return false;}
    if(!Parts(out)){error=Error::Part;return false;}
    if(!Topology(out)){error=Error::Topology;return false;}
    if(!Histories(out)){error=Error::History;return false;}
    Header fresh{};if(!Owners(fresh) || !Phase(fresh) || !gummi_editor::Same(out.header.owner,fresh.owner) ||
        out.header.cursorMode!=fresh.cursorMode || out.header.nextMode!=fresh.nextMode ||
        memcmp(out.header.cursorTasks,fresh.cursorTasks,sizeof(fresh.cursorTasks)) || !gummi_editor::HostReady()) {error=Error::Changed;return false;}
    out.valid=true;return true;
}
template<class T> bool Equal(const Buffer<T>& a,const Buffer<T>& b){return a.count==b.count && (!a.count || !memcmp(a.data,b.data,sizeof(T)*a.count));}
bool Same(const Snapshot& a,const Snapshot& b) {
    return a.valid && b.valid && !memcmp(&a.header,&b.header,sizeof(Header)) && a.slotCount==b.slotCount &&
        !memcmp(a.slots,b.slots,sizeof(a.slots)) && Equal(a.cells,b.cells) && Equal(a.indices,b.indices) && Equal(a.parameters,b.parameters) &&
        Equal(a.parts,b.parts) && Equal(a.objects,b.objects) && Equal(a.deleting,b.deleting) && Equal(a.tasks,b.tasks) && Equal(a.history,b.history);
}
// Both buffers belong to the caller and remain owned by it. This is a stable
// structural capture, still not a resource/allocation/placement call contract.
bool CaptureStable(Direction direction,Snapshot& first,Snapshot& second,Error& error) {
    if(&first==&second){first.valid=false;error=Error::Changed;return false;}
    if(!Capture(direction,first,error) || !Capture(direction,second,error) || !Same(first,second)) {
        first.valid=second.valid=false;if(error==Error::None)error=Error::Changed;return false;
    }
    return true;
}
} // namespace gummi_history
