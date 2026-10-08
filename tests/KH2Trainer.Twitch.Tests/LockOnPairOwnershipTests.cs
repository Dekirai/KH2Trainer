using KH2Trainer.Core;
using KH2Trainer.Twitch;

internal static class LockOnPairOwnershipTests
{
    private sealed class Harness
    {
        public readonly FakeGame Game;
        public readonly FakeSink Sink = new();
        public readonly EffectEngine Engine;
        public DateTimeOffset Now = new(2026, 10, 7, 12, 0, 0, TimeSpan.Zero);
        public bool PauseTimers = true;
        public Harness(IReadOnlyList<FeatureDefinition> features)
        {
            Game = new(features);
            Engine = new(Game, new(features), EffectCatalog.All,
                key => { var d = EffectCatalog.Find(key)!; return new(d.Title, d.DurationSeconds, d.Amount, SameEffectBehavior.Extend, ConflictBehavior.Queue); },
                () => new(TimeSpan.FromMinutes(10), 600, PauseTimers), Sink, _ => { }, _ => Task.CompletedTask);
        }
        public void Redeem(string key, string id = "a") => Engine.Submit(new(id,key,"Viewer","",Now));
        public Task Tick(double dt = .25) { Now = Now.AddSeconds(dt); return Engine.TickAsync(Now); }
        public Task End(string key) => Engine.EndEffectAsync(key,Now);
    }
    private static uint Bits(float value) => BitConverter.SingleToUInt32Bits(value);
    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool,string> check)
    {
        Decoder(check);
        var map = new FeatureMap(features);
        foreach (var key in new[] { "eagle-eye", "short-sighted" })
        {
            var definition = EffectCatalog.Find(key)!;
            float appliedScale = key == "eagle-eye" ? 4f : .15f;
            EffectContext Context(FakeGame game) => new(definition,new("a",key,"Viewer","",DateTimeOffset.UtcNow),60,0,game,map,new(1),_ => Task.CompletedTask);
            check(definition.AllowedRoles == EffectPlayerRoles.Sora && !definition.Features.Contains("targeting.search_scale"), key+": Sora-only paired ownership replaces scalar writes");
            foreach (float originalBreak in new[] { 777.25f, 2000.5f, 6501f, 10_000_000f })
            {
                var game = new FakeGame(features);game.Set("targeting.search_scale",1.2345678f);game.Set("targeting.break_distance",originalBreak);
                var context=Context(game); await definition.Start(context);
                check(game.Get("targeting.search_scale")==appliedScale && game.Get("targeting.break_distance")==appliedScale*2000.5f,key+": apply exact Float32 product");
                await context.SustainAsync();game.Set("targeting.default_break_distance",3000.25f);
                check(await context.RestoreAsync()==0&&!context.HasPendingRestores,key+": exact original pair restores after parameter default changes");
                check(Bits((float)game.Get("targeting.search_scale")!.Value)==Bits(1.2345678f)&&Bits((float)game.Get("targeting.break_distance")!.Value)==Bits(originalBreak),key+": custom original break is preserved, never recalculated");
                await context.RestoreAsync();check(game.LockOnWrites==2&&game.Count("targeting.search_scale")==0&&game.Count("targeting.break_distance")==0,key+": no scalar cleanup or repeated restore");
            }
            foreach (bool breakOnly in new[] { false,true })
            {
                var game=new FakeGame(features);var context=Context(game);await definition.Start(context);
                string id=breakOnly?"targeting.break_distance":"targeting.search_scale";
                game.Set(id,MathF.BitIncrement((float)game.Get(id)!.Value));
                var foreign=game.LockOnPair;await context.SustainAsync();await context.RestoreAsync();
                check(game.LockOnPair==foreign&&game.LockOnWrites==1&&!context.HasPendingRestores,key+": one-ULP "+id+" takeover preserves whole pair");
            }
            foreach (var role in new[] { PlayerRole.Roxas,PlayerRole.Mickey,PlayerRole.Other,PlayerRole.Unknown })
            {
                var h=new Harness(features);h.Game.Gameplay=new(true,role,GameplayBlockers.None);h.Redeem(key);await h.Tick();
                check(h.Game.Commands.Count==0&&h.Engine.PendingEffects.Count==1,key+": unsupported "+role+" waits without widened compatibility");
            }
            foreach (bool optOut in new[] { false,true })
            {
                var h=new Harness(features){PauseTimers=!optOut};h.Redeem(key);await h.Tick();double remaining=h.Engine.ActiveEffects.Single().RemainingSeconds;
                h.Game.LockOnSnapshotAvailable=false;await h.Tick();await h.Tick();
                check(h.Engine.ActiveEffects.Single().RemainingSeconds==remaining,key+": missing pair pauses even timer opt-out="+optOut);
                h.Game.LockOnSnapshotAvailable=true;await h.Tick();check(h.Engine.ActiveEffects.Single().RemainingSeconds==remaining,key+": missing interval never charged on return");
                h.Game.Gameplay=new(true,PlayerRole.Sora,GameplayBlockers.Menu);await h.Tick();await h.Tick();
                check(h.Engine.ActiveEffects.Single().RemainingSeconds==remaining&&h.Game.LockOnWrites==1,key+": owned pair during menu also pauses timer opt-out="+optOut);
                h.Game.Set("targeting.break_distance",1234.5);await h.Tick();await h.Tick();
                check(h.Engine.ActiveEffects.Single().RemainingSeconds==remaining&&h.Game.LockOnWrites==1,key+": foreign pair during menu does not count or get reapplied");
                h.Game.Gameplay=new(true,PlayerRole.Sora,GameplayBlockers.None);await h.Tick();
                check(h.Engine.ActiveEffects.Count==0&&h.Game.Get("targeting.break_distance")==1234.5&&h.Game.LockOnWrites==1,key+": control return ends on takeover without overwriting either field");
            }
            {
                var game=new FakeGame(features);game.Set("targeting.break_distance",777.25);var context=Context(game);
                game.BeforeLockOnDispatch=a=> { if(a[0]==0)game.NativeLockOnOverride=(1,888.5f); };
                bool failed=false;try{await definition.Start(context);}catch(InvalidOperationException){failed=true;}
                check(failed&&!context.HasPendingRestores&&game.LockOnWrites==0,key+": definite native rejection has no ownership");
                await context.RestoreAsync();check(!context.HasPendingRestores&&game.NativeLockOnOverride==(1f,888.5f)&&game.LockOnWrites==0,key+": stale-apply cleanup is acknowledged no-op preserving native edit");
            }
            {
                var game=new FakeGame(features);var context=Context(game);
                game.BeforeLockOnDispatch=a=>{if(a[0]==0)game.NativeLockOnOverride=(appliedScale,appliedScale*2000.5f);};
                bool rejected=false;try{await definition.Start(context);}catch(BridgeCommandRejectedException e){rejected=e.Code==4;}
                await context.RestoreAsync();
                check(rejected&&!context.HasPendingRestores&&game.NativeLockOnOverride==(appliedScale,appliedScale*2000.5f)&&game.Commands.Count==1&&game.LockOnWrites==0,
                    key+": foreign pair already equal to desired is preserved after definite mismatch ACK");
            }
            foreach(int code in new[]{1,2,3,4,99})
            {
                var game=new FakeGame(features);var context=Context(game);
                game.BeforeLockOnDispatch=_=>throw new BridgeCommandRejectedException(code,"synthetic native status");
                try{await definition.Start(context);}catch(BridgeCommandRejectedException){}
                check(context.HasPendingRestores==(code is not (2 or 3 or 4)),key+": only proven pre-write native status releases intent: "+code);
            }
            {
                var game=new FakeGame(features);var context=Context(game);await definition.Start(context);
                game.NativeLockOnOverride=(appliedScale,9000.125f);game.LockOnSnapshotAvailable=false;
                await context.RestoreAsync();check(!context.HasPendingRestores&&game.NativeLockOnOverride==(appliedScale,9000.125f)&&game.LockOnWrites==1,key+": native comparison protects post-snapshot break edit without host readback");
            }
            {
                var game=new FakeGame(features);var context=Context(game);await definition.Start(context);
                game.Reject=(f,a)=>f=="targeting.pair_compare_apply"&&a[0]==1;
                check(await context.RestoreAsync()==1&&context.HasPendingRestores,key+": cleanup reject retains intent");
                game.IsConnected=false;check(await context.RestoreAsync()==1&&context.HasPendingRestores,key+": disconnect cannot settle cleanup");
                game.IsConnected=true;game.Reject=null;await context.RestoreAsync();check(!context.HasPendingRestores&&game.LockOnWrites==2,key+": acknowledged retry restores once");
            }
            foreach(bool failedStart in new[]{false,true})
            {
                var h=new Harness(features);h.Game.Set("targeting.break_distance",777.25);
                h.Game.AfterExecute=(f,a)=>{if(f=="targeting.pair_compare_apply"&&a[0]==0&&failedStart)throw new TimeoutException("Apply ACK lost");};
                h.Game.Reject=(f,a)=>f=="targeting.pair_compare_apply"&&a[0]==1;
                h.Redeem(key);await h.Tick();if(!failedStart)await h.End(key);
                check(h.Engine.PendingCleanupCount==1&&h.Game.LockOnWrites==1,key+": "+(failedStart?"failed start":"end")+" retains intent");
                for(int i=0;i<205;i++)await h.Tick(1);
                check(h.Engine.PendingCleanupCount==1&&h.Game.LockOnWrites==1,key+": ambiguous cleanup survives ordinary 180-second window without another apply");
                h.Game.Reject=null;h.Game.AfterExecute=null;await h.Engine.StopAllAsync("test stop",h.Now);await h.Tick(1);
                check(h.Engine.PendingCleanupCount==0&&h.Game.Get("targeting.break_distance")==777.25,key+": delayed ACK settles exact original after long retry");
            }
            {
                var h=new Harness(features);h.Redeem(key);await h.Tick();bool lost=true;
                h.Game.AfterExecute=(f,a)=>{if(f=="targeting.pair_compare_apply"&&a[0]==1&&lost){lost=false;throw new TimeoutException("Restore ACK lost");}};
                await h.End(key);check(h.Engine.PendingCleanupCount==1&&h.Game.LockOnWrites==2,key+": lost restore ACK retained even though original already visible");
                await h.Tick(1);check(h.Engine.PendingCleanupCount==0&&h.Game.LockOnWrites==2,key+": subsequent native mismatch ACK is terminal no-op");
            }
            foreach(int missing in new[]{475,476,373})
            {
                var h=new Harness(features);h.Game.Unsupported.Add(missing);h.Redeem(key);await h.Tick();
                check(h.Game.LockOnWrites==0,key+": missing required capability "+missing+" blocks before write");
            }
            foreach(double value in new[]{double.NaN,double.PositiveInfinity,-1d,0d,10000001d})
            {
                var game=new FakeGame(features);game.Set("targeting.break_distance",value);var context=Context(game);
                check(definition.Check!(context).Kind==ReadinessKind.Wait,key+": invalid original distance waits "+value);
            }
        }
    }

    private static void Decoder(Action<bool,string> check)
    {
        TrainerSnapshot Snapshot()
        {
            var s=new TrainerSnapshot{Connected=true,ProtocolVersion=4,SceneReady=true,Status=1};
            foreach(var (slot,value) in new (int,double)[]{(463,1000),(475,Bits(1.25f)),(476,Bits(777.25f)),(373,2000.5)})
            {s.Values[slot]=value;s.Valid[slot/64]|=1UL<<(slot%64);s.Supported[slot/64]|=1UL<<(slot%64);}
            return s;
        }
        var good=Snapshot();var result=LockOnPairSnapshot.FromSnapshot(good,1000);
        check(result.Available&&result.ScaleBits==Bits(1.25f)&&result.BreakBits==Bits(777.25f)&&result.RetainBits==Bits(2000.5f),"lock-on decoder: coherent raw bits and exact float default");
        foreach(int slot in new[]{463,475,476,373})
        {
            var s=Snapshot();s.Valid[slot/64]&=~(1UL<<(slot%64));check(!LockOnPairSnapshot.FromSnapshot(s,1000).Available,"lock-on decoder: required valid bit "+slot);
            s=Snapshot();s.Supported[slot/64]&=~(1UL<<(slot%64));check(!LockOnPairSnapshot.FromSnapshot(s,1000).Available,"lock-on decoder: required capability "+slot);
        }
        foreach(int slot in new[]{475,476})foreach(double invalid in new[]{-1d,.5,4294967296d,double.NaN,double.PositiveInfinity,(double)Bits(float.NaN),(double)Bits(float.PositiveInfinity),0})
        {
            var s=Snapshot();s.Values[slot]=invalid;check(!LockOnPairSnapshot.FromSnapshot(s,1000).Available,"lock-on decoder: malformed/nonfinite/zero float bits rejected "+slot);
        }
        foreach(double invalid in new[]{0d,-1d,1000001d,2000.5000000001,double.NaN,double.PositiveInfinity})
        {var s=Snapshot();s.Values[373]=invalid;check(!LockOnPairSnapshot.FromSnapshot(s,1000).Available,"lock-on decoder: bounded exactly-Float32 native default");}
        foreach(var s in new[]{good with{Connected=false},good with{ProtocolVersion=3},good with{SceneReady=false},good with{Status=0},good with{ErrorCode=1}})
            check(!LockOnPairSnapshot.FromSnapshot(s,1000).Available,"lock-on decoder: disconnected/legacy/not-ready publication rejected");
        check(!LockOnPairSnapshot.FromSnapshot(good,2001).Available&&LockOnPairSnapshot.FromSnapshot(good,2000).Available,"lock-on decoder: precise freshness bound");
        check(!LockOnPairSnapshot.FromSnapshot(good,999).Available,"lock-on decoder: future publication rejected");
    }
}
