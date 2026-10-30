using System.Text.Json;
using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

internal static class JsonNumbers
{
    // JsonValue keeps the CLR type of values edited in memory (int versus double).
    public static double Read(JsonNode node) => node.Deserialize<double>();
    public static double Read(JsonNode? node, double fallback) => node is null ? fallback : Read(node);
}
