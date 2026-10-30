using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using CczRandomizer.Wpf.Core;
using Microsoft.Win32;

namespace CczRandomizer.Wpf;

public sealed class RunPage : UserControl
{
    private readonly Window _owner;
    private readonly RuleDocumentStore _rules;
    private readonly Func<string> _directory;
    private readonly Action<string> _changeDirectory;
    private readonly TextBlock _summary = new() { TextWrapping = TextWrapping.Wrap, LineHeight = 26 };
    private readonly TextBlock _status = new() { Text = "准备就绪", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 18, 0, 8) };
    private readonly TextBlock _scores = new() { TextWrapping = TextWrapping.Wrap, LineHeight = 25 };
    private readonly StackPanel _configuration = new();
    private readonly ComboBox _count = new() { Width = 90, ItemsSource = Enumerable.Range(1, 15), SelectedItem = 1 };
    private readonly ComboBox _workers = new() { Width = 90, ItemsSource = Enumerable.Range(1, 15), SelectedItem = 1 };
    private readonly CheckBox _loop = new() { Content = "循环随机", VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(16, 0, 0, 0) };
    private readonly CheckBox _compatibility = new() { Content = "兼容模式", ToolTip = "每次随机重新启动游戏，适合无法稳定复用读档的客户端。速度会稍慢。", VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(16, 0, 0, 0) };
    private bool _loadingPreferences;
    private readonly Button _start = new() { Content = "开始随机" };
    private readonly Button _stop = new() { Content = "停止", IsEnabled = false };
    private readonly Button _details = new() { Content = "评分详情", IsEnabled = false };
    private readonly ProgressBar _progress = new() { Height = 4, Minimum = 0, Maximum = 1, Margin = new Thickness(0, 12, 0, 12) };
    private CancellationTokenSource? _cancellation;
    private JsonObject? _latest;
    public Task? ActiveRun { get; private set; }
    public bool IsRunning => _cancellation is not null;
    public event Action<bool>? RunningChanged;

    public RunPage(Window owner, RuleDocumentStore rules, Func<string> directory, Action<string> changeDirectory)
    {
        _owner = owner; _rules = rules; _directory = directory; _changeDirectory = changeDirectory;
        var panel = new StackPanel();
        _configuration.Children.Add(_summary);
        var path = new TextBox { Text = directory(), IsReadOnly = true, MinWidth = 300, VerticalContentAlignment = VerticalAlignment.Center };
        var pathRow = new DockPanel { Margin = new Thickness(0, 20, 0, 24) };
        var browse = new Button { Content = "选择游戏目录" };
        DockPanel.SetDock(browse, Dock.Right); pathRow.Children.Add(browse); pathRow.Children.Add(path);
        browse.Click += (_, _) =>
        {
            var dialog = new OpenFileDialog { Title = "选择游戏目录中的 Ekd5.exe", Filter = "游戏程序|Ekd5.exe" };
            if (dialog.ShowDialog(owner) != true) return;
            try { changeDirectory(Path.GetDirectoryName(dialog.FileName)!); path.Text = directory(); RefreshRules(); LoadPreferences(); }
            catch (Exception error) { MessageBox.Show(owner, error.Message, "读取规则失败"); }
        };
        _configuration.Children.Add(pathRow);
        var options = new WrapPanel();
        options.Children.Add(new TextBlock { Text = "结果数量", VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 8, 0) });
        options.Children.Add(_count);
        options.Children.Add(new TextBlock { Text = "并发数量", VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(20, 0, 8, 0) });
        options.Children.Add(_workers); options.Children.Add(_loop); options.Children.Add(_compatibility); _configuration.Children.Add(options);
        _configuration.Children.Add(new TextBlock { Text = "从第 20 栏读取源存档。合格结果写入第 1 栏起，原栏位备份和每轮结果均保留。", TextWrapping = TextWrapping.Wrap, Foreground = Brushes.SlateGray, Margin = new Thickness(0, 12, 0, 22) });
        panel.Children.Add(_configuration);
        var actions = new WrapPanel(); actions.Children.Add(_start); actions.Children.Add(_stop); actions.Children.Add(_details); panel.Children.Add(actions);
        panel.Children.Add(_status); panel.Children.Add(_progress); panel.Children.Add(_scores);
        _start.Click += async (_, _) => { if (IsRunning) return; ActiveRun = RunAsync(); await ActiveRun; };
        _stop.Click += (_, _) => Stop();
        _details.Click += (_, _) => { if (_latest is not null) new HistoryResultWindow(owner, _latest) { Title = "评分详情" }.ShowDialog(); };
        Content = new ScrollViewer { Content = panel, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        RefreshRules();
        LoadPreferences();
        _count.SelectionChanged += (_, _) => SavePreferences(); _workers.SelectionChanged += (_, _) => SavePreferences();
        _loop.Checked += (_, _) => SavePreferences(); _loop.Unchecked += (_, _) => SavePreferences();
        _compatibility.Checked += (_, _) => SavePreferences(); _compatibility.Unchecked += (_, _) => SavePreferences();
    }
    private RuntimePreferences Preferences => new((int)_count.SelectedItem, (int)_workers.SelectedItem, _loop.IsChecked == true, _compatibility.IsChecked == true);
    private void LoadPreferences()
    {
        _loadingPreferences = true;
        try
        {
            var settings = RuntimePreferences.Load(_directory());
            _count.SelectedItem = settings.ResultCount; _workers.SelectedItem = settings.Workers;
            _loop.IsChecked = settings.Loop; _compatibility.IsChecked = settings.CompatibilityMode;
        }
        catch (Exception error) { _status.Text = $"运行参数读取失败：{error.Message}"; }
        finally { _loadingPreferences = false; }
    }
    private void SavePreferences()
    {
        if (_loadingPreferences || IsRunning) return;
        try { Preferences.Save(_directory()); }
        catch (Exception error) { _status.Text = $"运行参数保存失败：{error.Message}"; }
    }
    public void RefreshRules()
    {
        if (_rules.Path is null) { _summary.Text = "规则尚未加载，请修复规则文件后重新选择游戏目录。"; _start.IsEnabled = false; return; }
        _start.IsEnabled = !IsRunning;
        var people = _rules.ActiveProfile["threePerson"]!["qualifiedMembers"]!.AsArray().Select(x => x!.GetValue<string>());
        _summary.Text = $"当前规则：{_rules.ActiveProfileName}\n参与人物：{string.Join("、", people)}";
    }
    public void Stop()
    {
        _cancellation?.Cancel(); _stop.IsEnabled = false;
        if (IsRunning) _status.Text = "正在停止并释放游戏实例…";
    }
    private async Task RunAsync()
    {
        using var cancellation = new CancellationTokenSource();
        _cancellation = cancellation; _configuration.IsEnabled = false; _start.IsEnabled = false; _stop.IsEnabled = true;
        _latest = null; _details.IsEnabled = false; _scores.Text = ""; _progress.IsIndeterminate = true;
        RunningChanged?.Invoke(true);
        try
        {
            var native = Path.Combine(AppContext.BaseDirectory, "native");
            var settings = Preferences;
            var options = new RandomRunOptions(_directory(), native, settings.ResultCount, Workers: settings.Workers, Loop: settings.Loop, CompatibilityMode: settings.CompatibilityMode);
            var progress = new Progress<RunProgress>(value =>
            {
                if (_cancellation != cancellation || cancellation.IsCancellationRequested) return;
                _status.Text = $"第 {value.Round} 轮 · {value.Message} · 已保存 {value.SavedCount} 份";
                if (value.Snapshot is not null)
                {
                    _latest = value.Snapshot; _details.IsEnabled = true;
                    _scores.Text = ScorePresentation.Summary(value.Snapshot);
                }
            });
            var outcome = await new RandomRunService(imageWriter: ResultImageRenderer.WriteAsync).RunAsync(options, _rules.Document, progress, cancellation.Token);
            _status.Text = $"已完成 {outcome.Rounds} 轮，保存 {outcome.SavedCount} 份合格结果。";
            _progress.Value = 1;
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { _status.Text = "已停止，已保存的合格结果保留在历史记录中。"; }
        catch (Exception error) { _status.Text = $"运行未完成：{error.Message}"; }
        finally
        {
            _cancellation = null; _configuration.IsEnabled = true; _start.IsEnabled = true; _stop.IsEnabled = false; _progress.IsIndeterminate = false;
            RunningChanged?.Invoke(false);
        }
    }
}
