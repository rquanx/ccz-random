using System.IO;
using System.Windows;
using System.Windows.Controls;
using CczRandomizer.Wpf.Core;

namespace CczRandomizer.Wpf;

public partial class StorageCleanupWindow : Window
{
    private readonly (string Key, string Name, string Path)[] _targets;
    private StorageCleanupService Service => new(AppContext.BaseDirectory);
    public StorageCleanupWindow(Window owner)
    {
        Owner = owner; InitializeComponent();
        var root = AppContext.BaseDirectory;
        _targets = [("sandboxes", "沙箱", Path.Combine(root, "ccz_fast_data", "sandboxes")), ("logs", "日志", Path.Combine(root, "ccz_fast_logs")), ("screenshots", "故障截图", Path.Combine(root, "ccz_fast_logs"))];
        Render();
    }
    private void Render()
    {
        Rows.Children.Clear();
        foreach (var target in _targets)
        {
            var row = new DockPanel { Margin = new Thickness(0, 5, 0, 5) };
            var usage = Service.Scan().FirstOrDefault(x => x.Category == target.Key);
            var size = new TextBlock { Text = Format(usage?.Total ?? 0), Width = 110, HorizontalAlignment = HorizontalAlignment.Right, Foreground = System.Windows.Media.Brushes.SlateGray };
            DockPanel.SetDock(size, Dock.Right); row.Children.Add(size);
            var clear = new Button { Content = $"清理{target.Name}", Tag = target.Key, Padding = new Thickness(10, 5, 10, 5) }; clear.Click += Clear_Click; DockPanel.SetDock(clear, Dock.Right); row.Children.Add(clear);
            row.Children.Add(new TextBlock { Text = target.Name, VerticalAlignment = VerticalAlignment.Center }); Rows.Children.Add(row);
        }
    }
    private void Clear_Click(object sender, RoutedEventArgs e) { if (sender is Button button && button.Tag is string category) { Service.Clean(category); Render(); } }
    private void ClearAll_Click(object sender, RoutedEventArgs e) { Service.Clean(_targets.Select(x => x.Key).ToArray()); Render(); }
    private static string Format(long bytes) => bytes switch { > 1024 * 1024 * 1024 => $"{bytes / 1024d / 1024 / 1024:0.##} GB", > 1024 * 1024 => $"{bytes / 1024d / 1024:0.##} MB", > 1024 => $"{bytes / 1024d:0.##} KB", _ => $"{bytes} B" };
}
