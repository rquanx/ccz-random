namespace CczRandomizer.Wpf.Core;

public sealed record AttemptResult<T>(bool Accepted, bool SourceLoaded, T Payload);
public sealed record AcceptedResult<T>(int ResultSlot, int RoundIndex, T Payload);

public static class RandomWorkflow
{
    public const int MaxResultSlots = 15;

    public static IReadOnlyList<AcceptedResult<T>> Run<T>(
        int resultCount, int maxAttempts, Func<int, int, bool, AttemptResult<T>> runAttempt,
        Action<Exception, int, int>? recoverSession = null,
        Func<Exception, bool>? shouldRecover = null,
        Action<int, int>? onAttemptStarted = null,
        Action<AcceptedResult<T>>? onAccepted = null,
        Action? checkStop = null)
    {
        if (resultCount is < 1 or > MaxResultSlots) throw new ArgumentOutOfRangeException(nameof(resultCount));
        if (maxAttempts < 1) throw new ArgumentOutOfRangeException(nameof(maxAttempts));
        var accepted = new List<AcceptedResult<T>>(); var sourceLoaded = false;
        checkStop ??= static () => { }; shouldRecover ??= static _ => false; recoverSession ??= static (_, _, _) => { };
        for (var slot = 1; slot <= resultCount; slot++)
        {
            checkStop();
            var produced = false;
            for (var round = 1; round <= maxAttempts && !produced; round++)
            {
                checkStop(); onAttemptStarted?.Invoke(slot, round);
                AttemptResult<T> attempt;
                for (var recovery = 0; ; recovery++)
                {
                    try { attempt = runAttempt(slot, round, sourceLoaded); sourceLoaded = attempt.SourceLoaded; break; }
                    catch (Exception error) when (recovery == 0 && shouldRecover(error))
                    { recoverSession(error, slot, round); sourceLoaded = false; checkStop(); }
                }
                if (!attempt.Accepted) { checkStop(); continue; }
                var result = new AcceptedResult<T>(slot, round, attempt.Payload); accepted.Add(result); produced = true; onAccepted?.Invoke(result);
            }
            if (!produced) throw new InvalidOperationException($"结果 {slot} 连续 {maxAttempts} 轮未产生满足条件的结果。");
        }
        return accepted;
    }
}
