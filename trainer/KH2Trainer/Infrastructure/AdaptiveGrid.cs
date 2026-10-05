using System.Windows;
using System.Windows.Controls;

namespace KH2Trainer;

/// <summary>
/// Lays children out in equal-width columns. The column count follows the
/// available width, so tiles fill the row instead of leaving a ragged edge.
/// </summary>
public sealed class AdaptiveGrid : Panel
{
    public static readonly DependencyProperty MinColumnWidthProperty = DependencyProperty.Register(nameof(MinColumnWidth), typeof(double), typeof(AdaptiveGrid),
        new FrameworkPropertyMetadata(260.0, FrameworkPropertyMetadataOptions.AffectsMeasure));
    public static readonly DependencyProperty MaxColumnsProperty = DependencyProperty.Register(nameof(MaxColumns), typeof(int), typeof(AdaptiveGrid),
        new FrameworkPropertyMetadata(0, FrameworkPropertyMetadataOptions.AffectsMeasure));
    public static readonly DependencyProperty ColumnSpacingProperty = DependencyProperty.Register(nameof(ColumnSpacing), typeof(double), typeof(AdaptiveGrid),
        new FrameworkPropertyMetadata(0.0, FrameworkPropertyMetadataOptions.AffectsMeasure));
    public static readonly DependencyProperty RowSpacingProperty = DependencyProperty.Register(nameof(RowSpacing), typeof(double), typeof(AdaptiveGrid),
        new FrameworkPropertyMetadata(0.0, FrameworkPropertyMetadataOptions.AffectsMeasure));

    public double MinColumnWidth { get => (double)GetValue(MinColumnWidthProperty); set => SetValue(MinColumnWidthProperty, value); }
    public int MaxColumns { get => (int)GetValue(MaxColumnsProperty); set => SetValue(MaxColumnsProperty, value); }
    public double ColumnSpacing { get => (double)GetValue(ColumnSpacingProperty); set => SetValue(ColumnSpacingProperty, value); }
    public double RowSpacing { get => (double)GetValue(RowSpacingProperty); set => SetValue(RowSpacingProperty, value); }

    private List<UIElement> VisibleChildren() => InternalChildren.Cast<UIElement>().Where(c => c.Visibility != Visibility.Collapsed).ToList();

    private int ColumnsFor(double width, int count)
    {
        int columns = double.IsFinite(width) && width > 0
            ? (int)Math.Floor((width + ColumnSpacing) / (Math.Max(1, MinColumnWidth) + ColumnSpacing))
            : 2;
        if (MaxColumns > 0) columns = Math.Min(columns, MaxColumns);
        return Math.Max(1, Math.Min(columns, Math.Max(1, count)));
    }

    private double ColumnWidth(double width, int columns) => double.IsFinite(width)
        ? Math.Max(0, (width - ColumnSpacing * (columns - 1)) / columns)
        : MinColumnWidth;

    protected override Size MeasureOverride(Size available)
    {
        foreach (UIElement child in InternalChildren) if (child.Visibility == Visibility.Collapsed) child.Measure(new Size(0, 0));
        var children = VisibleChildren();
        if (children.Count == 0) return new Size(0, 0);
        int columns = ColumnsFor(available.Width, children.Count);
        double columnWidth = ColumnWidth(available.Width, columns), height = 0;
        for (int start = 0; start < children.Count; start += columns)
        {
            double row = 0;
            for (int i = start; i < Math.Min(start + columns, children.Count); i++)
            {
                children[i].Measure(new Size(columnWidth, double.PositiveInfinity));
                row = Math.Max(row, children[i].DesiredSize.Height);
            }
            height += row + (start > 0 ? RowSpacing : 0);
        }
        double width = double.IsFinite(available.Width) ? available.Width : columns * columnWidth + ColumnSpacing * (columns - 1);
        return new Size(width, height);
    }

    protected override Size ArrangeOverride(Size final)
    {
        var children = VisibleChildren();
        if (children.Count == 0) return final;
        int columns = ColumnsFor(final.Width, children.Count);
        double columnWidth = ColumnWidth(final.Width, columns), y = 0;
        for (int start = 0; start < children.Count; start += columns)
        {
            int end = Math.Min(start + columns, children.Count);
            double row = 0;
            for (int i = start; i < end; i++) row = Math.Max(row, children[i].DesiredSize.Height);
            for (int i = start; i < end; i++)
                children[i].Arrange(new Rect((i - start) * (columnWidth + ColumnSpacing), y, columnWidth, row));
            y += row + RowSpacing;
        }
        return final;
    }
}
