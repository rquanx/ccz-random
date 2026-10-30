using System.Globalization;
using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using CczRandomizer.Wpf.Core;

namespace CczRandomizer.Wpf;

/// <summary>Draw paginated result cards on a dedicated STA, without blocking the UI.</summary>
public static class ResultImageRenderer
{
    public static Task<IReadOnlyList<string>> WriteAsync(JsonObject snapshot)
    {
        var frozen = (JsonObject)snapshot.DeepClone();
        var completion = new TaskCompletionSource<IReadOnlyList<string>>(TaskCreationOptions.RunContinuationsAsynchronously);
        var thread = new Thread(() =>
        {
            try { completion.SetResult(Render(frozen)); }
            catch (Exception error) { completion.SetException(error); }
        }) { IsBackground = true, Name = "Result image export" };
        thread.SetApartmentState(ApartmentState.STA); thread.Start(); return completion.Task;
    }
    private static FormattedText Text(string value, double size, double width, Brush brush, bool bold = false) => new(value,
        CultureInfo.GetCultureInfo("zh-CN"), FlowDirection.LeftToRight,
        new Typeface(new FontFamily("Microsoft YaHei UI"), FontStyles.Normal, bold ? FontWeights.SemiBold : FontWeights.Normal, FontStretches.Normal), size, brush, 1)
        { MaxTextWidth = width, LineHeight = size * 1.6 };
    private static IReadOnlyList<string> Render(JsonObject snapshot)
    {
        var people = HistoryMembers.Resolve(snapshot).ToArray();
        var pages = people.Chunk(4).ToArray();
        var result = new List<string>();
        var stem = Path.ChangeExtension(snapshot["save"]!["path"]!.GetValue<string>(), null);
        for (var page = 0; page < pages.Length; page++)
        {
            var width = pages[page].Length == 1 ? 732 : 1400;
            var summary = Text(ScorePresentation.Summary(snapshot, false), 17, width - 96, Brushes.SlateGray);
            var blocks = pages[page].Select(person =>
            {
                var name = person["name"]!.GetValue<string>();
                var skillScore = snapshot["detail"]?["skill"]?["metrics"]?["memberSkillScores"]?[name];
                var skills = new List<string> { $"兵种评分：{person["jobScore"]}    特技评分：{skillScore?.ToString() ?? "未检查"}", "", "兵种天赋" };
                foreach (var (label, key) in new[] { ("", "jobSkills"), ("人物天赋", "personalSkills") })
                {
                    if (label.Length > 0) { skills.Add(""); skills.Add(label); }
                    skills.AddRange((person[key] as JsonArray)?.Select(x => "    " + x?["name"]?.GetValue<string>()) ?? ["    未保存"]);
                }
                return (Title: Text($"{person["name"]} · {person["job"]}", 24, 560, Brushes.MidnightBlue, true), Body: Text(string.Join("\n", skills), 19, 560, Brushes.DarkSlateGray));
            }).ToArray();
            var rowHeights = blocks.Chunk(2).Select(row => row.Max(x => x.Title.Height + x.Body.Height) + 64).ToArray();
            var header = 130 + summary.Height;
            var height = (int)Math.Ceiling(header + rowHeights.Sum() + rowHeights.Length * 24 + 60);
            var visual = new DrawingVisual();
            using (var dc = visual.RenderOpen())
            {
                dc.DrawRectangle(new SolidColorBrush(Color.FromRgb(245, 247, 251)), null, new Rect(0, 0, width, height));
                dc.DrawText(Text($"第 {snapshot["slot"]} 栏 · 合格结果", 32, width - 250, Brushes.MidnightBlue, true), new Point(48, 28));
                dc.DrawText(Text($"{page + 1} / {pages.Length}", 18, 100, Brushes.SlateGray), new Point(width - 150, 42));
                dc.DrawText(summary, new Point(48, 90));
                double y = header;
                for (var row = 0; row < rowHeights.Length; row++)
                {
                    for (var column = 0; column < 2 && row * 2 + column < blocks.Length; column++)
                    {
                        var block = blocks[row * 2 + column]; var x = 48 + column * 660;
                        dc.DrawRoundedRectangle(Brushes.White, new Pen(Brushes.LightGray, 1), new Rect(x, y, 636, rowHeights[row]), 14, 14);
                        dc.DrawText(block.Title, new Point(x + 28, y + 22));
                        dc.DrawText(block.Body, new Point(x + 28, y + 34 + block.Title.Height));
                    }
                    y += rowHeights[row] + 24;
                }
            }
            var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32); bitmap.Render(visual);
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
            var path = stem + $"-page-{page + 1:00}.png";
            using (var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None)) encoder.Save(output);
            result.Add(path);
        }
        return result;
    }
}
