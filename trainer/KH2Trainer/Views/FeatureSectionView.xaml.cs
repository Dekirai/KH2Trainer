using System.Windows.Controls;

namespace KH2Trainer;

public partial class FeatureSectionView : UserControl
{
    public FeatureSectionView() => InitializeComponent();

    private void TabChanged(object sender, SelectionChangedEventArgs e) => Scroller.ScrollToTop();
}
