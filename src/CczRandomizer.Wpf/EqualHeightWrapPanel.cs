using System.Windows;
using System.Windows.Controls;

namespace CczRandomizer.Wpf;

/// <summary>Cards wrap by available width; each visual row stretches to its tallest card.</summary>
public sealed class EqualHeightWrapPanel : Panel
{
    private const double PreferredWidth = 260;
    protected override Size MeasureOverride(Size availableSize)
    {
        var width = double.IsFinite(availableSize.Width) ? Math.Max(1, availableSize.Width) : PreferredWidth;
        var columns = Math.Max(1, (int)(width / PreferredWidth));
        var cardWidth = width / columns;
        double height = 0, rowHeight = 0;
        for (var i = 0; i < InternalChildren.Count; i++)
        {
            var child = InternalChildren[i]; child.Measure(new Size(cardWidth, double.PositiveInfinity));
            rowHeight = Math.Max(rowHeight, child.DesiredSize.Height);
            if ((i + 1) % columns == 0 || i == InternalChildren.Count - 1) { height += rowHeight; rowHeight = 0; }
        }
        return new(width, height);
    }
    protected override Size ArrangeOverride(Size finalSize)
    {
        var columns = Math.Max(1, (int)(finalSize.Width / PreferredWidth));
        var cardWidth = finalSize.Width / columns;
        double top = 0;
        for (var start = 0; start < InternalChildren.Count; start += columns)
        {
            var count = Math.Min(columns, InternalChildren.Count - start);
            var height = Enumerable.Range(start, count).Max(i => InternalChildren[i].DesiredSize.Height);
            for (var i = 0; i < count; i++) InternalChildren[start + i].Arrange(new Rect(i * cardWidth, top, cardWidth, height));
            top += height;
        }
        return finalSize;
    }
}
