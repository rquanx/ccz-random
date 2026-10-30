using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;
using System.IO;
using Microsoft.Win32;
using CczRandomizer.Wpf.Core;

namespace CczRandomizer.Wpf;

public partial class MainWindow : Window
{
    private readonly RuleStore _rules = new();
    private readonly RuleDocumentStore _documentStore = new();
    private readonly GameSandboxService _sandboxService = new();
    private string? _sandboxPath;

    public MainWindow()
    {
        InitializeComponent();
        _rules.TryLoad();
        if (_rules.FilePath is not null) _documentStore.Load(_rules.FilePath);
        ShowPage("run");
    }

    private void Navigate_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button button && button.Tag is string page) ShowPage(page);
    }

    private void ShowPage(string page)
    {
        PageContent.Content = page switch
        {
            "rules" => BuildRulesPage(),
            "history" => BuildInfoPage("历史记录", "历史结果查看将在迁移历史数据库后接入。"),
            "help" => BuildHelpPage(),
            _ => BuildRunPage(),
        };
        PageTitle.Text = page switch { "rules" => "规则设置", "history" => "历史记录", "help" => "常见问题", _ => "随机运行" };
    }

    private UIElement BuildRunPage()
    {
        var panel = new StackPanel();
        panel.Children.Add(new TextBlock { Text = "2.2 随机运行", FontSize = 22, FontWeight = FontWeights.SemiBold });
        panel.Children.Add(new TextBlock { Text = "WPF 迁移第一阶段已完成窗口与规则文件读取。运行控制、内存读取和评分流程将按模块迁移.", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 22), Foreground = FindResource("MutedBrush") as Brush });
        var status = new Border { Padding = new Thickness(18), Background = new SolidColorBrush(Color.FromRgb(241, 245, 249)), CornerRadius = new CornerRadius(12) };
        status.Child = new TextBlock { Text = _rules.FilePath is null ? "未找到 random_rules_v2.json" : $"已读取规则：{_rules.ActiveProfileName}\n参与人物：{string.Join("、", _rules.QualifiedMembers)}\n兵种门槛：{_rules.JobThreshold:0.##}（{_rules.JobMode}）", LineHeight = 24 };
        panel.Children.Add(status);
        panel.Children.Add(new TextBlock { Text = "游戏目录", FontSize = 15, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 24, 0, 8) });
        var gamePath = new TextBox { Text = Environment.GetEnvironmentVariable("CCZ_GAME_DIR") ?? string.Empty, Padding = new Thickness(8), MinWidth = 420 };
        var pathRow = new StackPanel { Orientation = Orientation.Horizontal };
        pathRow.Children.Add(gamePath);
        var browse = new Button { Content = "选择目录", Margin = new Thickness(10, 0, 0, 0) };
        browse.Click += (_, _) =>
        {
            var dialog = new OpenFileDialog { Title = "选择游戏目录中的 Ekd5.exe", Filter = "游戏程序|Ekd5.exe" };
            if (dialog.ShowDialog() == true) gamePath.Text = Path.GetDirectoryName(dialog.FileName) ?? string.Empty;
        };
        pathRow.Children.Add(browse); panel.Children.Add(pathRow);
        var launch = new Button { Content = "创建沙箱并启动游戏", Margin = new Thickness(0, 18, 0, 0), HorizontalAlignment = HorizontalAlignment.Left };
        launch.Click += (_, _) =>
        {
            try
            {
                if (!Directory.Exists(gamePath.Text)) throw new DirectoryNotFoundException("游戏目录不存在。");
                _sandboxPath = _sandboxService.Create(gamePath.Text);
                GameSandboxService.StartGame(_sandboxPath);
                MessageBox.Show($"沙箱已启动：\n{_sandboxPath}", "随机运行", MessageBoxButton.OK, MessageBoxImage.Information);
            }
            catch (Exception error) { MessageBox.Show(error.Message, "启动失败", MessageBoxButton.OK, MessageBoxImage.Error); }
        };
        panel.Children.Add(launch);
        var recruits = new Button { Content = "查看入队人员", Margin = new Thickness(0, 14, 0, 0), HorizontalAlignment = HorizontalAlignment.Left };
        recruits.Click += (_, _) => new RecruitmentWindow(this).ShowDialog();
        panel.Children.Add(recruits);
        return panel;
    }

    private UIElement BuildRulesPage()
    {
        var panel = new StackPanel();
        panel.Children.Add(new TextBlock { Text = "当前规则概览", FontSize = 22, FontWeight = FontWeights.SemiBold });
        panel.Children.Add(new TextBlock { Text = "规则编辑器会先迁移为独立 ViewModel，保持 random_rules_v2.json 格式兼容。", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 20), Foreground = FindResource("MutedBrush") as Brush });
        var thresholdRow = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 18) };
        thresholdRow.Children.Add(new TextBlock { Text = "兵种门槛", Width = 110, VerticalAlignment = VerticalAlignment.Center });
        var threshold = new TextBox { Text = _rules.JobThreshold.ToString("0.##"), Width = 100, Padding = new Thickness(8) };
        thresholdRow.Children.Add(threshold);
        var save = new Button { Content = "保存规则", Margin = new Thickness(12, 0, 0, 0) };
        save.Click += (_, _) =>
        {
            if (!double.TryParse(threshold.Text, out var value) || value < 0 || value > 20)
            {
                MessageBox.Show("请输入 0 到 20 之间的数字。", "规则设置", MessageBoxButton.OK, MessageBoxImage.Warning); return;
            }
            try { _documentStore.SetJobThreshold(value); _documentStore.Save(); MessageBox.Show("规则已保存。", "规则设置", MessageBoxButton.OK, MessageBoxImage.Information); }
            catch (Exception error) { MessageBox.Show(error.Message, "保存失败", MessageBoxButton.OK, MessageBoxImage.Error); }
        };
        thresholdRow.Children.Add(save); panel.Children.Add(thresholdRow);
        var selected = _rules.QualifiedMembers.ToHashSet(StringComparer.Ordinal);
        var members = LoadAllMemberNames();
        var memberGrid = new UniformGrid { Columns = 6, Margin = new Thickness(0, 0, 0, 16) };
        foreach (var member in members)
        {
            var check = new CheckBox { Content = member, IsChecked = selected.Contains(member), Margin = new Thickness(4, 5, 10, 5) };
            memberGrid.Children.Add(check);
        }
        panel.Children.Add(new TextBlock { Text = "关注人物", FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 4, 0, 8) });
        panel.Children.Add(new ScrollViewer { Height = 300, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Content = memberGrid });
        var saveMembers = new Button { Content = "保存人物设置", HorizontalAlignment = HorizontalAlignment.Left };
        saveMembers.Click += (_, _) =>
        {
            var values = memberGrid.Children.OfType<CheckBox>().Where(x => x.IsChecked == true).Select(x => x.Content?.ToString() ?? "").Where(x => x.Length > 0).ToArray();
            if (values.Length == 0) { MessageBox.Show("至少选择一名人物。", "人物设置", MessageBoxButton.OK, MessageBoxImage.Warning); return; }
            try { _documentStore.SetQualifiedMembers(values); _documentStore.Save(); MessageBox.Show("人物设置已保存。", "人物设置", MessageBoxButton.OK, MessageBoxImage.Information); }
            catch (Exception error) { MessageBox.Show(error.Message, "保存失败", MessageBoxButton.OK, MessageBoxImage.Error); }
        };
        panel.Children.Add(saveMembers);
        return panel;
    }

    private static IReadOnlyList<string> LoadAllMemberNames()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "resources", "data", "recruitment", "recruits_2.2.json");
        try { return RecruitmentCatalog.Load(path).People.Select(x => x.Name).Concat(FixedEntryCatalog.CreateRows().Select(x => x.Name)).Distinct().ToArray(); }
        catch { return FixedEntryCatalog.CreateRows().Select(x => x.Name).ToArray(); }
    }

    private static UIElement BuildInfoPage(string title, string description)
    {
        var panel = new StackPanel();
        panel.Children.Add(new TextBlock { Text = title, FontSize = 22, FontWeight = FontWeights.SemiBold });
        panel.Children.Add(new TextBlock { Text = description, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 0), Foreground = Brushes.SlateGray });
        return panel;
    }

    private UIElement BuildHelpPage()
    {
        var panel = (StackPanel)BuildInfoPage("常见问题", "这里保留空间清理、存档路径和运行故障说明。");
        var cleanup = new Button { Content = "打开空间清理", HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 22, 0, 0) };
        cleanup.Click += (_, _) => new StorageCleanupWindow(this).ShowDialog();
        panel.Children.Add(cleanup);
        return panel;
    }
}
