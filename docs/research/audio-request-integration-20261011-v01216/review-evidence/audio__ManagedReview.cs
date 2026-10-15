using System.Reflection;
using System.Text.Json;
using KH2Trainer;
using KH2Trainer.Core;
class ReviewHost:IFeatureHost {
 public bool Busy=>false;
 public bool ShowDescriptions=>true;
 public int Calls;
 public bool IsFavorite(string id)=>false;
 public void ToggleFavorite(FeatureVm f){}
 public Task Execute(int c,IReadOnlyList<double> args,string label){++Calls;throw new Exception("Observation must not dispatch");}
}
class ManagedReview {
 static int checks;
 static void Check(bool value,string why){++checks;if(!value)throw new Exception(why);}
 [STAThread] static int Main(string[] args){
  AsyncCommand.ReportError=e=>throw new Exception("Unexpected command error",e);
  using var input=Assembly.GetExecutingAssembly().GetManifestResourceStream("Review.features.json")!;
  var catalog=FeatureCatalog.Load(input);
  string[] ids=["audio.requests.free","audio.requests.interval","audio.requests.gates"];
  var host=new ReviewHost();
  var models=ids.Select(id=>new FeatureVm(catalog.Single(x=>x.Id==id),host,new Dictionary<string,IReadOnlyList<FeatureChoice>>())).ToArray();
  Check(catalog.Count(x=>x.Id.StartsWith("audio.requests."))==3,"exact diagnostic count");
  double[] maxima=[80,25,7];
  for(int n=0;n<models.Length;++n){
   var vm=models[n];var d=vm.Definition;
   Check(d.CapabilitySlot==482+n&&d.ValueSlot==482+n&&catalog.Count(f=>f.CapabilitySlot==482+n)==1,"unique protocol slots");
   Check(d.Kind==FeatureKind.ReadOnly&&d.CommandId==0&&!d.CanSaveInProfile&&!d.RequiresScene&&!d.ChangesProgression,"read-only global observation metadata");
   Check(d.Minimum==0&&d.Maximum==maxima[n]&&d.Step==1,"counter and mask bounds");
   Check(!vm.IsEditable&&!vm.ShowApplyButton&&!vm.ShowChoiceInput&&!vm.ShowValueInput&&vm.ShowLiveValue,"readout-only presentation");
   foreach(double value in new[]{0d,maxima[n]}){
    bool rejected=false;
    try{ProfileStore.Validate(new TrainerProfile{Name="review",Values=new(){{d.Id,value}}},catalog);}catch(System.IO.InvalidDataException){rejected=true;}
    Check(rejected,"even valid observed values cannot enter profiles");
   }
   // Matrix of scene, capability, validity. Unsupported historical bridges have
   // zero bits in these new slots; a supported scene-free sample is observable.
   foreach(bool scene in new[]{false,true})foreach(bool capability in new[]{false,true})foreach(bool measured in new[]{false,true}){
    var s=new TrainerSnapshot{Connected=true,Status=1,SceneReady=scene};
    if(capability)s.Supported[d.CapabilitySlot/64]|=1UL<<(d.CapabilitySlot%64);
    if(measured&&capability)s.Valid[d.ValueSlot/64]|=1UL<<(d.ValueSlot%64);
    s.Values[d.ValueSlot]=maxima[n];vm.Update(s);
    Check(vm.IsAvailable==capability,"scene independence and capability gate");
    Check((vm.LiveValue!="—")== (measured&&capability),"missing measured value clears display");
   }
   vm.Update(TrainerSnapshot.Disconnected);Check(!vm.IsAvailable&&vm.LiveValue=="—","disconnect clears values");
  }
  var allVms=catalog.Select(d=>new FeatureVm(d,host,new Dictionary<string,IReadOnlyList<FeatureChoice>>())).ToArray();
  var sections=CategoryLayout.Build(allVms);var requests=sections.Single(s=>s.Key=="audio").Tabs.Single(t=>t.Title=="Requests");
  Check(requests.Groups.Sum(g=>g.Readouts.Count)==3&&requests.Groups.All(g=>g.Controls.Count==0),"whole catalog navigation separates readouts");
  var gate=models[2].Definition;
  string[] labels=Enumerable.Range(0,8).Select(m=>FeatureFormatting.Format(gate,m)).ToArray();
  Check(labels.Distinct().Count()==8,"every reason set distinct");
  Check(labels[0]=="No sampled admission limit","zero is bounded observation");
  for(int m=1;m<=7;++m){
   var components=labels[m].ToLowerInvariant().Split(';',StringSplitOptions.TrimEntries).ToHashSet();
   var expected=new HashSet<string>();
   if(m%2==1)expected.Add("new requests inhibited");
   if(m is 2 or 3 or 6 or 7)expected.Add("pool reserve reached");
   if(m>=4)expected.Add("per-pass limit reached");
   Check(components.SetEquals(expected),"display reason membership");
  }
  foreach(double bad in new[]{-1d,8d,.5,double.NaN,double.PositiveInfinity,double.NegativeInfinity})
   Check(FeatureFormatting.Format(gate,bad)=="Unknown","invalid mask never indicates availability");
  Check(FeatureFormatting.Format(models[0].Definition,80)=="80 / 80","capacity unit");
  Check(host.Calls==0,"no transport calls in observation path");
  Check(models[2].Definition.Description.Contains("does not guarantee playback")&&models[2].Definition.RestoreBehavior.Contains("does not synchronize"),"explicit limits in product wording");
  var report=new{status="PASS",checks,gameAccess=false,windowsCreated=0,scope="Actual Core profile/catalog logic and linked production FeatureVm/formatting/navigation. No application window or game connection. Product assembly packaging is outside this fixture."};
  var json=JsonSerializer.Serialize(report,new JsonSerializerOptions{WriteIndented=true});
  System.IO.File.WriteAllText(args[0],json+"\n");Console.WriteLine(json);return 0;
 }
}
