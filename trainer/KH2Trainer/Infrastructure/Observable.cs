using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Windows;
using System.Windows.Input;

namespace KH2Trainer;

public abstract class Observable : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;
    protected void Changed([CallerMemberName] string? name = null) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    protected void Changed(params string[] names) { foreach (string name in names) Changed(name); }
    protected bool Set<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value; Changed(name); return true;
    }
}

/// <summary>Runs one asynchronous operation at a time and reports failures instead of crashing.</summary>
public sealed class AsyncCommand(Func<Task> execute, Func<bool>? canExecute = null) : ICommand
{
    /// <summary>Where command failures are shown. The main window routes them to its notification bar.</summary>
    public static Action<Exception> ReportError { get; set; } =
        e => MessageBox.Show(e.Message, "KH2 Trainer", MessageBoxButton.OK, MessageBoxImage.Information);

    private bool busy;
    public event EventHandler? CanExecuteChanged;
    public bool IsRunning => busy;
    public bool CanExecute(object? parameter) => !busy && (canExecute?.Invoke() ?? true);
    public async void Execute(object? parameter)
    {
        if (!CanExecute(parameter)) return;
        busy = true; Refresh();
        try { await execute(); }
        catch (Exception e) { ReportError(e); }
        finally { busy = false; Refresh(); }
    }
    public void Refresh() => CanExecuteChanged?.Invoke(this, EventArgs.Empty);
}

public sealed class RelayCommand(Action execute, Func<bool>? canExecute = null) : ICommand
{
    public event EventHandler? CanExecuteChanged;
    public bool CanExecute(object? parameter) => canExecute?.Invoke() ?? true;
    public void Execute(object? parameter) { if (CanExecute(parameter)) execute(); }
    public void Refresh() => CanExecuteChanged?.Invoke(this, EventArgs.Empty);
}
