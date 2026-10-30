using System.ComponentModel;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using CczRandomizer.Wpf.Core;

namespace CczRandomizer.Wpf;

public partial class EquipmentWindow : Window
{
    private readonly ICollectionView _view;
    private readonly bool _hasSnapshot;
    public EquipmentWindow(Window owner, JsonObject snapshot)
    {
        Owner = owner; InitializeComponent();
        _hasSnapshot = snapshot["equipment"] is not null || snapshot["detail"]?["equipment"] is not null;
        _view = new CollectionViewSource { Source = EquipmentCatalog.Read(snapshot) }.View;
        Cards.ItemsSource = _view; Refresh();
    }
    private void SearchChanged(object sender, TextChangedEventArgs e) { if (_view is not null) Refresh(); }
    private void Refresh()
    {
        _view.Filter = item => EquipmentCatalog.Matches((EquipmentCard)item, Search.Text);
        EmptyMessage.Text = !_hasSnapshot ? "本次结果未保存宝物信息。" : _view.IsEmpty ? "没有符合条件的宝物信息。" : "";
    }
}
