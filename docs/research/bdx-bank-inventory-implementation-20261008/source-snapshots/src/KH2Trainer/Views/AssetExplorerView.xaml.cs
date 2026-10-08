using System.Windows.Controls;
using System.Windows;
using System.Windows.Media;
using System.Windows.Threading;

namespace KH2Trainer;
public partial class AssetExplorerView : UserControl
{
    public AssetExplorerView() => InitializeComponent();
    private void ScriptInstructions_SelectionChanged(object sender,SelectionChangedEventArgs e) => ScrollToScriptSelection();
    private void ScriptEvent_SelectionChanged(object sender,SelectionChangedEventArgs e) => ScrollToScriptSelection();
    private void ScrollToScriptSelection()
    {
        // Event selection updates the viewmodel first; wait for its item binding.
        Dispatcher.BeginInvoke(DispatcherPriority.ContextIdle,new Action(()=>{
            if(ScriptInstructions.SelectedItem is {} selected) {
                ScriptInstructions.UpdateLayout();
                ScriptInstructions.ScrollIntoView(selected);
                // Recycled containers can still represent the old filtered viewport.
                if(FindScrollViewer(ScriptInstructions) is {} scroll) {
                    int index=ScriptInstructions.Items.IndexOf(selected);
                    if(index<scroll.VerticalOffset||index>=scroll.VerticalOffset+scroll.ViewportHeight)
                        scroll.ScrollToVerticalOffset(index);
                }
            }
        }));
    }
    private static ScrollViewer? FindScrollViewer(DependencyObject parent)
    {
        for(int i=0;i<VisualTreeHelper.GetChildrenCount(parent);i++) {
            var child=VisualTreeHelper.GetChild(parent,i);
            if(child is ScrollViewer viewer)return viewer;
            if(FindScrollViewer(child) is {} nested)return nested;
        }
        return null;
    }
}
