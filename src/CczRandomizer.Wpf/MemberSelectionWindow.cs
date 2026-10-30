using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;

namespace CczRandomizer.Wpf;

public sealed class MemberSelectionWindow : Window
{
    public IReadOnlyList<string> SelectedMembers { get; private set; } = [];
    public MemberSelectionWindow(Window owner, IReadOnlyList<string> members, IReadOnlySet<string> selected)
    {
        Owner = owner; Title = "选择人物"; Width = 920; Height = 650; MinWidth = 760; MinHeight = 420;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        var panel = new DockPanel { Margin = new Thickness(24) };
        var search = new TextBox { ToolTip = "按姓名筛选", Padding = new Thickness(8), Margin = new Thickness(0, 0, 0, 16) };
        DockPanel.SetDock(search, Dock.Top); panel.Children.Add(search);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 16, 0, 0) };
        var all = new Button { Content = "选中筛选结果" }; var none = new Button { Content = "取消筛选结果" };
        var apply = new Button { Content = "应用选择", IsDefault = true }; var cancel = new Button { Content = "取消", IsCancel = true };
        buttons.Children.Add(all); buttons.Children.Add(none); buttons.Children.Add(apply); buttons.Children.Add(cancel);
        DockPanel.SetDock(buttons, Dock.Bottom); panel.Children.Add(buttons);
        var grid = new UniformGrid { Columns = 7 };
        var checks = members.Select(name => new CheckBox { Content = name, IsChecked = selected.Contains(name), Margin = new Thickness(6, 10, 6, 10) }).ToArray();
        foreach (var check in checks) grid.Children.Add(check);
        search.TextChanged += (_, _) => { foreach (var check in checks) check.Visibility = check.Content.ToString()!.Contains(search.Text.Trim(), StringComparison.OrdinalIgnoreCase) ? Visibility.Visible : Visibility.Collapsed; };
        all.Click += (_, _) => { foreach (var check in checks.Where(x => x.Visibility == Visibility.Visible)) check.IsChecked = true; };
        none.Click += (_, _) => { foreach (var check in checks.Where(x => x.Visibility == Visibility.Visible)) check.IsChecked = false; };
        apply.Click += (_, _) =>
        {
            var values = checks.Where(x => x.IsChecked == true).Select(x => x.Content.ToString()!).ToArray();
            if (values.Length == 0) { MessageBox.Show(this, "至少选择一名人物。", "人物设置"); return; }
            SelectedMembers = values; DialogResult = true;
        };
        panel.Children.Add(new ScrollViewer { Content = grid, VerticalScrollBarVisibility = ScrollBarVisibility.Auto }); Content = panel;
    }
}
