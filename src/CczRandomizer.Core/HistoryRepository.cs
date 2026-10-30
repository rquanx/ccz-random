using System.Text.Json.Nodes;
using Microsoft.Data.Sqlite;

namespace CczRandomizer.Wpf.Core;

public sealed record HistoryRound(long Id, string RunId, int RoundNumber, string StartedAt, string Status, string RuleName, int ResultCount);

public sealed class HistoryRepository
{
    public string DatabasePath { get; }
    private static string Now => DateTimeOffset.Now.ToString("yyyy-MM-ddTHH:mm:sszzz");
    public HistoryRepository(string gameDirectory)
    {
        var directory = Path.Combine(gameDirectory, "ccz_fast_data");
        Directory.CreateDirectory(directory);
        DatabasePath = Path.Combine(directory, "history.sqlite3");
        if (Version(DatabasePath) > 1) DatabasePath = Path.Combine(directory, "history-v1.sqlite3");
        using var connection = Connect();
        var version = Convert.ToInt32(Scalar(connection, "PRAGMA user_version"));
        if (version > 1) throw new InvalidDataException("历史数据库版本过新");
        if (version == 0)
        {
            using var transaction = connection.BeginTransaction();
            Execute(connection, """
                CREATE TABLE runs (id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
                    status TEXT NOT NULL, mode TEXT NOT NULL, loop_random INTEGER NOT NULL,
                    rule_name TEXT NOT NULL, rule_json TEXT NOT NULL, build_json TEXT NOT NULL);
                CREATE TABLE rounds (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    round_number INTEGER NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, UNIQUE(run_id,round_number));
                CREATE TABLE results (id INTEGER PRIMARY KEY AUTOINCREMENT, round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
                    slot INTEGER NOT NULL, accepted_attempt INTEGER NOT NULL, created_at TEXT NOT NULL, mode TEXT NOT NULL,
                    job_average REAL, skill_score REAL, save_path TEXT, save_sha256 TEXT, save_verified INTEGER NOT NULL DEFAULT 0,
                    verification_error TEXT, snapshot_json TEXT NOT NULL, UNIQUE(round_id,slot));
                CREATE INDEX idx_rounds_started ON rounds(started_at DESC,id DESC);
                CREATE INDEX idx_results_round_slot ON results(round_id,slot);
                PRAGMA user_version=1;
                """);
            transaction.Commit();
        }
    }
    private static int Version(string path)
    {
        if (!File.Exists(path)) return 0;
        using var connection = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = path, Mode = SqliteOpenMode.ReadOnly, Pooling = false }.ToString());
        connection.Open();
        return Convert.ToInt32(Scalar(connection, "PRAGMA user_version"));
    }
    private SqliteConnection Connect()
    {
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = DatabasePath, ForeignKeys = true, DefaultTimeout = 5, Pooling = false }.ToString());
        try { connection.Open(); Execute(connection, "PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;"); return connection; }
        catch { connection.Dispose(); throw; }
    }
    private static SqliteCommand Command(SqliteConnection connection, string sql, params object?[] values)
    {
        var command = connection.CreateCommand(); command.CommandText = sql;
        for (var i = 0; i < values.Length; i++) command.Parameters.AddWithValue("$p" + i, values[i] ?? DBNull.Value);
        return command;
    }
    private static void Execute(SqliteConnection connection, string sql, params object?[] values) { using var command = Command(connection, sql, values); command.ExecuteNonQuery(); }
    private static object? Scalar(SqliteConnection connection, string sql, params object?[] values) { using var command = Command(connection, sql, values); return command.ExecuteScalar(); }

    public void StartRun(string id, bool loop, string ruleName, JsonObject rules, JsonObject build)
    {
        using var connection = Connect();
        Execute(connection, "INSERT INTO runs(id,started_at,status,mode,loop_random,rule_name,rule_json,build_json) VALUES($p0,$p1,'running','three',$p2,$p3,$p4,$p5)", id, Now, loop ? 1 : 0, ruleName, rules.ToJsonString(), build.ToJsonString());
    }
    public long StartRound(string runId, int number)
    {
        using var connection = Connect();
        Execute(connection, "INSERT INTO rounds(run_id,round_number,started_at,status) VALUES($p0,$p1,$p2,'running')", runId, number, Now);
        return Convert.ToInt64(Scalar(connection, "SELECT last_insert_rowid()"));
    }
    public void SaveResult(long roundId, JsonObject snapshot)
    {
        using var connection = Connect();
        var save = snapshot["save"];
        Execute(connection, """
            INSERT INTO results(round_id,slot,accepted_attempt,created_at,mode,job_average,skill_score,save_path,save_sha256,save_verified,verification_error,snapshot_json)
            VALUES($p0,$p1,$p2,$p3,$p4,$p5,$p6,$p7,$p8,$p9,$p10,$p11)
            ON CONFLICT(round_id,slot) DO UPDATE SET accepted_attempt=excluded.accepted_attempt,created_at=excluded.created_at,
                mode=excluded.mode,job_average=excluded.job_average,skill_score=excluded.skill_score,save_path=excluded.save_path,
                save_sha256=excluded.save_sha256,save_verified=excluded.save_verified,verification_error=excluded.verification_error,snapshot_json=excluded.snapshot_json
            """, roundId, snapshot["slot"]!.GetValue<int>(), snapshot["acceptedAttempt"]!.GetValue<int>(), snapshot["createdAt"]?.GetValue<string>() ?? Now,
            snapshot["mode"]?.GetValue<string>() ?? "three", snapshot["detail"]?["job"]?["metrics"]?["average"]?.GetValue<double>(),
            snapshot["detail"]?["skill"]?["metrics"]?["skillScore"]?.GetValue<double>(), save?["path"]?.GetValue<string>() ?? "",
            save?["sha256"]?.GetValue<string>() ?? "", save?["verified"]?.GetValue<bool>() == true ? 1 : 0, save?["verificationError"]?.GetValue<string>() ?? "", snapshot.ToJsonString());
    }
    public void FinishRound(long id, string status)
    {
        using var connection = Connect(); using var transaction = connection.BeginTransaction();
        Execute(connection, "UPDATE rounds SET status=$p0,finished_at=$p1 WHERE id=$p2", status, Now, id);
        Execute(connection, "DELETE FROM rounds WHERE id=$p0 AND NOT EXISTS(SELECT 1 FROM results WHERE results.round_id=rounds.id)", id);
        transaction.Commit();
    }
    public void FinishRun(string id, string status)
    {
        using var connection = Connect(); using var transaction = connection.BeginTransaction();
        Execute(connection, "UPDATE runs SET status=$p0,finished_at=$p1 WHERE id=$p2", status, Now, id);
        Execute(connection, "DELETE FROM rounds WHERE run_id=$p0 AND NOT EXISTS(SELECT 1 FROM results WHERE results.round_id=rounds.id)", id);
        Execute(connection, "DELETE FROM runs WHERE id=$p0 AND NOT EXISTS(SELECT 1 FROM rounds WHERE rounds.run_id=runs.id)", id);
        transaction.Commit();
    }
    public int CountRounds()
    {
        using var connection = Connect();
        return Convert.ToInt32(Scalar(connection, "SELECT COUNT(*) FROM rounds WHERE EXISTS(SELECT 1 FROM results WHERE results.round_id=rounds.id)"));
    }
    public IReadOnlyList<HistoryRound> ListRounds(int page = 1, int pageSize = 20)
    {
        pageSize = Math.Clamp(pageSize, 1, 100); page = Math.Max(1, page);
        using var connection = Connect();
        using var command = Command(connection, """
            SELECT rounds.id,rounds.run_id,rounds.round_number,rounds.started_at,rounds.status,runs.rule_name,COUNT(results.id)
            FROM rounds JOIN runs ON runs.id=rounds.run_id JOIN results ON results.round_id=rounds.id
            GROUP BY rounds.id ORDER BY rounds.started_at DESC,rounds.id DESC LIMIT $p0 OFFSET $p1
            """, pageSize, ((long)page - 1) * pageSize);
        using var reader = command.ExecuteReader(); var rows = new List<HistoryRound>();
        while (reader.Read()) rows.Add(new(reader.GetInt64(0), reader.GetString(1), reader.GetInt32(2), reader.GetString(3), reader.GetString(4), reader.GetString(5), reader.GetInt32(6)));
        return rows;
    }
    public IReadOnlyList<JsonObject> GetResults(long roundId)
    {
        using var connection = Connect(); using var command = Command(connection, "SELECT snapshot_json FROM results WHERE round_id=$p0 ORDER BY slot", roundId);
        using var reader = command.ExecuteReader(); var result = new List<JsonObject>();
        while (reader.Read()) result.Add(JsonNode.Parse(reader.GetString(0))!.AsObject());
        return result;
    }
    public void UpdateVerification(long roundId, int slot, bool verified, string error = "")
    {
        using var connection = Connect(); using var transaction = connection.BeginTransaction();
        if (Scalar(connection, "SELECT snapshot_json FROM results WHERE round_id=$p0 AND slot=$p1", roundId, slot) is string raw)
        {
            var snapshot = JsonNode.Parse(raw)!;
            if (snapshot["save"] is null) snapshot["save"] = new JsonObject();
            snapshot["save"]!["verified"] = verified; snapshot["save"]!["verificationError"] = error;
            Execute(connection, "UPDATE results SET save_verified=$p0,verification_error=$p1,snapshot_json=$p2 WHERE round_id=$p3 AND slot=$p4", verified ? 1 : 0, error, snapshot.ToJsonString(), roundId, slot);
        }
        transaction.Commit();
    }
    public void DeleteRound(long id)
    {
        using var connection = Connect(); using var transaction = connection.BeginTransaction();
        var runId = Scalar(connection, "SELECT run_id FROM rounds WHERE id=$p0", id);
        Execute(connection, "DELETE FROM rounds WHERE id=$p0", id);
        Execute(connection, "DELETE FROM runs WHERE id=$p0 AND NOT EXISTS(SELECT 1 FROM rounds WHERE rounds.run_id=runs.id)", runId);
        transaction.Commit();
    }
    public void Clear() { using var connection = Connect(); Execute(connection, "DELETE FROM runs"); }
}
