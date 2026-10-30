using System.Globalization;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using CczRandomizer.Wpf.Core;

namespace CczRandomizer.Wpf;

public sealed class StageGatesEditor : UserControl
{
    private sealed record ModeOption(string Key, string Label);
    private static readonly ModeOption[] Modes = [new("count", "指定人数达标"), new("average", "平均分达标"), new("total", "总分达标")];
    private readonly ComboBox _jobMode = ModeBox(), _skillMode = ModeBox();
    private readonly TextBox _jobThreshold = Entry(), _jobCount = Entry(), _skillThreshold = Entry(), _skillCount = Entry();
    private readonly RuleDocumentStore _store;
    public StageGatesEditor(RuleDocumentStore store)
    {
        _store = store;
        var profile = store.ActiveProfile;
        var job = profile["threePerson"]!;
        var skill = profile["skillQualification"];
        var all = job["jobQualificationMode"]?.GetValue<string>() == "all";
        _jobMode.SelectedValue = all ? "count" : job["jobQualificationMode"]?.GetValue<string>() ?? "average";
        _skillMode.SelectedValue = skill?["mode"]?.GetValue<string>() ?? "total";
        _jobThreshold.Text = (job["minJobAverage"]?.GetValue<double>() ?? 7.4).ToString(CultureInfo.CurrentCulture);
        _skillThreshold.Text = (skill?["threshold"]?.GetValue<double>() ?? 5).ToString(CultureInfo.CurrentCulture);
        _jobCount.Text = (all ? job["qualifiedMembers"]!.AsArray().Count : job["minQualifiedCount"]?.GetValue<int>() ?? 1).ToString();
        _skillCount.Text = (skill?["requiredCount"]?.GetValue<int>() ?? 1).ToString();
        var grid = new Grid { Margin = new Thickness(0, 12, 0, 18) };
        foreach (var width in new[] { 100d, 110, 180, 100 }) grid.ColumnDefinitions.Add(new() { Width = new GridLength(width) });
        for (var i = 0; i < 3; i++) grid.RowDefinitions.Add(new() { Height = GridLength.Auto });
        Place(grid, new TextBlock { Text = "合格分" }, 0, 1);
        Place(grid, new TextBlock { Text = "算分模式" }, 0, 2);
        Place(grid, new TextBlock { Text = "达标人数" }, 0, 3);
        AddRow(grid, "兵种评分", 1, _jobThreshold, _jobMode, _jobCount);
        AddRow(grid, "特技评分", 2, _skillThreshold, _skillMode, _skillCount);
        _jobMode.SelectionChanged += (_, _) => UpdateCount();
        _skillMode.SelectionChanged += (_, _) => UpdateCount();
        UpdateCount(); Content = grid;
    }
    private void UpdateCount()
    {
        _jobCount.IsEnabled = _jobMode.SelectedValue as string == "count";
        _skillCount.IsEnabled = _skillMode.SelectedValue as string == "count";
    }
    public void Apply()
    {
        if (!double.TryParse(_jobThreshold.Text, out var jobThreshold) || !double.TryParse(_skillThreshold.Text, out var skillThreshold) ||
            !int.TryParse(_jobCount.Text, out var jobCount) || !int.TryParse(_skillCount.Text, out var skillCount)) throw new ArgumentException("合格分须为数字，达标人数须为整数");
        _store.SetGates((string)_jobMode.SelectedValue, jobThreshold, jobCount, (string)_skillMode.SelectedValue, skillThreshold, skillCount);
    }
    private static TextBox Entry() => new() { Margin = new Thickness(0, 4, 12, 4), Padding = new Thickness(6) };
    private static ComboBox ModeBox() => new() { ItemsSource = Modes, DisplayMemberPath = "Label", SelectedValuePath = "Key", Margin = new Thickness(0, 4, 12, 4), Padding = new Thickness(6) };
    private static void Place(Grid grid, UIElement element, int row, int column) { Grid.SetRow(element, row); Grid.SetColumn(element, column); grid.Children.Add(element); }
    private static void AddRow(Grid grid, string label, int row, TextBox threshold, ComboBox mode, TextBox count)
    {
        Place(grid, new TextBlock { Text = label, VerticalAlignment = VerticalAlignment.Center }, row, 0);
        Place(grid, threshold, row, 1); Place(grid, mode, row, 2); Place(grid, count, row, 3);
    }
}
