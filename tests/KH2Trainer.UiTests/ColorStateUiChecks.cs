using System.IO;
using KH2Trainer;
using KH2Trainer.Core;

internal static class ColorStateUiChecks
{
    public static object Run()
    {
        using var stream=typeof(FeatureVm).Assembly.GetManifestResourceStream("KH2Trainer.Data.features.json")
            ?? throw new InvalidDataException("Embedded feature catalog missing.");
        var feature=FeatureCatalog.Load(stream).Single(f=>f.Id=="display.color_state");
        int checks=0;
        void Check(bool ok) {++checks;if(!ok)throw new InvalidDataException("Color observation label is incorrect.");}
        Check(FeatureFormatting.Format(feature,0)=="Off");
        for(int mode=1;mode<=3;++mode) for(int strength=1;strength<=10;++strength)
            Check(FeatureFormatting.Format(feature,mode*16+strength)==$"Mode {mode} · {strength}/10");
        foreach(double invalid in new[]{-1,1,10,16,27,31,32,43,48,59,100,double.NaN,double.PositiveInfinity,17.5})
            Check(FeatureFormatting.Format(feature,invalid)=="Unknown");
        return new {success=true,checks,scope="Coherent color observation labels for every valid pair and invalid encodings."};
    }
}
