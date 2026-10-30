using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using CczRandomizer.Wpf.Core;

namespace CczRandomizer.Wpf;

public sealed class HistoryWindow : Window
{
    private readonly string _directory;
    private HistoryRepository? _repository;
    private readonly DataGrid _rounds = new() { AutoGenerateColumns = false, IsReadOnly = true, CanUserAddRows = false, EnableRowVirtualization = true, SelectionMode = DataGridSelectionMode.Single };
    private readonly ListBox _results = new() { DisplayMemberPath = "Label", MinHeight = 110 };
    private readonly TextBlock _pageText = new() { VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(12, 0, 12, 0) };
    private int _page = 1, _request;
    private sealed record ResultRow(string Label, JsonObject Snapshot);

    public HistoryWindow(Window owner, string directory)
    {
        Owner = owner; _directory = directory; Title = "历史记录"; WindowStartupLocation = WindowStartupLocation.CenterOwner;
        Width = 940; Height = 680; MinWidth = 640; MinHeight = 480;
        var root = new DockPanel { Margin = new Thickness(24) };
        var toolbar = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 14) };
        Add(toolbar, "上一页", async () => { if (_page > 1) { _page--; await LoadAsync(); } });
        toolbar.Children.Add(_pageText);
        Add(toolbar, "下一页", async () => { if (_repository is not null && _page * 20 < await Task.Run(_repository.CountRounds)) { _page++; await LoadAsync(); } });
        Add(toolbar, "刷新", LoadAsync);
        Add(toolbar, "删除所选记录", async () =>
        {
            if (_rounds.SelectedItem is not HistoryRound selected || _repository is null) return;
            if (MessageBox.Show(this, "删除所选历史记录？存档和结果图片将保留。", "历史记录", MessageBoxButton.YesNo) != MessageBoxResult.Yes) return;
            await Task.Run(() => _repository.DeleteRound(selected.Id)); await LoadAsync();
        });
        Add(toolbar, "清空记录", async () =>
        {
            if (_repository is null || MessageBox.Show(this, "清空全部历史记录？存档和结果图片将保留。", "历史记录", MessageBoxButton.YesNo) != MessageBoxResult.Yes) return;
            await Task.Run(_repository.Clear); _page = 1; await LoadAsync();
        });
        DockPanel.SetDock(toolbar, Dock.Top); root.Children.Add(toolbar);
        var bottom = new DockPanel { Height = 180, Margin = new Thickness(0, 16, 0, 0) };
        var details = new Button { Content = "查看存档详情", HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 8, 0, 0) };
        details.Click += (_, _) => ShowDetail(); DockPanel.SetDock(details, Dock.Bottom); bottom.Children.Add(details);
        bottom.Children.Add(_results); DockPanel.SetDock(bottom, Dock.Bottom); root.Children.Add(bottom);
        foreach (var (header, path) in new[] { ("开始时间", "StartedAt"), ("规则", "RuleName"), ("轮次", "RoundNumber"), ("合格结果", "ResultCount"), ("状态", "Status") })
            _rounds.Columns.Add(new DataGridTextColumn { Header = header, Binding = new Binding(path), Width = new DataGridLength(1, DataGridLengthUnitType.Star) });
        _rounds.SelectionChanged += async (_, _) => await LoadResultsAsync();
        _results.MouseDoubleClick += (_, _) => ShowDetail();
        root.Children.Add(_rounds); Content = root;
        Loaded += async (_, _) => await Guard(LoadAsync);
        Closed += (_, _) => _request++;
    }
    private void Add(Panel parent, string label, Func<Task> action)
    {
        var button = new Button { Content = label }; button.Click += async (_, _) => { button.IsEnabled = false; try { await Guard(action); } finally { button.IsEnabled = true; } }; parent.Children.Add(button);
    }
    private async Task Guard(Func<Task> action) { try { await action(); } catch (Exception error) { MessageBox.Show(this, error.Message, "历史记录读取失败"); } }
    private async Task LoadAsync()
    {
        var page = _page;
        var data = await Task.Run(() =>
        {
            var repository = _repository ?? new HistoryRepository(_directory);
            var total = repository.CountRounds();
            var validPage = Math.Min(page, Math.Max(1, (total + 19) / 20));
            return (repository, total, validPage, rows: repository.ListRounds(validPage));
        });
        if (!IsVisible) return;
        _repository = data.repository; _page = data.validPage;
        _pageText.Text = $"{_page} / {Math.Max(1, (data.total + 19) / 20)}";
        _rounds.ItemsSource = data.rows; _results.ItemsSource = null;
        if (data.rows.Count > 0) _rounds.SelectedIndex = 0;
    }
    private async Task LoadResultsAsync()
    {
        var request = ++_request;
        _results.ItemsSource = null;
        if (_repository is null || _rounds.SelectedItem is not HistoryRound selected) return;
        await Guard(async () =>
        {
            var results = await Task.Run(() => _repository.GetResults(selected.Id).Select(snapshot => new ResultRow(
                $"第 {snapshot["slot"]} 栏 · {string.Join("、", HistoryMembers.Resolve(snapshot).Select(x => x["name"]!.GetValue<string>()))}", snapshot)).ToArray());
            if (request != _request || !IsVisible) return;
            _results.ItemsSource = results;
            if (results.Length > 0) _results.SelectedIndex = 0;
        });
    }
    private void ShowDetail() { if (_results.SelectedItem is ResultRow row) new HistoryResultWindow(this, row.Snapshot).ShowDialog(); }
}
