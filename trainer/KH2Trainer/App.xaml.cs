using System.Windows;

namespace KH2Trainer;
public partial class App : Application
{
    private Mutex? instance;
    protected override void OnStartup(StartupEventArgs e)
    {
        if (e.Args.Length == 2 && e.Args[0] == "--verify-package")
        {
            try { PackageVerification.WriteReport(e.Args[1]); Shutdown(0); }
            catch { Shutdown(1); }
            return;
        }
        instance = new Mutex(true, "Local\\KH2Trainer.Desktop", out bool created);
        if (!created) { MessageBox.Show("KH2 Trainer is already open.", "KH2 Trainer"); Shutdown(); return; }
        DispatcherUnhandledException += (_, args) => { MessageBox.Show(args.Exception.Message, "KH2 Trainer", MessageBoxButton.OK, MessageBoxImage.Information); args.Handled = true; };
        base.OnStartup(e);
    }
    protected override void OnExit(ExitEventArgs e) { if (instance != null) { try { instance.ReleaseMutex(); } catch (ApplicationException) { } instance.Dispose(); } base.OnExit(e); }
}
