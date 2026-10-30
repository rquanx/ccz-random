using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace CczRandomizer.Wpf;

public partial class MainWindow : Window
{
    private readonly RuleStore _rules = new();

    public MainWindow()
    {
        InitializeComponent();
        _rules.TryLoad();
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
            "help" => BuildInfoPage("常见问题", "这里会保留空间清理、存档路径和运行故障说明。"),
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
        panel.Children.Add(new Button { Content = "开始迁移后的随机流程", IsEnabled = false, Margin = new Thickness(0, 22, 0, 0), HorizontalAlignment = HorizontalAlignment.Left });
        return panel;
    }

    private UIElement BuildRulesPage()
    {
        var panel = new StackPanel();
        panel.Children.Add(new TextBlock { Text = "当前规则概览", FontSize = 22, FontWeight = FontWeights.SemiBold });
        panel.Children.Add(new TextBlock { Text = "规则编辑器会先迁移为独立 ViewModel，保持 random_rules_v2.json 格式兼容。", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 20), Foreground = FindResource("MutedBrush") as Brush });
        foreach (var member in _rules.QualifiedMembers) panel.Children.Add(new TextBlock { Text = $"• {member}", FontSize = 15, Margin = new Thickness(0, 4, 0, 4) });
        return panel;
    }

    private static UIElement BuildInfoPage(string title, string description)
    {
        var panel = new StackPanel();
        panel.Children.Add(new TextBlock { Text = title, FontSize = 22, FontWeight = FontWeights.SemiBold });
        panel.Children.Add(new TextBlock { Text = description, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 0), Foreground = Brushes.SlateGray });
        return panel;
    }
}
