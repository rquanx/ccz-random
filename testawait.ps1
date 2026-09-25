Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null=[Windows.Storage.Streams.IRandomAccessStreamWithContentType,Windows.Storage.Streams,ContentType=WindowsRuntime]
function AwaitOp($op,$resultType) {
  $iface=[type]::GetType("Windows.Foundation.IAsyncOperation``1[["+$resultType.AssemblyQualifiedName+"]]",$true)
  $cast=$op -as $iface
  $m=[System.WindowsRuntimeSystemExtensions].GetMethods() | ? {$_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1} | select -First 1
  $task=$m.MakeGenericMethod($resultType).Invoke($null,@($cast)); $task.GetAwaiter().GetResult()
}
$f=AwaitOp ([Windows.Storage.StorageFile]::GetFileFromPathAsync('C:\Users\91658\Documents\Codex\2026-09-18\hi\work\ccz-fast\ref_01.png')) ([Windows.Storage.StorageFile]); $f.Path
$op=$f.OpenReadAsync(); $op.GetType().FullName
$s=AwaitOp $op ([Windows.Storage.Streams.IRandomAccessStreamWithContentType]); $s.Size
