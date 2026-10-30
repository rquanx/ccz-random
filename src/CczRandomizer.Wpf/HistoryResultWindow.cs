using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using CczRandomizer.Wpf.Core;

namespace CczRandomizer.Wpf;

public sealed class HistoryResultWindow : Window
{
    public HistoryResultWindow(Window owner, JsonObject snapshot)
    {
        Owner = owner; Title = "存档详情"; WindowStartupLocation = WindowStartupLocation.CenterOwner;
        Width = 820; Height = 650; MinWidth = 560; MinHeight = 400;
        var panel = new DockPanel { Margin = new Thickness(24) };
        var actionRow = new System.Windows.Controls.Primitives.UniformGrid { Columns = 3, Margin = new Thickness(0, 0, 0, 16) };
        var talents = new Button { Content = "兵种天赋", HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 0, 0, 12) };
        talents.Click += (_, _) =>
        {
            try { new JobTalentsWindow(this, snapshot).ShowDialog(); }
            catch (Exception error) { MessageBox.Show(this, error.Message, "无法读取兵种天赋"); }
        };
        actionRow.Children.Add(talents);
        var entries = new Button { Content = "入队人员信息" };
        entries.Click += (_, _) =>
        {
            try { new RecruitmentWindow(this, snapshot).ShowDialog(); }
            catch (Exception error) { MessageBox.Show(this, error.Message, "无法读取入队人员"); }
        };
        actionRow.Children.Add(entries);
        var equipment = new Button { Content = "宝物信息", HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 0, 0, 16) };
        equipment.Click += (_, _) => new EquipmentWindow(this, snapshot).ShowDialog();
        actionRow.Children.Add(equipment);
        foreach (Button action in actionRow.Children) { action.HorizontalAlignment = HorizontalAlignment.Stretch; action.Margin = new Thickness(0, 0, 8, 0); action.Padding = new Thickness(12); }
        DockPanel.SetDock(actionRow, Dock.Top); panel.Children.Add(actionRow);
        var summary = new ScrollViewer { MaxHeight = 170, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            Content = new TextBlock { Text = ScorePresentation.Summary(snapshot, false), TextWrapping = TextWrapping.Wrap, LineHeight = 25, Margin = new Thickness(0, 0, 0, 12) } };
        DockPanel.SetDock(summary, Dock.Top); panel.Children.Add(summary);
        var footer = new TextBlock { Text = $"第 {snapshot["slot"]} 栏 · 第 {snapshot["acceptedAttempt"]} 次随机 · {(snapshot["save"]?["verified"]?.GetValue<bool>() == true ? "回读验证通过" : "尚无验证存档")}", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 0) };
        DockPanel.SetDock(footer, Dock.Bottom); panel.Children.Add(footer);
        var skillDetails = snapshot["detail"]?["skill"]?["details"] as JsonArray;
        var cards = HistoryMembers.Resolve(snapshot).Select(member => new ResultMemberCard(
            $"{member["name"]} · {member["job"] ?? JsonValue.Create("未保存兵种")}",
            $"兵种评分 {member["jobScore"]}    特技评分 {snapshot["detail"]?["skill"]?["metrics"]?["memberSkillScores"]?[member["name"]!.GetValue<string>()]?.ToString() ?? "未记录"}",
            ReadSkills(member, "jobSkills"), ReadSkills(member, "personalSkills"),
            skillDetails?.Where(x => x?["member"]?.GetValue<string>() == member["name"]?.GetValue<string>())
                .Select(x => $"{x!["name"]} · {(x["counted"]?.GetValue<bool>() == true ? x["score"] + " 分" : "不计分")}").ToArray() ?? [])).ToArray();
        var list = new ListBox { ItemsSource = cards, BorderThickness = new Thickness(0), Background = Brushes.Transparent };
        VirtualizingPanel.SetIsVirtualizing(list, true); VirtualizingPanel.SetVirtualizationMode(list, VirtualizationMode.Recycling);
        ScrollViewer.SetHorizontalScrollBarVisibility(list, ScrollBarVisibility.Disabled);
        var style = new Style(typeof(ListBoxItem)); style.Setters.Add(new Setter(HorizontalContentAlignmentProperty, HorizontalAlignment.Stretch)); list.ItemContainerStyle = style;
        list.ItemTemplate = (DataTemplate)System.Windows.Markup.XamlReader.Parse("""
            <DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
              <Border Padding="18" Margin="0,0,0,14" BorderBrush="#DDE4F1" BorderThickness="1" CornerRadius="10" Background="White">
                <StackPanel>
                  <TextBlock Text="{Binding Title}" FontSize="18" FontWeight="SemiBold"/>
                  <TextBlock Text="{Binding Score}" Margin="0,8,0,0"/>
                  <TextBlock Text="兵种天赋" FontWeight="SemiBold" Margin="0,12,0,4"/>
                  <ItemsControl ItemsSource="{Binding JobTalents}" Margin="16,0,0,0"><ItemsControl.ItemTemplate><DataTemplate><TextBlock Text="{Binding}" TextWrapping="Wrap" Margin="0,2"/></DataTemplate></ItemsControl.ItemTemplate></ItemsControl>
                  <TextBlock Text="人物天赋" FontWeight="SemiBold" Margin="0,12,0,4"/>
                  <ItemsControl ItemsSource="{Binding PersonalTalents}" Margin="16,0,0,0"><ItemsControl.ItemTemplate><DataTemplate><TextBlock Text="{Binding}" TextWrapping="Wrap" Margin="0,2"/></DataTemplate></ItemsControl.ItemTemplate></ItemsControl>
                  <TextBlock Text="特技计分明细" FontWeight="SemiBold" Margin="0,12,0,4"/>
                  <ItemsControl ItemsSource="{Binding Details}" Margin="16,0,0,0"><ItemsControl.ItemTemplate><DataTemplate><TextBlock Text="{Binding}" TextWrapping="Wrap" Margin="0,2"/></DataTemplate></ItemsControl.ItemTemplate></ItemsControl>
                </StackPanel>
              </Border>
            </DataTemplate>
            """);
        panel.Children.Add(list); Content = panel;
    }
    private static string[] ReadSkills(JsonObject member, string key) => (member[key] as JsonArray)?.Select(x => x?["name"]?.GetValue<string>() ?? "未知天赋").ToArray() ?? ["历史记录未保存"];
}

public sealed record ResultMemberCard(string Title, string Score, string[] JobTalents, string[] PersonalTalents, string[] Details);
