using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using CczRandomizer.Wpf.Core;
using Microsoft.Win32;

namespace CczRandomizer.Wpf;

public sealed class ProfileToolbar : WrapPanel
{
    public ProfileToolbar(Window owner, RuleDocumentStore store, Action refresh)
    {
        Orientation = Orientation.Horizontal; Margin = new Thickness(0, 0, 0, 16);
        var selector = new ComboBox { ItemsSource = store.ProfileNames, SelectedItem = store.ActiveProfileName, MinWidth = 160, Margin = new Thickness(0, 0, 12, 0), Padding = new Thickness(6) };
        selector.SelectionChanged += (_, _) => { if (selector.SelectedItem is string name && name != store.ActiveProfileName) Run(() => store.SelectProfile(name)); };
        Children.Add(selector);
        Add("复制", () => { var name = AskName(owner, store.ActiveProfileName + "副本"); if (name is not null) Run(() => store.CopyProfile(name)); });
        Add("重命名", () => { var name = AskName(owner, store.ActiveProfileName, "重命名规则"); if (name is not null) Run(() => store.RenameActiveProfile(name)); });
        Add("恢复默认参数", () =>
        {
            if (MessageBox.Show(owner, "将当前规则的参数恢复为内置默认值？", "恢复默认参数", MessageBoxButton.YesNo) == MessageBoxResult.Yes) Run(store.ResetActiveProfile);
        });
        Add("删除", () =>
        {
            if (MessageBox.Show(owner, $"删除规则“{store.ActiveProfileName}”？", "删除规则", MessageBoxButton.YesNo) == MessageBoxResult.Yes) Run(store.DeleteActiveProfile);
        });
        Add("导入", () =>
        {
            var dialog = new OpenFileDialog { Filter = "规则 JSON|*.json", Title = "导入规则" };
            if (dialog.ShowDialog(owner) != true) return;
            Run(() =>
            {
                var payload = JsonNode.Parse(File.ReadAllText(dialog.FileName)) as JsonObject ?? throw new InvalidDataException("规则文件根节点必须是对象");
                var mode = RuleImporter.ReadLegacyMode(dialog.FileName);
                try { store.Import(payload, mode); }
                catch (LegacyModeRequiredException)
                {
                    var answer = MessageBox.Show(owner, "无法从同目录设置判断旧版生效模式。\n选“是”使用三人设置，选“否”使用七人设置，取消则不导入。", "选择旧版实际运行模式", MessageBoxButton.YesNoCancel);
                    if (answer == MessageBoxResult.Cancel) throw new OperationCanceledException();
                    store.Import(payload, answer == MessageBoxResult.Yes ? "three" : "seven");
                }
            });
        });
        Add("导出", () =>
        {
            var scope = MessageBox.Show(owner, "导出所有规则？\n选“是”导出全部，选“否”仅导出当前规则。", "导出范围", MessageBoxButton.YesNoCancel);
            if (scope == MessageBoxResult.Cancel) return;
            var dialog = new SaveFileDialog { Filter = "规则 JSON|*.json", FileName = "规则导出.json" };
            if (dialog.ShowDialog(owner) != true) return;
            try { File.WriteAllText(dialog.FileName, RuleImporter.Export(store.Document, scope == MessageBoxResult.Yes ? store.ProfileNames : [store.ActiveProfileName]).ToJsonString(new JsonSerializerOptions { WriteIndented = true })); }
            catch (Exception error) { MessageBox.Show(owner, error.Message, "导出失败"); }
        });

        void Add(string title, Action action) { var button = new Button { Content = title, IsEnabled = !store.IsBuiltin || title is not ("重命名" or "删除" or "恢复默认参数") }; button.Click += (_, _) => action(); Children.Add(button); }
        void Run(Action action)
        {
            var before = (JsonObject)store.Document.DeepClone();
            try { action(); store.Save(); refresh(); }
            catch (OperationCanceledException) { store.RestoreDraft(before); }
            catch (Exception error) { store.RestoreDraft(before); MessageBox.Show(owner, error.Message, "规则操作失败"); }
        }
    }
    private static string? AskName(Window owner, string initial, string title = "复制规则")
    {
        var dialog = new Window { Owner = owner, WindowStartupLocation = WindowStartupLocation.CenterOwner, Title = title, Width = 420, SizeToContent = SizeToContent.Height, ResizeMode = ResizeMode.NoResize };
        var panel = new StackPanel { Margin = new Thickness(24) };
        panel.Children.Add(new TextBlock { Text = "新规则名称" });
        var input = new TextBox { Text = initial, Padding = new Thickness(8), Margin = new Thickness(0, 12, 0, 16) }; panel.Children.Add(input);
        var button = new Button { Content = "确定", IsDefault = true, HorizontalAlignment = HorizontalAlignment.Right };
        button.Click += (_, _) => dialog.DialogResult = true;
        panel.Children.Add(button); dialog.Content = panel;
        return dialog.ShowDialog() == true ? input.Text : null;
    }
}
