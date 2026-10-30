using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Text.Json.Nodes;
using CczRandomizer.Wpf.Core;

namespace CczRandomizer.Wpf;

public sealed class RuleSettingsWindow : Window
{
    private sealed record TypeOption(string Key, string Label);
    private static readonly TypeOption[] Types = [new("ALL_ROUNDER", "全能型"), new("WARRIOR", "武将型"), new("MASTER", "文官型"), new("NONE", "不限制")];
    private readonly RuleSettingsDraft _draft;
    private readonly List<DataGrid> _grids = [];
    public JsonObject? EditedProfile { get; private set; }
    public RuleSettingsWindow(Window owner, JsonObject profile, IEnumerable<string> memberNames, int selectedTab = 0)
    {
        Owner = owner; WindowStartupLocation = WindowStartupLocation.CenterOwner;
        Title = "基础设置与人物倾向"; Width = 840; Height = 680; MinWidth = 640; MinHeight = 480;
        _draft = new(profile, memberNames);
        var panel = new DockPanel { Margin = new Thickness(24) };
        var footer = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 16, 0, 0) };
        var cancel = new Button { Content = "取消", IsCancel = true };
        var apply = new Button { Content = "应用设置", IsDefault = true };
        apply.Click += (_, _) =>
        {
            if (_grids.Any(g => !g.CommitEdit(DataGridEditingUnit.Cell, true) || !g.CommitEdit(DataGridEditingUnit.Row, true))) return;
            if (HasValidationError(this)) { MessageBox.Show(this, "请修正标红的数字输入。", "设置有误"); return; }
            try { EditedProfile = _draft.BuildProfile(); DialogResult = true; }
            catch (Exception error) { MessageBox.Show(this, error.Message, "设置有误"); }
        };
        footer.Children.Add(cancel); footer.Children.Add(apply); DockPanel.SetDock(footer, Dock.Bottom); panel.Children.Add(footer);
        var tabs = new TabControl { SelectedIndex = selectedTab };
        var jobOptions = new WrapPanel();
        jobOptions.Children.Add(Check("启用人物倾向", nameof(_draft.AffinityEnabled)));
        jobOptions.Children.Add(Number("基础分权重", nameof(_draft.BaseScoreWeight)));
        jobOptions.Children.Add(Number("适配最低分", nameof(_draft.AffinityMinimum)));
        jobOptions.Children.Add(Number("主要加成比例", nameof(_draft.PrimaryBonus)));
        jobOptions.Children.Add(Number("次要加成比例", nameof(_draft.SecondaryBonus)));
        tabs.Items.Add(Page("兵种基础设置", _draft.Jobs, jobOptions, false));
        tabs.Items.Add(Page("特技基础设置", _draft.Skills, Check("启用特技类型匹配", nameof(_draft.SkillTypeMatching)), true));
        tabs.Items.Add(Page("人物倾向", _draft.Members, new TextBlock { Text = "为每名人物分别设置主要和次要倾向。", Margin = new Thickness(0, 8, 0, 8) }, true, true));
        panel.Children.Add(tabs); Content = panel;
    }
    private static bool HasValidationError(DependencyObject root)
    {
        if (Validation.GetHasError(root)) return true;
        for (var i = 0; i < System.Windows.Media.VisualTreeHelper.GetChildrenCount(root); i++)
            if (HasValidationError(System.Windows.Media.VisualTreeHelper.GetChild(root, i))) return true;
        return false;
    }
    private CheckBox Check(string label, string property)
    {
        var box = new CheckBox { Content = label, Margin = new Thickness(0, 8, 20, 8), VerticalAlignment = VerticalAlignment.Center };
        box.SetBinding(CheckBox.IsCheckedProperty, new Binding(property) { Source = _draft, Mode = BindingMode.TwoWay }); return box;
    }
    private UIElement Number(string label, string property)
    {
        var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 4, 12, 4) };
        row.Children.Add(new TextBlock { Text = label, VerticalAlignment = VerticalAlignment.Center });
        var input = new TextBox { Width = 65, Margin = new Thickness(6, 0, 0, 0), Padding = new Thickness(4) };
        input.SetBinding(TextBox.TextProperty, new Binding(property) { Source = _draft, Mode = BindingMode.TwoWay, UpdateSourceTrigger = UpdateSourceTrigger.PropertyChanged, ValidatesOnExceptions = true });
        row.Children.Add(input); return row;
    }
    private TabItem Page(string title, System.Collections.IEnumerable rows, UIElement options, bool allowNone, bool affinity = false)
    {
        var panel = new DockPanel { Margin = new Thickness(12) };
        DockPanel.SetDock(options, Dock.Top); panel.Children.Add(options);
        var search = new TextBox { Margin = new Thickness(0, 8, 0, 12), Padding = new Thickness(6), ToolTip = "按名称筛选" };
        DockPanel.SetDock(search, Dock.Top); panel.Children.Add(search);
        var source = new CollectionViewSource { Source = rows };
        search.TextChanged += (_, _) =>
        {
            var filter = search.Text.Trim();
            source.View.Filter = item => (item is ScoreSetting score ? score.Name : ((AffinitySetting)item).Name).Contains(filter, StringComparison.OrdinalIgnoreCase);
        };
        var grid = new DataGrid { ItemsSource = source.View, AutoGenerateColumns = false, CanUserAddRows = false, CanUserDeleteRows = false,
            EnableRowVirtualization = true, EnableColumnVirtualization = true, RowHeight = 36, HeadersVisibility = DataGridHeadersVisibility.Column };
        VirtualizingPanel.SetVirtualizationMode(grid, VirtualizationMode.Recycling);
        grid.Columns.Add(new DataGridTextColumn { Header = "名称", Binding = new Binding("Name"), IsReadOnly = true, Width = new DataGridLength(1, DataGridLengthUnitType.Star) });
        if (affinity) { grid.Columns.Add(TypeColumn("主要倾向", "PrimaryType", true)); grid.Columns.Add(TypeColumn("次要倾向", "SecondaryType", true)); }
        else
        {
            grid.Columns.Add(new DataGridTextColumn { Header = "基础分", Binding = new Binding("Score") { Mode = BindingMode.TwoWay, ValidatesOnExceptions = true }, Width = 100 });
            grid.Columns.Add(TypeColumn("匹配类型", "Type", allowNone));
        }
        _grids.Add(grid); panel.Children.Add(grid); return new TabItem { Header = title, Content = panel };
    }
    private static DataGridComboBoxColumn TypeColumn(string title, string property, bool allowNone) => new()
    {
        Header = title, ItemsSource = allowNone ? Types : Types[..3], DisplayMemberPath = "Label", SelectedValuePath = "Key",
        SelectedValueBinding = new Binding(property) { Mode = BindingMode.TwoWay, UpdateSourceTrigger = UpdateSourceTrigger.PropertyChanged }, Width = 130
    };
}
