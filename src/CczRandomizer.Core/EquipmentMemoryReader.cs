using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public static class EquipmentMemoryReader
{
    public const uint Address = 0x005064D8;
    public const int Size = 376;
    private static readonly JsonObject Definitions = Load();
    private static JsonObject Load()
    {
        using var stream = typeof(EquipmentMemoryReader).Assembly.GetManifestResourceStream("Equipment.Definitions")!;
        return JsonNode.Parse(stream)!.AsObject();
    }
    public static string Effect(byte code, byte parameter)
    {
        if (Definitions["FIXED_EQUIPMENT_EFFECTS"]?[code.ToString()] is JsonValue fixedValue) return fixedValue.GetValue<string>();
        if (Definitions["FORMATTED_EQUIPMENT_EFFECTS"]?[code.ToString()] is JsonArray format)
            return $"{format[0]!.GetValue<string>()}{parameter + format[2]!.GetValue<int>()}{format[1]!.GetValue<string>()}";
        if (code is 0x1C or 0x51 or 0x66 or 0x6E or 0x7A)
        {
            var mask = Definitions["ABILITY_MASK_NAMES"]?[parameter.ToString()]?.GetValue<string>();
            if (mask is null) return $"能力组合0x{parameter:X2}";
            var prefix = code switch { 0x1C => "HP辅助", 0x51 => "提升周围", 0x66 => "自动提升", 0x6E => "MP辅助", _ => "忽视能力" };
            var separator = code == 0x1C && parameter is 5 or 9 || code == 0x66 && parameter == 0x3F ? "" : "-";
            return prefix + separator + mask;
        }
        if (code is 0x77 or 0x78 or 0x79)
        {
            var strategy = Definitions["STRATEGY_NAMES"]?[parameter.ToString()]?.GetValue<string>() ?? $"策略编号{parameter}";
            return (code switch { 0x77 => "攻击追加", 0x78 => "策略先手", _ => "策略反击" }) + "-" + strategy;
        }
        return code switch
        {
            0x33 => parameter switch { 4 => "穿透攻击-两格", 7 => "穿透攻击-三格", 9 => "穿透攻击-横扫", _ => $"穿透攻击-{parameter}" },
            0x70 => parameter switch { 4 => "弱点攻击-爆发", 5 => "弱点攻击-士气", _ => $"弱点攻击-{parameter}" },
            0x7B => parameter switch { 2 => "能力辅助-攻-防", 0x11 => "能力辅助-防-攻", 0x22 => "能力辅助-精-防", 0x33 => "能力辅助-爆-攻防", 0x45 => "能力辅助-士-攻精", _ => $"能力辅助-0x{parameter:X2}" },
            0x7C => parameter switch { 4 => "能力替换-攻-精", 0x10 => "能力替换-攻-士", 0x11 => "能力替换-防-攻", 0x14 => "能力替换-防-精", 0x22 => "能力替换-精-防", _ => $"能力替换-0x{parameter:X2}" },
            _ => $"未知特效(0x{code:X2}/0x{parameter:X2})"
        };
    }
    public static JsonObject Capture(IMemoryReader memory) => Decode(memory.Read(Address, Size));
    public static JsonObject Decode(ReadOnlySpan<byte> raw)
    {
        if (raw.Length != Size) throw new InvalidDataException("宝物记录长度错误");
        var names = Definitions["EQUIPMENT_NAMES"]!.AsArray().Select(x => x!.GetValue<string>()).ToArray();
        var effects = new Dictionary<string, string>();
        for (var i = 0; i < names.Length; i++)
        {
            var offset = i < 46 ? i * 4 : 184 + (i - 46) * 8;
            effects[names[i]] = Effect(raw[offset], raw[offset + (i < 46 ? 2 : 4)]);
        }
        var categories = new JsonArray();
        foreach (var category in Definitions["EQUIPMENT_CATEGORY_NAMES"]!.AsArray().Select(x => x!.GetValue<string>()))
        {
            var items = new JsonArray();
            foreach (var name in names.Where(n => (Definitions["EQUIPMENT_CATEGORY_BY_NAME"]?[n]?.GetValue<string>() ?? "辅助") == category))
                items.Add(new JsonObject { ["name"] = name, ["effect"] = effects[name] });
            if (items.Count > 0) categories.Add(new JsonObject { ["name"] = category, ["items"] = items });
        }
        var specials = new JsonArray();
        foreach (var set in Definitions["EQUIPMENT_SETS"]!.AsArray())
            specials.Add(new JsonObject { ["title"] = set![0]!.GetValue<string>(), ["items"] = new JsonArray(set[1]!.AsArray().Select(x => JsonValue.Create($"{x!.GetValue<string>()}：{effects[x.GetValue<string>()]}" )).ToArray()) });
        var markers = Definitions["GOOD_EQUIPMENT_SKILL_MARKERS"]!.AsArray().Select(x => x!.GetValue<string>()).ToArray();
        specials.Add(new JsonObject { ["title"] = "好东西", ["items"] = new JsonArray(effects.Where(x => markers.Any(x.Value.Contains)).Select(x => JsonValue.Create($"{x.Key}：{x.Value}")).ToArray()) });
        return new() { ["categories"] = categories, ["specials"] = specials };
    }
}
