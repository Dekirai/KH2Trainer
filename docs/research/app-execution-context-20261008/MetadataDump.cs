using System.Reflection;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json;

// Read-only PE/CLI inspection. Never loads or invokes the target assembly.
if (args.Length != 2) throw new ArgumentException("input PE, output JSON");
byte[] image = File.ReadAllBytes(args[0]);
using var stream = new MemoryStream(image, writable: false);
using var pe = new PEReader(stream);
var md = pe.GetMetadataReader();
var opcodes = typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static)
    .Where(f => f.FieldType == typeof(OpCode)).Select(f => (OpCode)f.GetValue(null)!)
    .ToDictionary(o => unchecked((ushort)o.Value));
string Name(EntityHandle h) => h.Kind switch {
    HandleKind.MethodDefinition => MethodName((MethodDefinitionHandle)h),
    HandleKind.MemberReference => MemberName((MemberReferenceHandle)h),
    HandleKind.TypeReference => md.GetString(md.GetTypeReference((TypeReferenceHandle)h).Namespace) + "." + md.GetString(md.GetTypeReference((TypeReferenceHandle)h).Name),
    HandleKind.TypeDefinition => TypeName((TypeDefinitionHandle)h),
    HandleKind.FieldDefinition => TypeName(md.GetFieldDefinition((FieldDefinitionHandle)h).GetDeclaringType()) + "::" + md.GetString(md.GetFieldDefinition((FieldDefinitionHandle)h).Name),
    HandleKind.MethodSpecification => Name(md.GetMethodSpecification((MethodSpecificationHandle)h).Method),
    _ => h.Kind.ToString()
};
string TypeName(TypeDefinitionHandle h) {
    var t = md.GetTypeDefinition(h); return md.GetString(t.Namespace) + "." + md.GetString(t.Name);
}
string MethodName(MethodDefinitionHandle h) {
    var m = md.GetMethodDefinition(h); return TypeName(m.GetDeclaringType()) + "::" + md.GetString(m.Name);
}
string MemberName(MemberReferenceHandle h) {
    var m=md.GetMemberReference(h);return Name(m.Parent)+"::"+md.GetString(m.Name);
}
object Resolve(int token) {
    if ((token & unchecked((int)0xff000000)) == 0x70000000)
        return new { token = $"0x{token:X8}", text = md.GetUserString(MetadataTokens.UserStringHandle(token & 0xffffff)) };
    var h = MetadataTokens.EntityHandle(token);
    return new { token = $"0x{token:X8}", name = Name(h), kind = h.Kind.ToString() };
}
List<object> Decode(byte[] il) {
    var rows = new List<object>(); int p = 0;
    while (p < il.Length) {
        int start = p; ushort key = il[p++]; if (key == 0xfe) key = (ushort)(0xfe00 | il[p++]);
        if (!opcodes.TryGetValue(key, out var op)) throw new BadImageFormatException($"opcode {key:X}");
        object? operand = null;
        int I4() { int n = BitConverter.ToInt32(il, p); p += 4; return n; }
        switch (op.OperandType) {
            case OperandType.InlineNone: break;
            case OperandType.ShortInlineI: operand = (sbyte)il[p++]; break;
            case OperandType.InlineI: operand = I4(); break;
            case OperandType.InlineI8: operand = BitConverter.ToInt64(il,p); p += 8; break;
            case OperandType.ShortInlineR: operand = BitConverter.ToSingle(il,p); p += 4; break;
            case OperandType.InlineR: operand = BitConverter.ToDouble(il,p); p += 8; break;
            case OperandType.ShortInlineVar: operand = il[p++]; break;
            case OperandType.InlineVar: operand = BitConverter.ToUInt16(il,p); p += 2; break;
            case OperandType.ShortInlineBrTarget: { int d=(sbyte)il[p++]; operand = $"IL_{p+d:X4}"; break; }
            case OperandType.InlineBrTarget: { int d=I4(); operand = $"IL_{p+d:X4}"; break; }
            case OperandType.InlineSwitch: { int n=I4(); int end=p+4*n; var targets=new List<string>(); for(int i=0;i<n;i++) targets.Add($"IL_{end+I4():X4}"); operand=targets; break; }
            case OperandType.InlineSig: { int token=I4(); var signature=md.GetStandaloneSignature((StandaloneSignatureHandle)MetadataTokens.EntityHandle(token)); operand=new {token=$"0x{token:X8}",blob=Convert.ToHexString(md.GetBlobBytes(signature.Signature))}; break; }
            case OperandType.InlineField: case OperandType.InlineMethod: case OperandType.InlineString:
            case OperandType.InlineTok: case OperandType.InlineType: operand=Resolve(I4()); break;
            default: throw new BadImageFormatException(op.OperandType.ToString());
        }
        rows.Add(new { offset=$"IL_{start:X4}",op=op.Name,operand,bytes=Convert.ToHexString(il.AsSpan(start,p-start)) });
    }
    return rows;
}
var methods = new List<object>();
foreach (var handle in md.MethodDefinitions) {
    var m=md.GetMethodDefinition(handle); object? body=null;
    if (m.RelativeVirtualAddress != 0 && (m.ImplAttributes & MethodImplAttributes.CodeTypeMask) == MethodImplAttributes.IL) {
        var b=pe.GetMethodBody(m.RelativeVirtualAddress); byte[] il=b.GetILBytes()!;
        body=new {size=b.Size,headerAndBodyBytes=Convert.ToHexString(pe.GetSectionData(m.RelativeVirtualAddress).GetContent(0,b.Size).AsSpan()),
            ilBytes=Convert.ToHexString(il),maxStack=b.MaxStack,localVariablesInitialized=b.LocalVariablesInitialized,
            localSignatureToken=$"0x{MetadataTokens.GetToken(b.LocalSignature):X8}",
            exceptionRegions=b.ExceptionRegions.Select(x=>new {kind=x.Kind.ToString(),tryOffset=x.TryOffset,tryLength=x.TryLength,handlerOffset=x.HandlerOffset,handlerLength=x.HandlerLength,filterOffset=x.FilterOffset,catchType=x.CatchType.IsNil?null:Name(x.CatchType)}),
            instructions=Decode(il)};
    }
    var import=m.GetImport();
    methods.Add(new {token=$"0x{MetadataTokens.GetToken(handle):X8}",name=MethodName(handle),rva=$"0x{m.RelativeVirtualAddress:X}",attributes=m.Attributes.ToString(),implementation=m.ImplAttributes.ToString(),
        signature=Convert.ToHexString(md.GetBlobBytes(m.Signature)),customAttributes=m.GetCustomAttributes().Select(a=>{var c=md.GetCustomAttribute(a);return new {constructor=Name(c.Constructor),value=Convert.ToHexString(md.GetBlobBytes(c.Value))};}),import=import.Module.IsNil?null:new {module=md.GetString(md.GetModuleReference(import.Module).Name),name=md.GetString(import.Name)},body});
}
var cor=pe.PEHeaders.CorHeader!;var fixups=new List<object>();
if(cor.VtableFixupsDirectory.Size>0) {
    byte[] rows=pe.GetSectionData(cor.VtableFixupsDirectory.RelativeVirtualAddress).GetContent(0,cor.VtableFixupsDirectory.Size).ToArray();
    for(int off=0;off<rows.Length;off+=8) {
        int rva=BitConverter.ToInt32(rows,off);int count=BitConverter.ToUInt16(rows,off+4);int flags=BitConverter.ToUInt16(rows,off+6);int size=(flags&2)!=0?8:4;
        byte[] cells=pe.GetSectionData(rva).GetContent(0,count*size).ToArray();
        fixups.Add(new {rva=$"0x{rva:X}",count,flags,bytes=Convert.ToHexString(cells),tokens=Enumerable.Range(0,count).Select(n=>Resolve(BitConverter.ToInt32(cells,n*size)))});
    }
}
var result=new {schemaVersion=1,Domain="clr",scope="Static CLI metadata and IL decoded from file bytes; target assembly never loaded or executed.",
    originalSha256=Convert.ToHexString(SHA256.HashData(image)).ToLowerInvariant(),imageBase=$"0x{pe.PEHeaders.PEHeader!.ImageBase:X}",
    peEntryPointRva=$"0x{pe.PEHeaders.PEHeader.AddressOfEntryPoint:X}",corFlags=cor.Flags.ToString(),corEntryPoint=$"0x{cor.EntryPointTokenOrRelativeVirtualAddress:X8}",
    metadataVersion=md.MetadataVersion,fixups,methods,
    members=md.MemberReferences.Select(h=>{var m=md.GetMemberReference(h);return new {token=$"0x{MetadataTokens.GetToken(h):X8}",name=Name(h),signature=Convert.ToHexString(md.GetBlobBytes(m.Signature))};}),
    fields=md.FieldDefinitions.Select(h=>{var f=md.GetFieldDefinition(h);return new {token=$"0x{MetadataTokens.GetToken(h):X8}",name=Name(h),signature=Convert.ToHexString(md.GetBlobBytes(f.Signature)),attributes=f.Attributes.ToString()};}),
    types=md.TypeDefinitions.Select(h=>{var t=md.GetTypeDefinition(h);return new {token=$"0x{MetadataTokens.GetToken(h):X8}",name=Name(h),baseType=t.BaseType.IsNil?null:Name(t.BaseType)};}),
    assemblies=md.AssemblyReferences.Select(h=>{var a=md.GetAssemblyReference(h);return new {name=md.GetString(a.Name),version=a.Version.ToString()};})};
File.WriteAllText(args[1],JsonSerializer.Serialize(result,new JsonSerializerOptions{WriteIndented=true})+"\n");
Console.WriteLine($"methods={methods.Count}, fixup groups={fixups.Count}");
