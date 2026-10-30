using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public sealed record EquipmentCard(string Category, string Name, string Effect, bool Special);
public static class EquipmentCatalog
{
    public static IReadOnlyList<EquipmentCard> Read(JsonObject snapshot)
    {
        var equipment = snapshot["equipment"] ?? snapshot["detail"]?["equipment"];
        if (equipment is null) return [];
        var cards = new List<EquipmentCard>();
        foreach (var special in equipment["specials"] as JsonArray ?? [])
            cards.Add(new("宝物特殊组合", special?["title"]?.GetValue<string>() ?? "特殊组合",
                string.Join("\n", (special?["items"] as JsonArray ?? []).Select(x => x?.GetValue<string>() ?? "")), true));
        foreach (var category in equipment["categories"] as JsonArray ?? [])
            foreach (var item in category?["items"] as JsonArray ?? [])
                cards.Add(new(category?["name"]?.GetValue<string>() ?? "其他", item?["name"]?.GetValue<string>() ?? "",
                    item?["effect"]?.GetValue<string>() ?? "", false));
        return cards;
    }
    public static bool Matches(EquipmentCard card, string query)
    {
        var text = $"{card.Category} {card.Name} {card.Effect}";
        return query.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries).All(term => text.Contains(term, StringComparison.OrdinalIgnoreCase));
    }
}
