using System.ComponentModel;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using CczRandomizer.Wpf.Core;

namespace CczRandomizer.Wpf;

public partial class JobTalentsWindow : Window
{
    private readonly ICollectionView _view;
    public JobTalentsWindow(Window owner, JsonObject snapshot)
    {
        Owner = owner; InitializeComponent();
        _view = new CollectionViewSource { Source = JobTalentCatalog.Read(snapshot) }.View;
        Cards.ItemsSource = _view;
    }
    private void SearchChanged(object sender, TextChangedEventArgs e)
    {
        if (_view is null) return;
        var terms = Search.Text.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
        _view.Filter = item => { var row = (JobTalentCard)item; return terms.All(term => (row.Name + " " + row.Description).Contains(term, StringComparison.OrdinalIgnoreCase)); };
    }
}
