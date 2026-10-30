using System.Windows;
using System.Windows.Controls;
using CczRandomizer.Wpf.Core;

namespace CczRandomizer.Wpf;

public partial class StorageCleanupWindow : Window
{
    private readonly StorageCleanupService _service;
    private bool _busy;
    public StorageCleanupWindow(Window owner, string gameDirectory)
    {
        Owner = owner;
        InitializeComponent();
        _service = new(gameDirectory);
        Loaded += async (_, _) => await RefreshAsync();
    }

    private async Task RefreshAsync(string[]? cleanup = null)
    {
        if (_busy) return;
        _busy = true;
        IsEnabled = false;
        try
        {
            var outcome = await Task.Run(() =>
            {
                var result = cleanup is null ? null : _service.Clean(cleanup);
                return (Rows: _service.Scan(), Result: result);
            });
            Rows.Children.Clear();
            foreach (var usage in outcome.Rows)
            {
                var row = new DockPanel { Margin = new Thickness(0, 6, 0, 6) };
                var clear = new Button { Content = $"清理{usage.Name}", IsEnabled = usage.Files > 0 };
                clear.Click += async (_, _) => await RefreshAsync([usage.Category]);
                DockPanel.SetDock(clear, Dock.Right);
                row.Children.Add(clear);
                row.Children.Add(new TextBlock { Text = $"{usage.Name}  {Format(usage.Total)}\n可清理 {Format(usage.Cleanable)}", VerticalAlignment = VerticalAlignment.Center });
                Rows.Children.Add(row);
            }
            if (outcome.Result?.Failed > 0) MessageBox.Show(this, $"{outcome.Result.Failed} 个文件暂时无法清理，可稍后重试。", "空间清理");
        }
        catch (Exception error) { MessageBox.Show(this, error.Message, "空间清理失败"); }
        finally { _busy = false; IsEnabled = true; }
    }
    private async void ClearAll_Click(object sender, RoutedEventArgs e) => await RefreshAsync(["logs", "screenshots", "sandboxes"]);
    private static string Format(long bytes) => bytes switch
    {
        >= 1024L * 1024 * 1024 => $"{bytes / 1024d / 1024 / 1024:0.##} GB",
        >= 1024 * 1024 => $"{bytes / 1024d / 1024:0.##} MB",
        >= 1024 => $"{bytes / 1024d:0.##} KB", _ => $"{bytes} B"
    };
}
