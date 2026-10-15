global using System.IO;
using System.Globalization;
using System.IO.MemoryMappedFiles;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using KH2Trainer;
using KH2Trainer.Core;

int checks=0,wireChecks=0;
void Check(bool condition,string text){++checks;if(!condition)throw new InvalidDataException(text);}
using var featureStream=Assembly.GetExecutingAssembly().GetManifestResourceStream("features.json")!;
var catalog=FeatureCatalog.Load(featureStream);
var byId=catalog.ToDictionary(f=>f.Id);
var features=catalog.Where(f=>f.CapabilitySlot>=477&&f.CapabilitySlot<=481).ToArray();
Check(catalog.Count==358&&features.Length==5,"358 controls and five new mission definitions");
Check(features.All(f=>catalog.Count(g=>g.CapabilitySlot==f.CapabilitySlot)==1),"no slot aliases");
foreach(var f in features){
 bool rejected=false;
 try{ProfileStore.Validate(new TrainerProfile{Name="independent rejection",Values=new(){[f.Id]=0}},catalog);}catch(InvalidDataException){rejected=true;}
 Check(rejected,"all new actions and readouts blocked from profile replay");
}
var host=new Host();var errors=new List<Exception>();AsyncCommand.ReportError=errors.Add;
var vms=features.Select(f=>new FeatureVm(f,host,new Dictionary<string,IReadOnlyList<FeatureChoice>>())).ToArray();
var snap=new TrainerSnapshot{Connected=true,Status=1,SceneReady=true};
foreach(var vm in vms){vm.Update(snap);Check(!vm.IsAvailable,"older bridge missing support blocks feature");}
foreach(var f in features)snap.Supported[f.CapabilitySlot/64]|=1UL<<(f.CapabilitySlot%64);
foreach(var vm in vms)vm.Update(snap);
var add=vms.Single(x=>x.Id=="mission.counter.add");var digit=vms.Single(x=>x.Id=="mission.counter.digit");
foreach(int index in Enumerable.Range(0,3)){
 add.Arguments[0].SelectedChoice=add.Arguments[0].Choices.Single(c=>c.Value==index);
 foreach(long delta in new long[]{int.MinValue,-100,-1,0,1,100,int.MaxValue}){
  add.Arguments[1].ValueText=delta.ToString(CultureInfo.InvariantCulture);int before=host.Calls.Count;add.ApplyCommand.Execute(null);
  Check(host.Calls.Count==before+1&&host.Calls[^1].Command==1477&&host.Calls[^1].Args.SequenceEqual(new double[]{index,delta}),"delta sign/endpoints/order");
 }
 foreach(int position in Enumerable.Range(0,10))foreach(int number in Enumerable.Range(0,10)){
  digit.Arguments[0].SelectedChoice=digit.Arguments[0].Choices.Single(c=>c.Value==index);
  digit.Arguments[1].SelectedChoice=digit.Arguments[1].Choices.Single(c=>c.Value==position);
  digit.Arguments[2].SelectedChoice=digit.Arguments[2].Choices.Single(c=>c.Value==number);
  int before=host.Calls.Count;digit.ApplyCommand.Execute(null);
  Check(host.Calls.Count==before+1&&host.Calls[^1].Command==1478&&host.Calls[^1].Args.SequenceEqual(new double[]{index,position,number}),"all digit selector combinations");
 }
}
foreach(string invalid in new[]{"-2147483649","2147483648","NaN","Infinity","text",""}){
 int before=host.Calls.Count,err=errors.Count;add.Arguments[1].ValueText=invalid;add.ApplyCommand.Execute(null);
 Check(host.Calls.Count==before&&errors.Count==err+1,"invalid text/range rejected before host");
}
host.Pending=new(TaskCreationOptions.RunContinuationsAsynchronously);int pendingStart=host.Calls.Count;
digit.ApplyCommand.Execute(null);digit.ApplyCommand.Execute(null);
Check(host.Calls.Count==pendingStart+1&&!digit.ApplyCommand.CanExecute(null),"pending action cannot duplicate dispatch");
host.Pending.SetException(new IOException("synthetic uncertain result"));
for(int attempt=0;digit.ApplyCommand.IsRunning&&attempt<100;++attempt)await Task.Delay(5);
Check(!digit.ApplyCommand.IsRunning,"async command finishes failure");host.Pending=null;
foreach(var vm in vms)vm.Update(snap);Check(host.Calls.Count==pendingStart+1,"snapshot does not retry relative action");
foreach(var vm in vms.Where(v=>v.IsReadOnly)){
 Check(!vm.IsEditable&&!vm.ShowApplyButton&&vm.LiveValue=="—","read-only observation absent");
 int slot=vm.Definition.ValueSlot;
 foreach(double value in slot==481?new[]{-123.5,-0.5,-0d,0d,1.25,(double)float.MaxValue}:new[]{0d,1d,(double)int.MaxValue}){
  snap.Valid[slot/64]|=1UL<<(slot%64);snap.Values[slot]=value;vm.Update(snap);
  Check(vm.LiveValue==FeatureFormatting.Format(vm.Definition,value),"combo formatted value is actual readout");
  Check(!vm.ShowApplyButton&&host.Calls.Count==pendingStart+1,"combo update sends no command");
 }
 snap.Valid[slot/64]&=~(1UL<<(slot%64));vm.Update(snap);Check(vm.LiveValue=="—","invalidated sample clears display");
}
host.Busy=true;Check(!add.ApplyCommand.CanExecute(null)&&!digit.ApplyCommand.CanExecute(null),"shell busy gate");host.Busy=false;
foreach(var vm in vms)vm.Update(snap with{SceneReady=false});Check(!add.ApplyCommand.CanExecute(null)&&!digit.ApplyCommand.CanExecute(null),"scene gate");

// A newly created mapping with a negative pseudo-PID cannot name a live game.
int pseudoPid=-Random.Shared.Next(1,int.MaxValue);
using var mapping=MemoryMappedFile.CreateNew(BridgeProtocol.MappingPrefix+pseudoPid,BridgeProtocol.MappingSize);
using var peer=mapping.CreateViewAccessor();peer.Write(0,BridgeProtocol.Magic);peer.Write(4,BridgeProtocol.Version);
using var connection=new BridgeConnection(pseudoPid);
async Task Wire(int command,double[] expected,int resultCode){
 var task=connection.ExecuteAsync(command,expected);
 int sequence=peer.ReadInt32(BridgeProtocol.RequestSequence);
 Check(sequence!=peer.ReadInt32(BridgeProtocol.ResponseSequence),"request published");
 Check(peer.ReadInt32(BridgeProtocol.Command)==command,"wire command");
 for(int i=0;i<8;++i){Check(peer.ReadDouble(BridgeProtocol.Arguments+i*8)==(i<expected.Length?expected[i]:0),"wire precise ordered arguments and zero tail");++wireChecks;}
 peer.Write(BridgeProtocol.ResultCode,resultCode);Thread.MemoryBarrier();peer.Write(BridgeProtocol.ResponseSequence,sequence);
 var result=await task;Check(result.Code==resultCode&&result.Sequence==sequence&&result.Success==(resultCode==0),"one acknowledged result");
}
foreach(int index in Enumerable.Range(0,3))foreach(double delta in new[]{(double)int.MinValue,-1d,0d,1d,(double)int.MaxValue})await Wire(1477,new[]{(double)index,delta},delta==0?2:0);
foreach(int index in Enumerable.Range(0,3))foreach(int position in Enumerable.Range(0,10))foreach(int number in Enumerable.Range(0,10))await Wire(1478,new[]{(double)index,position,number},0);
Check(BdxNativeCallCatalog.Default.AnnotatedCount==256,"compiled actual BDX resource");
var resultObject=new{success=true,checks,wireArgumentChecks=wireChecks,sourceCompiled=true,featureDefinitions=catalog.Count,missionControls=features.Length,bdxAnnotations=BdxNativeCallCatalog.Default.AnnotatedCount,featureSha256=Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[0]))).ToLowerInvariant(),scope="Actual Core and FeatureVm source compiled in isolated output. Synthetic host and newly created negative-pseudo-PID mapping only. No target process, injection, GUI, saves or gameplay."};
Console.WriteLine(JsonSerializer.Serialize(resultObject,new JsonSerializerOptions{WriteIndented=true}));

sealed class Host:IFeatureHost{
 public bool Busy{get;set;}public bool ShowDescriptions=>true;public bool IsFavorite(string id)=>false;public void ToggleFavorite(FeatureVm feature){}
 public List<(int Command,double[] Args)> Calls{get;}=[];public TaskCompletionSource? Pending{get;set;}
 public Task Execute(int command,IReadOnlyList<double> arguments,string label){Calls.Add((command,arguments.ToArray()));return Pending?.Task??Task.CompletedTask;}
}
