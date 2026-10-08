using KH2Trainer.Core;
using System.Security.Cryptography;
using System.Text.Json;

if(args.Length!=3)throw new ArgumentException("gameRoot expected-structure.json output.json");
string gameRoot=Path.GetFullPath(args[0]),expectedPath=Path.GetFullPath(args[1]),outputPath=Path.GetFullPath(args[2]);
var reader=new AssetArchiveReader(protectedDirectories:[gameRoot]);
using var expected=JsonDocument.Parse(File.ReadAllBytes(expectedPath));
var references=expected.RootElement.EnumerateArray().ToDictionary(j=>j.GetProperty("asset").GetString()!,j=>j);
string names=Path.Combine(gameRoot,"Modding","openkh","resources","kh2idx.txt");
var results=new List<object>();int checks=0;
void Check(bool condition,string label) {checks++;if(!condition)throw new InvalidDataException(label);}
static string Hash(byte[] bytes)=>Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
async Task<byte[]> Read(AssetPayload payload) {
    Check(payload.Length<=128*1024*1024,"Bounded selected asset");
    await using var stream=await reader.OpenReadAsync(payload);byte[] data=new byte[checked((int)payload.Length)];await stream.ReadExactlyAsync(data);return data;
}
string? EdgeName(string kind)=>kind switch {
    "fallthrough" or "conditional-fallthrough"=>"Next", "branch" or "conditional-branch"=>"Branch",
    "call"=>"Call", "call-continuation"=>"CallContinuation", "yield-resume"=>"YieldResume",
    "native-trap-continuation"=>"NativeContinuation", "dynamic-return-or-status3"=>"DynamicReturn",
    "unknown-native-effects" or "status2-exit" or "status5-invalid-opcode"=>null,
    _=>throw new InvalidDataException("Unknown prototype edge "+kind)};
foreach(string hed in Directory.GetFiles(Path.Combine(gameRoot,"Image","dt"),"kh2_*.hed").Order()) {
    var index=reader.OpenPackageIndex(hed,names);
    foreach(var entry in index.Entries.Where(e=>references.ContainsKey(e.Name))) {
        var reference=references[entry.Name];var package=reader.InspectPackageEntry(index,entry.Ordinal);
        var bar=await reader.ReadBarAsync(package.Original);var child=bar.Entries.Single(e=>e.Ordinal==2);
        Check(child.Type==3,"Selected original BAR entry is BDX");byte[] bytes=await Read(child.Payload);
        string hash=Hash(bytes);Check(hash==reference.GetProperty("scriptSha256").GetString(),"Retail payload matches independent loose-source SHA");
        string loosePath=Path.Combine(gameRoot,"Modding","openkh","data","kh2",entry.Name.Replace('/',Path.DirectorySeparatorChar));
        var loose=reader.OpenLooseFile(loosePath);var looseBar=await reader.ReadBarAsync(loose);byte[] looseBytes=await Read(looseBar.Entries[2].Payload);
        Check(bytes.SequenceEqual(looseBytes),"Retail and loose BDX byte identity");
        var d=await BdxInspector.ReadAsync(reader,child.Payload);Check(!d.HitLimit&&d.Diagnostics.Count==0,"Retail script has complete bounded traversal without structural diagnostics");
        var h=reference.GetProperty("header");Check(d.Header.Name==h.GetProperty("name").GetString()&&d.Header.NameHex.Equals(h.GetProperty("nameRaw").GetString(),StringComparison.OrdinalIgnoreCase),"Independent header name");
        Check(d.Header.WorkBytes==h.GetProperty("workSize").GetInt32()&&d.Header.StackBytes==h.GetProperty("stackSize").GetInt32()&&
              d.Header.TemporaryBytes==h.GetProperty("tempSize").GetInt32()&&d.Header.HeaderEnd==h.GetProperty("end").GetInt32(),"Independent size and event boundary");
        var ev=h.GetProperty("events").EnumerateArray().ToArray();Check(ev.Length==d.Header.Events.Count,"Independent event count");
        for(int i=0;i<ev.Length;i++)Check(d.Header.Events[i].Id==ev[i].GetProperty("id").GetInt32()&&d.Header.Events[i].Pc==ev[i].GetProperty("pc").GetInt32()&&
            d.Header.Events[i].IsFirstForId!=ev[i].GetProperty("shadowed").GetBoolean(),"Independent event record");
        var nodes=reference.GetProperty("instructions").EnumerateArray().ToDictionary(i=>i.GetProperty("pc").GetInt32());
        Check(nodes.Keys.Order().SequenceEqual(d.Instructions.Select(i=>i.Pc)),"Every decoded instruction PC agrees with independent prototype");
        foreach(var i in d.Instructions) {
            var node=nodes[i.Pc];Check(i.WidthInWords==node.GetProperty("width").GetInt32(),"Independent instruction width");
            var edges=node.GetProperty("edges").EnumerateArray().Select(e=>(kind:EdgeName(e.GetProperty("kind").GetString()!),target:e.GetProperty("target").ValueKind==JsonValueKind.Null?(int?)null:e.GetProperty("target").GetInt32()))
                .Where(e=>e.kind!=null).Select(e=>$"{e.kind}:{e.target}").Order().ToArray();
            Check(edges.SequenceEqual(i.Edges.Select(e=>$"{e.Kind}:{e.TargetPc}").Order()),"Independent control-flow successors");
        }
        results.Add(new {asset=entry.Name,hed=Path.GetFileName(hed),hedSha256=Hash(File.ReadAllBytes(hed)),entryOrdinal=entry.Ordinal,
            barOrdinal=child.Ordinal,barOffset=child.RelativeOffset,payloadBytes=bytes.Length,payloadSha256=hash,loosePayloadIdentical=true,
            eventCount=d.Header.Events.Count,instructionCount=d.Instructions.Count,decodedBytes=d.DecodedBytes,undecodedBytes=d.UndecodedBytes,
            matchingRebindTraps=d.Instructions.Where(i=>i.TrapBank==2&&i.TrapIndex is 9 or 95).Select(i=>new {i.Pc,i.FileOffset,i.TrapBank,i.TrapIndex}).ToArray(),
            allInstructionPcsWidthsAndEdgesMatch=true,diagnostics=d.Diagnostics.Count});
    }
}
Check(results.Count==references.Count,"Exactly one original-package witness per selected reference");
var report=new {passed=true,checks,expectedStructureSha256=Hash(File.ReadAllBytes(expectedPath)),results,
    scope="Read-only selected original payloads from local retail HED/PKG. Loose-source byte identity and full structural agreement with independent native-derived prototype; not proof of runtime execution or valid trap operands."};
File.WriteAllText(outputPath,JsonSerializer.Serialize(report,new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine(JsonSerializer.Serialize(report));
