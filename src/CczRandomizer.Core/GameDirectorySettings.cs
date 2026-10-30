namespace CczRandomizer.Wpf.Core;

public static class GameDirectorySettings
{
    public static string SettingsPath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "CczRandomizer", "game-directory.txt");
    public static string Discover(string baseDirectory, string? environmentOverride = null, string? settingsPath = null)
    {
        if (!string.IsNullOrWhiteSpace(environmentOverride)) return Path.GetFullPath(environmentOverride);
        // A portable installation belongs to the game beside it, even if another copy was used earlier.
        foreach (var path in new[] { baseDirectory, Directory.GetParent(baseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar))?.FullName })
            if (path is not null && File.Exists(Path.Combine(path, "Ekd5.exe"))) return Path.GetFullPath(path);
        try
        {
            var saved = File.ReadAllText(settingsPath ?? SettingsPath).Trim();
            if (File.Exists(Path.Combine(saved, "Ekd5.exe"))) return Path.GetFullPath(saved);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException) { }
        return Path.GetFullPath(baseDirectory);
    }

    public static void Remember(string directory, string? settingsPath = null)
    {
        var path = settingsPath ?? SettingsPath;
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try { File.WriteAllText(temporary, Path.GetFullPath(directory)); File.Move(temporary, path, true); }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
