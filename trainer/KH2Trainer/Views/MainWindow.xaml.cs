using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;

namespace KH2Trainer;

public partial class MainWindow : Window
{
    private readonly MainViewModel model;

    public MainWindow()
    {
        InitializeComponent();
        DataContext = model = new MainViewModel();
        // Show command failures in the notification bar instead of modal dialogs.
        AsyncCommand.ReportError = e => model.Notify(e.Message, true);
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

    protected override void OnClosed(EventArgs e)
    {
        model.Dispose();
        base.OnClosed(e);
    }
}
