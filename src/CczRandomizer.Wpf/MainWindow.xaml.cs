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
    private readonly RuleDocumentStore _documentStore = new();
    private readonly RunPage _runPage;
    private bool _closingAfterStop;
    private string _gameDirectory = GameDirectorySettings.Discover(AppContext.BaseDirectory, Environment.GetEnvironmentVariable("CCZ_GAME_DIR"));

    public MainWindow()
    {
        InitializeComponent();
        try { _documentStore.Load(Path.Combine(_gameDirectory, "random_rules_v2.json")); }
        catch (Exception error)
        {
            Loaded += (_, _) => MessageBox.Show(this, $"无法读取规则，原文件未修改。请修复 random_rules_v2.json 后重新选择游戏目录。\n{error.Message}", "读取规则失败", MessageBoxButton.OK, MessageBoxImage.Error);
        }
        _runPage = new RunPage(this, _documentStore, () => _gameDirectory, directory =>
        {
            _documentStore.Load(Path.Combine(directory, "random_rules_v2.json"));
            _gameDirectory = directory;
            try { GameDirectorySettings.Remember(directory); }
            catch (Exception error) { MessageBox.Show(this, $"游戏目录已选择，但无法记住路径：{error.Message}", "路径保存失败"); }
        });
        _runPage.RunningChanged += running => RulesNavigation.IsEnabled = !running;
        Closing += async (_, e) =>
        {
            if (_closingAfterStop || !_runPage.IsRunning) return;
            e.Cancel = true;
            _runPage.Stop();
            if (_runPage.ActiveRun is { } run) await run;
            _closingAfterStop = true; Close();
        };
        ShowPage("run");
    }

    private void Navigate_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: "history" }) { new HistoryWindow(this, _gameDirectory).ShowDialog(); return; }
        if (sender is Button button && button.Tag is string page) ShowPage(page);
    }

    private void ShowPage(string page)
    {
        if (page == "run") _runPage.RefreshRules();
        PageSubtitle.Text = page == "run" ? "按所选人物评分，合格后保存并读回验证。" : "";
        PageContent.Content = page switch
        {
            "rules" => BuildRulesPage(),
            "help" => BuildHelpPage(),
            _ => _runPage,
        };
        PageTitle.Text = page switch { "rules" => "规则设置", "history" => "历史记录", "help" => "常见问题", _ => "随机运行" };
    }

    private UIElement BuildRulesPage()
    {
        if (_documentStore.Path is null) return BuildInfoPage("规则设置", "请先在随机运行页面选择包含 random_rules_v2.json 的游戏目录。");
        var panel = new StackPanel();
        panel.Children.Add(new ProfileToolbar(this, _documentStore, () => ShowPage("rules")));
        var draft = _documentStore.CreateDraft();
        panel.Children.Add(new TextBlock { Text = "阶段门槛", FontSize = 22, FontWeight = FontWeights.SemiBold });
        var gates = new StageGatesEditor(draft);
        gates.IsEnabled = !draft.IsBuiltin;
        if (draft.IsBuiltin) panel.Children.Add(new TextBlock { Text = "内置规则只读，请先复制再修改。", Margin = new Thickness(0, 8, 0, 8) });
        panel.Children.Add(gates);
        var selected = draft.ActiveProfile["threePerson"]!["qualifiedMembers"]!.AsArray().Select(x => x!.GetValue<string>()).ToHashSet(StringComparer.Ordinal);
        var members = LoadAllMemberNames();
        panel.Children.Add(new TextBlock { Text = "人物设置", FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 4, 0, 8) });
        var settingsActions = new WrapPanel { Margin = new Thickness(0, 0, 0, 12) };
        var selectionSummary = new TextBlock { Text = string.Join("、", selected), TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 20) };
        var choose = new Button { Content = "选择人物" };
        choose.Click += (_, _) =>
        {
            var dialog = new MemberSelectionWindow(this, members, selected);
            if (dialog.ShowDialog() == true) { selected = dialog.SelectedMembers.ToHashSet(); selectionSummary.Text = string.Join("、", selected); }
        };
        settingsActions.Children.Add(choose);
        foreach (var (label, tab) in new[] { ("设置人物倾向", 2), ("兵种基础设置", 0), ("特技基础设置", 1) })
        {
            var button = new Button { Content = label };
            button.Click += (_, _) =>
            {
                var dialog = new RuleSettingsWindow(this, draft.ActiveProfile, members, tab);
                if (dialog.ShowDialog() == true) draft.ReplaceActiveProfile(dialog.EditedProfile!);
            };
            settingsActions.Children.Add(button);
        }
        panel.Children.Add(settingsActions);
        settingsActions.IsEnabled = !draft.IsBuiltin;
        panel.Children.Add(selectionSummary);
        var saveMembers = new Button { Content = "保存规则", HorizontalAlignment = HorizontalAlignment.Left, IsEnabled = !draft.IsBuiltin };
        saveMembers.Click += (_, _) =>
        {
            var values = selected.ToArray();
            if (values.Length == 0) { MessageBox.Show("至少选择一名人物。", "人物设置", MessageBoxButton.OK, MessageBoxImage.Warning); return; }
            var previous = (System.Text.Json.Nodes.JsonObject)draft.Document.DeepClone();
            try
            {
                draft.SetQualifiedMembers(values);
                gates.Apply();
                RuleImporter.ValidateProfile(draft.ActiveProfile);
                draft.Save();
                _documentStore.Load(draft.Path!);
                MessageBox.Show(this, "规则已保存。", "规则设置", MessageBoxButton.OK, MessageBoxImage.Information);
            }
            catch (Exception error) { draft.RestoreDraft(previous); MessageBox.Show(this, error.Message, "保存失败", MessageBoxButton.OK, MessageBoxImage.Error); }
        };
        panel.Children.Add(saveMembers);
        return new ScrollViewer { Content = panel, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
    }

    private static IReadOnlyList<string> LoadAllMemberNames()
    {
        return FixedEntryCatalog.CreateRows().Select(x => x.Name).Concat(RecruitmentCatalog.Bundled.People.Select(x => x.Name)).Distinct().ToArray();
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
        var panel = (StackPanel)BuildInfoPage("运行准备", "在许子将处完成随机前配置，存入第 20 栏。随机后无需选择招募版设置，工具会直接保存。源第 20 栏不会被工具覆盖。");
        var sourceHelp = new Button { Content = "查看第 20 栏准备示意图", HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 12, 0, 0) };
        sourceHelp.Click += (_, _) => new Window
        {
            Owner = this, Title = "第 20 栏源存档准备", Width = 850, Height = 650, WindowStartupLocation = WindowStartupLocation.CenterOwner,
            Content = new ScrollViewer { Content = new Image { Source = new System.Windows.Media.Imaging.BitmapImage(new Uri("pack://application:,,,/CczRandomizer.Wpf;component/resources/source_slot_20_help.png")), Stretch = Stretch.Uniform } }
        }.ShowDialog();
        panel.Children.Add(sourceHelp);
        panel.Children.Add(new TextBlock { Text = "评分规则", FontSize = 20, Margin = new Thickness(0, 24, 0, 8) });
        panel.Children.Add(new TextBlock { Text = "兵种与特技使用同一组所选人物。先检查兵种，再检查特技，两项均达标才保留。指定人数：每人达到合格分，达标人数达到要求；平均分：所选人物平均分达标；总分：所选人物分数相加达标。兵种高分不会跳过特技。人物倾向加成受兵种类型与基础分门槛影响。启用特技类型匹配时，文官兵种不计武官型特技，武官兵种不计文官型特技。", TextWrapping = TextWrapping.Wrap, LineHeight = 26 });
        panel.Children.Add(new TextBlock { Text = "存档与故障处理", FontSize = 20, Margin = new Thickness(0, 24, 0, 8) });
        panel.Children.Add(new TextBlock { Text = "每轮结果、图片和被替换的旧存档保存在 randResult；历史记录只展示合格结果。停止或异常不会删除已保存结果。运行失败时，可查看游戏目录下 ccz_fast_logs 的日志。空间清理只处理旧日志、故障截图和已结束的沙箱，不删除结果或历史。", TextWrapping = TextWrapping.Wrap, LineHeight = 26 });
        var cleanup = new Button { Content = "打开空间清理", HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 22, 0, 0) };
        cleanup.Click += (_, _) => new StorageCleanupWindow(this, _gameDirectory).ShowDialog();
        panel.Children.Add(cleanup);
        var sound = new Button { Content = "游戏没声音", HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 12, 0, 0) };
        sound.Click += async (_, _) =>
        {
            if (MessageBox.Show(this, "请先启动正常游戏并进入能播放声音的界面。此操作只恢复所选游戏目录中正常 Ekd5.exe 的静音状态，不调整音量或其他应用。", "游戏声音修复", MessageBoxButton.OKCancel, MessageBoxImage.Information) != MessageBoxResult.OK) return;
            sound.IsEnabled = false;
            try { var result = await Task.Run(() => AudioRepairService.Repair(_gameDirectory)); MessageBox.Show(this, result.Message, "游戏声音修复"); }
            catch (Exception error) { MessageBox.Show(this, error.Message, "游戏声音修复失败"); }
            finally { sound.IsEnabled = true; }
        };
        panel.Children.Add(sound);
        return new ScrollViewer { Content = panel, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
    }
}
