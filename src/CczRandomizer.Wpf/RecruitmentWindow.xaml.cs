using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.IO;
using CczRandomizer.Wpf.Core;

namespace CczRandomizer.Wpf;

public partial class RecruitmentWindow : Window
{
    private readonly RecruitmentCatalog _catalog;
    public RecruitmentWindow(Window owner) { Owner = owner; InitializeComponent(); _catalog = LoadCatalog(); RenderCards(); }

    private static RecruitmentCatalog LoadCatalog()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "resources", "data", "recruitment", "recruits_2.2.json");
        return RecruitmentCatalog.Load(path);
    }

    private void FilterBox_TextChanged(object sender, TextChangedEventArgs e) => RenderCards();

    private void RenderCards()
    {
        Cards.Children.Clear(); var filter = FilterBox?.Text.Trim() ?? "";
        foreach (var person in _catalog.People.Where(person => filter.Length == 0 || Matches(person, filter)))
        {
            var card = new Border { Width = 270, Margin = new Thickness(0, 0, 14, 14), Padding = new Thickness(16), CornerRadius = new CornerRadius(12), Background = Brushes.White, BorderBrush = new SolidColorBrush(Color.FromRgb(226, 232, 240)), BorderThickness = new Thickness(1) };
            var content = new StackPanel();
            content.Children.Add(new TextBlock { Text = person.Name, FontSize = 18, FontWeight = FontWeights.SemiBold });
            content.Children.Add(new TextBlock { Text = person.JobChoices.Length == 0 ? "兵种：未采集" : $"兵种：{string.Join("、", person.JobChoices)}", Foreground = Brushes.SlateGray, Margin = new Thickness(0, 6, 0, 0) });
            content.Children.Add(new TextBlock { Text = $"次数消耗：{person.Cost}", Foreground = new SolidColorBrush(Color.FromRgb(37, 99, 235)), Margin = new Thickness(0, 4, 0, 0) });
            content.Children.Add(new TextBlock { Text = "关卡", FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 12, 0, 2) });
            foreach (var stage in person.Stages) content.Children.Add(new TextBlock { Text = $"    {stage.Route} · {stage.Name}", TextWrapping = TextWrapping.Wrap, FontSize = 12, Foreground = Brushes.SlateGray });
            content.Children.Add(new TextBlock { Text = "兵种天赋", FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 12, 0, 2) });
            foreach (var talent in person.JobTalents.DefaultIfEmpty("未采集")) content.Children.Add(new TextBlock { Text = $"    {talent}", TextWrapping = TextWrapping.Wrap, FontSize = 12 });
            content.Children.Add(new TextBlock { Text = "人物天赋", FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 10, 0, 2) });
            foreach (var talent in person.PersonalTalents.DefaultIfEmpty("未采集")) content.Children.Add(new TextBlock { Text = $"    {talent}", TextWrapping = TextWrapping.Wrap, FontSize = 12 });
            card.Child = content; Cards.Children.Add(card);
        }
    }

    private static bool Matches(RecruitPerson person, string filter)
        => person.Name.Contains(filter, StringComparison.OrdinalIgnoreCase)
        || person.JobChoices.Any(x => x.Contains(filter, StringComparison.OrdinalIgnoreCase))
        || person.Stages.Any(x => x.Name.Contains(filter, StringComparison.OrdinalIgnoreCase) || x.Route.Contains(filter, StringComparison.OrdinalIgnoreCase));
}
