using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using CczRandomizer.Wpf.Core;

namespace CczRandomizer.Wpf;

public partial class RecruitmentWindow : Window
{
    private readonly IReadOnlyList<EntryCard> _people;
    private readonly DispatcherTimer _filterTimer = new() { Interval = TimeSpan.FromMilliseconds(120) };
    public RecruitmentWindow(Window owner, JsonObject? snapshot = null)
    {
        Owner = owner; InitializeComponent();
        var catalog = RecruitmentCatalog.Load(Path.Combine(AppContext.BaseDirectory, "resources/data/recruitment/recruits_2.2.json"));
        _people = EntrySnapshot.Read(snapshot ?? new JsonObject(), catalog);
        StageBox.ItemsSource = new[] { "全部关卡" }.Concat(_people.SelectMany(x => x.Stages).DistinctBy(x => (x.StageId, x.Name, x.Route)).OrderBy(x => x.StageId).Select(EntrySnapshot.StageLabel)).ToArray();
        StageBox.SelectedIndex = 0;
        _filterTimer.Tick += (_, _) => { _filterTimer.Stop(); Refresh(); };
        Closed += (_, _) => _filterTimer.Stop();
        Refresh();
    }
    private void FilterChanged(object sender, TextChangedEventArgs e) { _filterTimer.Stop(); _filterTimer.Start(); }
    private void StageChanged(object sender, SelectionChangedEventArgs e) { if (_people is not null) Refresh(); }
    private void Refresh() => Groups.ItemsSource = EntrySnapshot.Group(_people, FilterBox.Text, StageBox.SelectedIndex > 0 ? StageBox.SelectedItem as string : null);
}
