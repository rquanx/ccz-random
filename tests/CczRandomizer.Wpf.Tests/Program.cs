using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using CczRandomizer.Wpf;
using CczRandomizer.Wpf.Core;

internal static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        var app = new App { ShutdownMode = ShutdownMode.OnExplicitShutdown };
        app.InitializeComponent();
        SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext(Dispatcher.CurrentDispatcher));
        if (args.Length == 2 && args[0] == "--run-ui-smoke-isolated")
        {
            // The user's normal game may be updating autosaves. Validate against a separate source copy.
            var sourceCopy = new GameSandboxService().Create(args[1], workerName: "independent-source");
            try { TestRealRun(sourceCopy); }
            finally { GameSandboxService.Remove(sourceCopy); app.Shutdown(); }
            return;
        }
        if (args.Length == 2 && args[0] == "--run-ui-smoke")
        {
            try { TestRealRun(args[1]); }
            finally { app.Shutdown(); }
            return;
        }
        var owner = new Window { Width = 900, Height = 700, WindowStartupLocation = WindowStartupLocation.CenterScreen, ShowInTaskbar = false };
        owner.Show();
        try
        {
            var config = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "skill-parity.json")))![0]!["config"]!;
            var profile = (JsonObject)config["profiles"]![config["activeProfile"]!.GetValue<string>()]!;
            var before = profile.ToJsonString();
            var dialog = new RuleSettingsWindow(owner, profile, ["张宝", "曹操"], 1);
            dialog.Show();
            try
            {
                Pump(dialog);
                var grid = Descendants<DataGrid>(dialog).Single();
                if (grid.Items.Count < 100) throw new Exception("特技目录未完整加载");
                var realizedRows = Descendants<DataGridRow>(grid).Count();
                if (realizedRows == 0 || realizedRows >= grid.Items.Count) throw new Exception("特技列表未按视口虚拟化");
                var centerX = dialog.Left + dialog.ActualWidth / 2;
                if (Math.Abs(centerX - (owner.Left + owner.ActualWidth / 2)) > 5) throw new Exception("弹窗未相对主窗口居中");
                var search = Descendants<TextBox>(dialog).Single(x => Equals(x.ToolTip, "按名称筛选"));
                search.Text = "攻击追加";
                Pump(dialog);
                if (grid.Items.Count == 0 || grid.Items.Cast<ScoreSetting>().Any(x => !x.Name.Contains("攻击追加"))) throw new Exception("特技筛选无效");
                ((ScoreSetting)grid.Items[0]).Score = 17;
                search.Text = "";
                Pump(dialog);
                if (!grid.Items.Cast<ScoreSetting>().Any(x => x.Score == 17)) throw new Exception("筛选丢失编辑值");
                var tabs = Descendants<TabControl>(dialog).Single();
                tabs.SelectedIndex = 2;
                Pump(dialog);
                var affinity = Descendants<DataGrid>(dialog).Single();
                if (affinity.Items.Count != 2 || affinity.Columns.Count != 3) throw new Exception("人物倾向列缺失");
                ((AffinitySetting)affinity.Items[0]).PrimaryType = "MASTER";
            }
            finally { dialog.Close(); }
            if (profile.ToJsonString() != before) throw new Exception("关闭弹窗修改原规则");
            TestHistory(owner);
            TestEquipment(owner);
            TestRecruitment(owner);
            TestRunPage(owner);
            TestMainWindow();
            TestImages(owner);
            var talentsWindow = new JobTalentsWindow(owner, new JsonObject());
            talentsWindow.Show();
            try
            {
                Pump(talentsWindow);
                var jobs = Descendants<ListBox>(talentsWindow).Single();
                if (jobs.Items.Count != RuleDefaults.Jobs.Count || jobs.Items.Cast<JobTalentCard>().Any(x => x.Talents is not null)) throw new Exception("历史兵种目录缺失状态错误");
                Descendants<TextBox>(talentsWindow).Single().Text = "道士";
                Pump(talentsWindow);
                if (jobs.Items.Count != 1) throw new Exception("兵种天赋筛选失败");
            }
            finally { talentsWindow.Close(); }
            Console.WriteLine("WPF UI tests passed: centering, virtualized rows, filtering, edit retention, cancel isolation.");
        }
        finally { owner.Close(); app.Shutdown(); }
    }
    private static void TestRealRun(string gameDirectory)
    {
        var protectedFiles = Directory.EnumerateFiles(gameDirectory, "*.json").Concat(Directory.EnumerateFiles(Path.Combine(gameDirectory, "SV"))).ToDictionary(p => p, p => System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(p)));
        var sandbox = new GameSandboxService().Create(gameDirectory, workerName: "wpf-ui-smoke");
        var old = Environment.GetEnvironmentVariable("CCZ_GAME_DIR");
        Environment.SetEnvironmentVariable("CCZ_GAME_DIR", sandbox);
        MainWindow? window = null;
        try
        {
            var rules = RuleDefaults.NewConfig(); var profile = rules["profiles"]![rules["activeProfile"]!.GetValue<string>()]!;
            profile["threePerson"]!["qualifiedMembers"] = new JsonArray("张宝");
            profile["threePerson"]!["minJobAverage"] = 0;
            profile["threePerson"]!["jobQualificationMode"] = "average";
            profile["skillQualification"]!["threshold"] = 0;
            File.WriteAllText(Path.Combine(sandbox, "random_rules_v2.json"), rules.ToJsonString());
            window = new MainWindow(); window.Show(); Pump(window);
            var page = Descendants<RunPage>(window).Single();
            Descendants<Button>(page).Single(x => Equals(x.Content, "开始随机")).RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            var deadline = DateTime.UtcNow.AddMinutes(2);
            while (page.IsRunning && DateTime.UtcNow < deadline) { Pump(window); Thread.Sleep(25); }
            if (page.IsRunning) { page.Stop(); throw new TimeoutException("真实 WPF 随机未在两分钟内完成"); }
            Pump(window);
            var history = new HistoryRepository(sandbox);
            var round = history.ListRounds().Single();
            var result = history.GetResults(round.Id).Single();
            if (round.Status != "completed" || result["save"]!["verified"]!.GetValue<bool>() != true || result["images"]!.AsArray().Count != 1)
                throw new Exception("WPF 运行、读回或图片导出不完整");
            var path = Path.Combine(Environment.CurrentDirectory, "artifacts/wpf-real-run.png");
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            var bitmap = new System.Windows.Media.Imaging.RenderTargetBitmap((int)window.ActualWidth, (int)window.ActualHeight, 96, 96, PixelFormats.Pbgra32);
            bitmap.Render(window); var encoder = new System.Windows.Media.Imaging.PngBitmapEncoder(); encoder.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bitmap));
            using (var output = File.Create(path)) encoder.Save(output);
        }
        finally
        {
            if (window is not null)
            {
                var page = Descendants<RunPage>(window).Single(); page.Stop();
                while (page.IsRunning) { Pump(window); Thread.Sleep(25); }
                window.Close();
            }
            Environment.SetEnvironmentVariable("CCZ_GAME_DIR", old);
            GameSandboxService.Remove(sandbox);
            foreach (var file in protectedFiles)
                if (!System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(file.Key)).SequenceEqual(file.Value)) throw new Exception($"测试期间源文件发生变化（需排查并行游戏或其他写入）：{file.Key}");
        }
        Console.WriteLine("WPF real-game smoke passed: UI start, selected-person scoring, verified save, PNG export and history; source copy hashes unchanged.");
    }
    private static void TestMainWindow()
    {
        var folder = Path.Combine(Path.GetTempPath(), "ccz-main-ui-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        var old = Environment.GetEnvironmentVariable("CCZ_GAME_DIR");
        var store = new RuleDocumentStore(); store.Load(Path.Combine(folder, "random_rules_v2.json"));
        store.CopyProfile("可编辑副本"); store.SelectProfile("默认规则"); store.Save();
        Environment.SetEnvironmentVariable("CCZ_GAME_DIR", folder);
        var window = new MainWindow(); window.Show();
        try
        {
            window.Width = window.MinWidth; window.Height = window.MinHeight;
            Descendants<Button>(window).Single(b => Equals(b.Content, "规则设置")).RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); Pump(window);
            if (Descendants<StageGatesEditor>(window).Single().IsEnabled || Descendants<Button>(window).Single(b => Equals(b.Content, "保存规则")).IsEnabled) throw new Exception("内置规则未只读保护");
            var toolbar = Descendants<ProfileToolbar>(window).Single();
            Descendants<ComboBox>(toolbar).Single().SelectedItem = "可编辑副本"; Pump(window);
            if (!Descendants<StageGatesEditor>(window).Single().IsEnabled || !Descendants<Button>(window).Single(b => Equals(b.Content, "重命名")).IsEnabled) throw new Exception("副本不能编辑");
            var content = Descendants<StageGatesEditor>(window).Single();
            if (content.ActualWidth < 490) throw new Exception("最小窗口截断门槛输入");
            var image = new System.Windows.Media.Imaging.BitmapImage(new Uri("pack://application:,,,/CczRandomizer.Wpf;component/resources/source_slot_20_help.png"));
            if (image.PixelWidth < 100 || image.PixelHeight < 100) throw new Exception("源存档说明图缺失");
            var reloaded = new RuleDocumentStore(); reloaded.Load(store.Path!);
            if (reloaded.ActiveProfileName != "可编辑副本") throw new Exception("界面切换规则没有持久化");
        }
        finally { window.Close(); Environment.SetEnvironmentVariable("CCZ_GAME_DIR", old); Directory.Delete(folder, true); }
    }
    private static void TestRunPage(Window owner)
    {
        var folder = Path.Combine(Path.GetTempPath(), "ccz-run-ui-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        var store = new RuleDocumentStore(); store.Load(Path.Combine(folder, "random_rules_v2.json")); store.SetQualifiedMembers(["张宝"]);
        var page = new RunPage(owner, store, () => folder, _ => { });
        var window = new Window { Owner = owner, Content = page, Width = 950, Height = 650, WindowStartupLocation = WindowStartupLocation.CenterOwner };
        window.Show();
        try
        {
            Pump(window);
            if (!Descendants<TextBlock>(page).Any(x => x.Text.Contains("参与人物：张宝"))) throw new Exception("运行页规则未统一读取");
            store.SetQualifiedMembers(["曹洪"]); page.RefreshRules(); Pump(window);
            if (!Descendants<TextBlock>(page).Any(x => x.Text.Contains("参与人物：曹洪"))) throw new Exception("运行页切换规则未刷新");
            var start = Descendants<Button>(page).Single(x => Equals(x.Content, "开始随机"));
            start.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            var deadline = DateTime.UtcNow.AddSeconds(5);
            while (page.IsRunning && DateTime.UtcNow < deadline) { Pump(window); Thread.Sleep(10); }
            Pump(window);
            if (page.IsRunning || !start.IsEnabled || !Descendants<TextBlock>(page).Any(x => x.Text.StartsWith("运行未完成："))) throw new Exception("启动失败后界面未恢复");
        }
        finally { window.Close(); Directory.Delete(folder, true); }
    }
    private static void TestImages(Window owner)
    {
        var snapshot = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "verified-result.json")))!.AsObject();
        var folder = Path.Combine(Path.GetTempPath(), "ccz-image-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder); snapshot["save"]!["path"] = Path.Combine(folder, "SV001.E5S");
        try
        {
            var files = ResultImageRenderer.WriteAsync(snapshot).GetAwaiter().GetResult();
            if (files.Count != 1) throw new Exception("单选人物结果图片数目错误");
            using var input = File.OpenRead(files[0]);
            var image = System.Windows.Media.Imaging.BitmapFrame.Create(input, System.Windows.Media.Imaging.BitmapCreateOptions.None, System.Windows.Media.Imaging.BitmapCacheOption.OnLoad);
            if (image.PixelWidth != 732 || image.PixelHeight < 500) throw new Exception("结果图片尺寸错误");
            var artifact = Path.Combine(Environment.CurrentDirectory, "artifacts", "wpf-result-sample.png");
            Directory.CreateDirectory(Path.GetDirectoryName(artifact)!); File.Copy(files[0], artifact, true);
            var rows = snapshot["personnel"]!.AsArray().Concat(snapshot["fixedPersonnel"]!.AsArray()).ToArray();
            var people = rows.Select(x => new PersonnelRecord(x!["recordIndex"]!.GetValue<int>(), x["memberId"]!.GetValue<uint>(), x["name"]!.GetValue<string>(),
                x["jobId"]!.GetValue<byte>(), x["currentJobId"]!.GetValue<byte>(), x["jobTalents"]!.AsArray().Select(t => t!.GetValue<string>()).ToArray(), x["personalTalents"]!.AsArray().Select(t => t!.GetValue<string>()).ToArray())).ToArray();
            var rules = RuleDefaults.NewConfig(); var profile = rules["profiles"]![rules["activeProfile"]!.GetValue<string>()]!;
            profile["threePerson"]!["qualifiedMembers"] = new JsonArray(people.Select(x => (JsonNode)JsonValue.Create(x.Name)!).ToArray());
            profile["threePerson"]!["minJobAverage"] = 0; profile["threePerson"]!["jobQualificationMode"] = "average";
            profile["skillQualification"]!["threshold"] = 0;
            var full = ResultSnapshot.Score(rules, new(people, JobTalentCatalog.Read(snapshot), snapshot["equipment"]!.AsObject()), 2, 1).Document;
            full["save"] = new JsonObject { ["path"] = Path.Combine(folder, "SV002.E5S"), ["verified"] = true };
            var watch = System.Diagnostics.Stopwatch.StartNew();
            var details = new HistoryResultWindow(owner, full);
            details.Show();
            try
            {
                Pump(details);
                var list = Descendants<ListBox>(details).Single(); var realized = Descendants<ListBoxItem>(list).Count();
                if (list.Items.Count != 130 || realized == 0 || realized > 20) throw new Exception("全员评分详情未按视口加载");
                details.Width = 600; details.Height = 500; Pump(details);
                list.ScrollIntoView(list.Items[^1]); Pump(details);
                if (!Descendants<TextBlock>(list).Any(x => x.Text.Contains(people[^1].Name))) throw new Exception("全员详情无法查看最后一人");
            }
            finally { details.Close(); }
            var detailMs = watch.ElapsedMilliseconds; watch.Restart();
            var fullFiles = ResultImageRenderer.WriteAsync(full).GetAwaiter().GetResult();
            if (fullFiles.Count != 33) throw new Exception("130 人图片分页缺失");
            foreach (var file in fullFiles)
            {
                using var png = File.OpenRead(file);
                var frame = System.Windows.Media.Imaging.BitmapFrame.Create(png, System.Windows.Media.Imaging.BitmapCreateOptions.None, System.Windows.Media.Imaging.BitmapCacheOption.OnLoad);
                if (frame.PixelHeight is < 500 or > 8192) throw new Exception("全员结果图片尺寸失控");
            }
            File.Copy(fullFiles[^1], Path.Combine(Environment.CurrentDirectory, "artifacts/wpf-result-last-page.png"), true);
            Console.WriteLine($"130-person detail open/resize/scroll: {detailMs} ms; 33 PNG pages: {watch.ElapsedMilliseconds} ms.");
        }
        finally { Directory.Delete(folder, true); }
    }
    private static void TestRecruitment(Window owner)
    {
        var snapshot = new JsonObject
        {
            ["personnel"] = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "personnel.json"))),
            ["fixedPersonnel"] = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "fixed-personnel.json")))
        };
        var catalog = RecruitmentCatalog.Load(Path.Combine(AppContext.BaseDirectory, "resources/data/recruitment/recruits_2.2.json"));
        var people = EntrySnapshot.Read(snapshot, catalog);
        if (people.Count != 130 || people.Select(x => x.Index).Distinct().Count() != 130) throw new Exception("入队目录人数错误");
        foreach (var row in ((JsonArray)snapshot["personnel"]!).Concat((JsonArray)snapshot["fixedPersonnel"]!))
        {
            var person = people.Single(x => x.Index == row!["recordIndex"]!.GetValue<int>());
            var expectedJob = row!["job"]?.GetValue<string>() ?? RuleDefaults.Jobs[row["jobId"]!.GetValue<int>()].Name;
            if (person.Name != row["name"]!.GetValue<string>() || person.Job != expectedJob ||
                !person.PersonalTalents.SequenceEqual(row["personalTalents"]!.AsArray().Select(x => x!.GetValue<string>())))
                throw new Exception("入队卡片未使用本次真实人物信息");
        }
        var groups = EntrySnapshot.Group(people);
        if (groups.Any(x => x.Stage.StartsWith("共通")) || !groups.Any(x => x.Stage == "汜水关之战" && x.People.Any(p => p.Name == "曹洪" && p.Fixed))) throw new Exception("入队关卡分组错误");
        var dialog = new RecruitmentWindow(owner, snapshot);
        dialog.Show();
        try
        {
            Pump(dialog);
            var list = Descendants<ListBox>(dialog).Single();
            var realized = Descendants<ListBoxItem>(list).Count();
            if (realized < 1 || realized >= list.Items.Count) throw new Exception("入队关卡列表未虚拟化");
            Descendants<TextBox>(dialog).Single().Text = "张宝";
            var deadline = DateTime.UtcNow.AddSeconds(3);
            while (DateTime.UtcNow < deadline && list.Items.Cast<EntryGroup>().SelectMany(x => x.People).Any(x => x.Name != "张宝")) { Thread.Sleep(15); Pump(dialog); }
            if (list.Items.Count == 0 || list.Items.Cast<EntryGroup>().SelectMany(x => x.People).Any(x => x.Name != "张宝")) throw new Exception("入队人物搜索失败");
        }
        finally { dialog.Close(); }
        var panel = new EqualHeightWrapPanel();
        foreach (var height in new[] { 30d, 80d, 40d }) panel.Children.Add(new Border { Child = new Border { Height = height } });
        panel.Measure(new Size(600, double.PositiveInfinity)); panel.Arrange(new Rect(0, 0, 600, panel.DesiredSize.Height));
        if (panel.Children[0].RenderSize.Height != 80 || panel.Children[1].RenderSize.Height != 80 || panel.Children[2].TranslatePoint(new Point(), panel).Y != 80) throw new Exception("入队卡片行内等高或换行错误");
        panel.Measure(new Size(300, double.PositiveInfinity)); panel.Arrange(new Rect(0, 0, 300, panel.DesiredSize.Height));
        if (panel.DesiredSize.Height != 150 || panel.Children[2].TranslatePoint(new Point(), panel).Y != 110) throw new Exception("窄窗口卡片没有重新换行");
    }
    private static void TestEquipment(Window owner)
    {
        var equipment = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "equipment.json")))!;
        var snapshot = new JsonObject { ["equipment"] = equipment };
        var dialog = new EquipmentWindow(owner, snapshot);
        dialog.Show();
        try
        {
            Pump(dialog);
            var cards = Descendants<ListBox>(dialog).Single();
            if (cards.Items.Cast<EquipmentCard>().Count(x => !x.Special) != 70) throw new Exception("宝物记录未完整加载");
            if (!cards.Items.Cast<EquipmentCard>().Any(x => x.Special)) throw new Exception("缺少宝物组合");
            var realized = Descendants<ListBoxItem>(cards).Count();
            if (realized < 1 || realized >= cards.Items.Count) throw new Exception("宝物列表未虚拟化");
            var search = Descendants<TextBox>(dialog).Single();
            search.Text = "剑 反击";
            Pump(dialog);
            if (!cards.Items.Cast<EquipmentCard>().Any(x => x.Name == "雌雄双剑") || cards.Items.Cast<EquipmentCard>().Any(x => !EquipmentCatalog.Matches(x, "剑 反击"))) throw new Exception("宝物多词筛选失败");
            search.Text = "不存在的宝物";
            Pump(dialog);
            if (cards.Items.Count != 0 || !Descendants<TextBlock>(dialog).Any(x => x.Text == "没有符合条件的宝物信息。")) throw new Exception("宝物空结果提示缺失");
        }
        finally { dialog.Close(); }
        var missing = new EquipmentWindow(owner, new JsonObject());
        missing.Show();
        try { Pump(missing); if (!Descendants<TextBlock>(missing).Any(x => x.Text == "本次结果未保存宝物信息。")) throw new Exception("旧记录缺失宝物提示错误"); }
        finally { missing.Close(); }
    }
    private static void TestHistory(Window owner)
    {
        var folder = Path.Combine(Path.GetTempPath(), "ccz-history-ui-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(folder, "ccz_fast_data"));
        File.Copy(Path.Combine(AppContext.BaseDirectory, "python-history.sqlite3"), Path.Combine(folder, "ccz_fast_data/history.sqlite3"));
        var dialog = new HistoryWindow(owner, folder);
        try
        {
            dialog.Show();
            var deadline = DateTime.UtcNow.AddSeconds(5);
            ListBox? results = null;
            while (DateTime.UtcNow < deadline)
            {
                Pump(dialog);
                results = Descendants<ListBox>(dialog).SingleOrDefault();
                if (results?.Items.Count > 0) break;
                Thread.Sleep(10);
            }
            if (results?.Items.Count != 1) throw new Exception("历史结果没有异步加载");
            if (Descendants<DataGrid>(dialog).Single().Items.Count != 1) throw new Exception("历史窗口显示空轮次");
            if (Math.Abs(dialog.Left + dialog.ActualWidth / 2 - owner.Left - owner.ActualWidth / 2) > 5) throw new Exception("历史窗口未居中");
            var snapshot = new HistoryRepository(folder).GetResults(new HistoryRepository(folder).ListRounds()[0].Id)[0];
            var details = new HistoryResultWindow(dialog, snapshot);
            details.Show();
            try
            {
                Pump(details);
                var text = Descendants<TextBlock>(details).Select(x => x.Text).ToArray();
                if (!text.Any(x => x.Contains("张宝")) || text.Any(x => x.Contains("曹操"))) throw new Exception("历史详情显示错误人物");
                if (!text.Contains("攻击追加 诱惑")) throw new Exception("历史详情未显示真实天赋");
            }
            finally { details.Close(); }
        }
        finally { dialog.Close(); Directory.Delete(folder, true); }
    }
    private static void Pump(Window window)
    {
        window.UpdateLayout();
        window.Dispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
    }
    private static IEnumerable<T> Descendants<T>(DependencyObject root) where T : DependencyObject
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++)
        {
            var child = VisualTreeHelper.GetChild(root, i);
            if (child is T match) yield return match;
            foreach (var descendant in Descendants<T>(child)) yield return descendant;
        }
    }
}
