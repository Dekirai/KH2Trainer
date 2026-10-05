using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Threading;

namespace KH2Trainer;

public partial class MainWindow : Window
{
    private readonly MainViewModel model;
    private bool shutDown;
    private Task? closing;

    public MainWindow()
    {
        InitializeComponent();
        DataContext = model = new MainViewModel();
        // Show command failures in the notification bar instead of modal dialogs.
        AsyncCommand.ReportError = e => model.Notify(e.Message, true);
        // Logoff or Windows shutdown does not wait for an async close; give Twitch a short, bounded moment.
        Application.Current.SessionEnding += (_, _) => WaitBriefly(model.ShutdownAsync(), TimeSpan.FromSeconds(3));
    }

    // Clicking the current section while searching returns to it.
    private void NavigationClicked(object sender, MouseButtonEventArgs e) => model.Search = "";

    private void FocusSearch(object sender, ExecutedRoutedEventArgs e)
    {
        SearchBox.Focus();
        SearchBox.SelectAll();
    }

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);
        var handle = new WindowInteropHelper(this).Handle;
        int enabled = 1;
        // Windows 10/11 keep the native caption buttons and resizing behavior.
        if (DwmSetWindowAttribute(handle, 20, ref enabled, sizeof(int)) < 0)
            DwmSetWindowAttribute(handle, 19, ref enabled, sizeof(int));
        // Windows 11 supports explicit caption and text colors; older versions
        // ignore these attributes and still use immersive dark mode above.
        int caption = 0x001E1612, text = 0x00F5EEE9;
        DwmSetWindowAttribute(handle, 35, ref caption, sizeof(int));
        DwmSetWindowAttribute(handle, 36, ref text, sizeof(int));
    }

    [DllImport("dwmapi.dll", PreserveSig = true)]
    private static extern int DwmSetWindowAttribute(IntPtr window, int attribute, ref int value, int size);

    // Twitch needs a moment to end effects and pause rewards; the window closes once that is done.
    protected override void OnClosing(CancelEventArgs e)
    {
        base.OnClosing(e);
        if (shutDown || e.Cancel) return;
        e.Cancel = true;
        closing ??= CloseAfterShutdownAsync(); // Further clicks on X wait for the same shutdown.
    }

    private async Task CloseAfterShutdownAsync()
    {
        IsEnabled = false;
        Title = "KH2 Trainer · closing…";
        try { await model.ShutdownAsync(); }
        catch (Exception) { /* Closing must never fail. */ }
        shutDown = true;
        await Dispatcher.BeginInvoke(Close);
    }

    private static void WaitBriefly(Task task, TimeSpan limit)
    {
        var frame = new DispatcherFrame();
        task.ContinueWith(_ => frame.Continue = false, TaskScheduler.Default);
        var timer = new DispatcherTimer { Interval = limit };
        timer.Tick += (_, _) => { timer.Stop(); frame.Continue = false; };
        timer.Start();
        Dispatcher.PushFrame(frame);
        timer.Stop();
    }

    protected override void OnClosed(EventArgs e)
    {
        model.Dispose();
        base.OnClosed(e);
    }
}
