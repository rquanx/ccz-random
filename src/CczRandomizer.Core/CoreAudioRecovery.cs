using System.Runtime.InteropServices;

namespace CczRandomizer.Wpf.Core;

/// <summary>Core Audio ABI mirrors the former audio_recovery.py. Changes only a matching process session's mute flag.</summary>
internal static class CoreAudioRecovery
{
    private static readonly Guid EnumeratorClass = new("bcde0395-e52f-467c-8e3d-c4579291692e");
    private static readonly Guid EnumeratorInterface = new("a95664d2-9614-4f35-a746-de8db63617e6");
    private static readonly Guid ManagerInterface = new("77aa99a0-1bd6-484f-8bc7-2c654c9a9b6f");
    private static readonly Guid ControlInterface = new("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d");
    private static readonly Guid VolumeInterface = new("87ce5498-68d6-44e5-9215-6da47ef883d8");
    public static AudioRecovery Restore(int pid) => SetMuted(pid, false);
    internal static AudioRecovery SetMuted(int pid, bool desiredMuted)
    {
        if (pid <= 0) throw new ArgumentOutOfRangeException(nameof(pid));
        var initialized = CoInitializeEx(0, 0);
        if (initialized < 0 && initialized != unchecked((int)0x80010106)) Marshal.ThrowExceptionForHR(initialized);
        try
        {
            Check(CoCreateInstance(EnumeratorClass, 0, 0x17, EnumeratorInterface, out var pointer));
            using var enumerator = new ComReference(pointer);
            Check(enumerator.Call<Endpoints>(3)(pointer, 0, 1, out var collection));
            using var devices = new ComReference(collection);
            Check(devices.Call<Number>(3)(collection, out var count));
            var matched = 0; var restored = 0;
            for (var i = 0; i < count; i++)
            {
                Check(devices.Call<Item>(4)(collection, i, out var devicePointer));
                using var device = new ComReference(devicePointer);
                Check(device.Call<Activate>(3)(devicePointer, ManagerInterface, 0x17, 0, out var managerPointer));
                using var manager = new ComReference(managerPointer);
                Check(manager.Call<Pointer>(5)(managerPointer, out var sessionsPointer));
                using var sessions = new ComReference(sessionsPointer);
                Check(sessions.Call<Number>(3)(sessionsPointer, out var sessionCount));
                for (var j = 0; j < sessionCount; j++)
                {
                    Check(sessions.Call<Item>(4)(sessionsPointer, j, out var controlPointer));
                    using var control = new ComReference(controlPointer);
                    using var control2 = control.Query(ControlInterface);
                    Check(control2.Call<Number>(14)(control2.Value, out var sessionPid));
                    if (sessionPid != pid) continue;
                    using var volume = control2.Query(VolumeInterface);
                    Check(volume.Call<Number>(6)(volume.Value, out var muted));
                    matched++;
                    if ((muted != 0) == desiredMuted) continue;
                    Check(volume.Call<SetMute>(5)(volume.Value, desiredMuted ? 1 : 0, 0)); restored++;
                }
            }
            return new(matched, restored);
        }
        finally { if (initialized >= 0) CoUninitialize(); }
    }
    private static void Check(int status) { if (status < 0) Marshal.ThrowExceptionForHR(status); }
    private sealed class ComReference(nint value) : IDisposable
    {
        public nint Value { get; } = value != 0 ? value : throw new InvalidOperationException("声音服务返回空接口。");
        public T Call<T>(int slot) where T : Delegate => Marshal.GetDelegateForFunctionPointer<T>(Marshal.ReadIntPtr(Marshal.ReadIntPtr(Value), slot * nint.Size));
        public ComReference Query(Guid iid) { Check(Marshal.QueryInterface(Value, in iid, out var pointer)); return new(pointer); }
        public void Dispose() => Marshal.Release(Value);
    }
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int Endpoints(nint self, int flow, uint state, out nint result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int Number(nint self, out int result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int Item(nint self, int index, out nint result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int Pointer(nint self, out nint result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int Activate(nint self, in Guid iid, uint context, nint parameters, out nint result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int SetMute(nint self, int muted, nint context);
    [DllImport("ole32.dll")] private static extern int CoInitializeEx(nint reserved, uint flags);
    [DllImport("ole32.dll")] private static extern void CoUninitialize();
    [DllImport("ole32.dll")] private static extern int CoCreateInstance(in Guid clsid, nint outer, uint context, in Guid iid, out nint result);
}
